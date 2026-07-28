"""
Módulo compartilhado: busca e extração de dados da rota "all2" do Investidor10.

Usado tanto pelo script de coleta (coletar_dados.py) quanto por scripts
exploratórios. As funções aqui já foram validadas contra HTML real (276/276
FIIs extraídos corretamente, sem quebras).
"""

import re
import time

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

CATEGORIAS = {
    "acoes": "https://investidor10.com.br/acoes/all2/",
    "fiis": "https://investidor10.com.br/fiis/all2/",
    "stocks": "https://investidor10.com.br/stocks/all2/",
    "bdrs": "https://investidor10.com.br/bdrs/all2/",
    "etfs": "https://investidor10.com.br/etfs/all2/",
}

TIMEOUT = 15
DELAY_ENTRE_REQUESTS = 2  # segundos, por educação com o servidor

# Política de retry com backoff exponencial para falhas transitórias.
MAX_TENTATIVAS = 3
BACKOFF_BASE = 2  # segundos: espera = BACKOFF_BASE * 2**(tentativa-1)
STATUS_RETENTAVEIS = {429, 500, 502, 503, 504}

# Limite de páginas por categoria -- salvaguarda contra loop infinito caso
# a condição de parada da paginação nunca seja atingida.
MAX_PAGINAS = 100

# Divide por vírgula apenas quando ela for seguida de um novo rótulo de campo
# (ex: ", P/VP :"), e não quando faz parte do valor decimal (ex: "10,96 B").
# Inclui hífen na classe de caracteres do rótulo -- rótulos como "Preço-teto
# de Bazin" têm hífen, e sem isso a divisão falhava e o campo inteiro ficava
# grudado no campo anterior (bug real encontrado em produção).
PADRAO_DIVISAO_CAMPOS = re.compile(r",\s*(?=[A-ZÀ-Ý][\wÀ-ÿ/.\- ]*?:)")

# Campos que representam valores em R$ -- a sanitização extrai só o token
# "R$ X,XX" válido, descartando qualquer texto residual de uma divisão que
# tenha falhado (defesa extra, além do regex acima já corrigido).
CAMPOS_MOEDA = {"Preço Atual", "Preço-teto de Bazin", "Preço Justo de Graham"}

# Campos que são múltiplos/razões (ex: 28.4x), nunca percentuais -- se algum
# "%" vazar pra cá por causa de um campo vizinho mal dividido, a sanitização
# descarta tudo depois do número válido.
CAMPOS_RAZAO = {
    "P/L", "P/VP", "EV/EBIT", "P/Ativo", "P/SR", "P/Capital de Giro",
    "P/Ativo Circulante", "Liquidez Corrente", "PEG Ratio", "Giro de Ativos",
}

# Campos percentuais que já vêm como texto com "%" na fonte -- a sanitização
# mantém só o primeiro "número%" válido, descartando texto de outro campo
# que tenha vazado pra cá (ex: "12,34% Cresc. Lucro 5 anos : 8,10%" -> "12,34%").
CAMPOS_PERCENTUAL_TEXTO = {
    "ROE", "Margem Líquida", "Margem Bruta", "Margem EBIT",
    "Cresc. Receita 5 anos", "Cresc. Lucro 5 anos",
    "Dividend Yield", "DY Médio 5 anos",
}

# Campos percentuais que vêm como número cru sem "%" (ex: "48.501110424782")
# -- a formatação com "%" acontece na exibição (schema), aqui só limpamos
# qualquer texto residual, mantendo só o número.
CAMPOS_PERCENTUAL_NUMERO_CRU = {"Upside Bazin", "Upside Graham"}


def _sanitizar_valor(chave: str, valor: str) -> str:
    """Aplica limpeza defensiva conforme o tipo conhecido do campo."""
    if chave in CAMPOS_MOEDA:
        m = re.match(r"R\$\s*-?\d[\d.,]*", valor)
        return m.group(0) if m else valor

    if chave in CAMPOS_RAZAO:
        m = re.match(r"-?\d[\d.,]*", valor)
        return m.group(0) if m else valor

    if chave in CAMPOS_PERCENTUAL_TEXTO:
        m = re.match(r"-?\d[\d.,]*\s*%", valor)
        return m.group(0) if m else valor

    if chave in CAMPOS_PERCENTUAL_NUMERO_CRU:
        m = re.match(r"-?\d+\.?\d*", valor)
        return m.group(0) if m else valor

    return valor


def buscar_pagina(url: str, page: int | None = 1) -> str:
    """
    Faz o GET de uma página da rota all2, com retry e backoff exponencial.

    Retenta em falhas de conexão/timeout e em respostas com status transitório
    (429, 500, 502, 503, 504), respeitando o header ``Retry-After`` quando
    presente. Erros HTTP não-retentáveis (ex: 404) são levantados na hora.
    Levanta a última exceção se esgotar as tentativas.
    """
    params = {"page": page} if page else {}
    ultimo_erro: Exception | None = None

    for tentativa in range(1, MAX_TENTATIVAS + 1):
        espera = BACKOFF_BASE * (2 ** (tentativa - 1))
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
        except requests.RequestException as e:
            ultimo_erro = e
        else:
            if resp.status_code in STATUS_RETENTAVEIS:
                ultimo_erro = requests.HTTPError(
                    f"HTTP {resp.status_code} para {resp.url}", response=resp
                )
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    espera = max(espera, int(retry_after))
            else:
                resp.raise_for_status()  # 4xx não-retentável levanta agora
                return resp.text

        if tentativa == MAX_TENTATIVAS:
            break

        print(
            f"    [retry] tentativa {tentativa}/{MAX_TENTATIVAS} falhou "
            f"({ultimo_erro}); aguardando {espera}s..."
        )
        time.sleep(espera)

    raise ultimo_erro


def extrair_ativos(html: str) -> list[dict]:
    """
    Extrai os ativos listados na rota all2.

    Estrutura real (o link é relativo, ex: href="kncr11"):

    <section id="card-articles">
      ...<ul>
        <li>
          <a href="kncr11">
            <strong>KNCR11</strong> — Nome , Campo : valor , Campo : valor ... , Empresa : Nome
          </a>
        </li>
      </ul>...
    </section>
    """
    soup = BeautifulSoup(html, "lxml")
    resultados = []
    vistos = set()

    container = soup.select_one("section#card-articles") or soup

    for li in container.find_all("li"):
        a = li.find("a")
        if not a:
            continue

        strong = a.find("strong")
        ticker = strong.get_text(strip=True) if strong else None
        if not ticker or ticker in vistos:
            continue

        texto = a.get_text(" ", strip=True)
        # colapsa qualquer sequência de espaços/quebras de linha em um único
        # espaço -- o HTML de origem tem indentação/whitespace interno que
        # o get_text preserva, gerando valores com \n soltos no meio
        texto = re.sub(r"\s+", " ", texto)
        if "—" not in texto:
            continue

        apos_travessao = texto.split("—", 1)[1]
        partes = [p.strip() for p in PADRAO_DIVISAO_CAMPOS.split(apos_travessao)]

        nome = partes[0] if partes else None
        campos = {}
        for parte in partes[1:]:
            if ":" in parte:
                chave, valor = parte.split(":", 1)
                chave = chave.strip()
                valor = valor.strip()
                # o HTML de alguns campos (ex: Dividend Yield) renderiza o "%" num
                # elemento separado, o que gera duplicação tipo "13,37%%" ao juntar
                # o texto -- colapsa qualquer sequência de "%" (com ou sem espaço) em um só
                valor = re.sub(r"\s*%\s*%+", "%", valor)
                valor = _sanitizar_valor(chave, valor)
                campos[chave] = valor

        vistos.add(ticker)
        resultados.append(
            {"ticker": ticker, "nome": nome, "href_relativo": a.get("href"), **campos}
        )

    return resultados


def coletar_categoria(categoria: str) -> list[dict]:
    """
    Busca e extrai todos os ativos de uma categoria (ex: 'fiis'), paginando
    até o fim.

    A cada página, ignora tickers já vistos em páginas anteriores; quando uma
    página não traz nenhum ticker inédito (lista vazia ou só duplicatas),
    entende que chegou ao fim e para. Isso funciona tanto se a rota all2
    paginar de verdade quanto se devolver a lista inteira já na página 1.
    """
    url = CATEGORIAS[categoria]
    todos: list[dict] = []
    vistos: set[str] = set()

    for page in range(1, MAX_PAGINAS + 1):
        html = buscar_pagina(url, page=page)
        ativos = extrair_ativos(html)

        novos = [a for a in ativos if a["ticker"] not in vistos]
        if not novos:
            break

        vistos.update(a["ticker"] for a in novos)
        todos.extend(novos)

        if page < MAX_PAGINAS:
            time.sleep(DELAY_ENTRE_REQUESTS)

    return todos