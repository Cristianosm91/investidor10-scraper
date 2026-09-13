"""
Módulo compartilhado: busca e extração de dados da listagem pública de ativos
do Investidor10.

Usado tanto pelo script de coleta (coletar_dados.py) quanto por scripts
exploratórios.

Histórico importante (ver README, seção "Observações"):
A rota antiga `/{categoria}/all2/` passou a devolver HTTP 302 para a home
(`https://investidor10.com.br/`) em requisições sem sessão de navegador --
provavelmente uma rota interna do site que ficou restrita. A home contém
apenas alguns ativos "mais buscados" (destaque), então um parser que não
verifica o redirecionamento acaba silenciosamente tratando esses poucos
destaques como se fosse a coleta completa.

A rota pública confirmada e usada atualmente é a listagem paginada de cada
categoria, ex.: `https://investidor10.com.br/fiis/?page=2`. Essa rota
devolve HTML 200 (sem redirecionamento) com uma tabela `<table>` real,
paginada via query string `page`. Cada linha da tabela tem uma célula com
um link `<a href="/fiis/<ticker>/" title="Nome da empresa/fundo">`, e as
demais colunas variam por categoria (ex: para FIIs: Patrimônio Líquido,
P/VP, Dividend Yield, etc.) -- por isso `extrair_ativos` lê os cabeçalhos
de `<thead>` dinamicamente em vez de fixar nomes de coluna.

Limitação conhecida: essa listagem não traz "Preço Atual" nem os preços-
teto de Bazin/Graham (que a rota antiga trazia) -- esses dados só existem
na página de cada ativo individual. Ver README para detalhes.

Estratégia de requisição (histórico da 2ª correção):
A 1ª correção deste módulo trocou a rota (de `all2/` para a listagem
paginada) mas manteve `requests` puro para buscar as páginas. Em produção
(fora deste ambiente de desenvolvimento), isso continuou devolvendo "0
ativos" em todas as categorias -- sem redirecionamento, sem erro HTTP,
apenas a tabela sem nenhuma linha reconhecida. A hipótese mais provável é
que o site tem alguma forma de detecção de tráfego automatizado baseada em
fingerprint de TLS/HTTP (não apenas no header `User-Agent`) -- a biblioteca
`requests`/`urllib3` tem uma "assinatura" de handshake TLS (JA3) facilmente
distinguível de um navegador real, mesmo com headers de navegador. Diversas
tentativas de busca ao vivo (fora deste projeto) mostraram o HTML completo
sendo servido normalmente, o que descarta a hipótese de conteúdo carregado
só via JavaScript.

Por isso este módulo passou a usar `curl_cffi` (`pip install curl_cffi`),
que faz o handshake TLS/HTTP imitando um navegador Chrome real
(`impersonate="chrome131"`), resolvendo o mismatch de fingerprint sem
precisar de um navegador headless completo (Playwright/Selenium). A API é
compatível com `requests` (`Session`, `.get()`, `resp.status_code`,
`resp.url`, `resp.history`, `resp.headers`), então a lógica de retry,
backoff e detecção de redirecionamento não mudou -- só a implementação do
transporte HTTP.

Se mesmo assim a coleta continuar vindo vazia, o próximo degrau é um
navegador headless de verdade (Playwright) -- ver README, seção
"Observações".
"""

import re
import time
import logging
from urllib.parse import urlparse

from curl_cffi import requests as curl_requests
from curl_cffi.requests import Session
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Navegador imitado no handshake TLS/HTTP (JA3/JA4 + ordem de headers), não
# apenas no header User-Agent -- ver docstring do módulo.
IMPERSONATE = "chrome131"

# Sessão reutilizada entre requisições (keep-alive + headers centralizados).
SESSION: Session = Session(impersonate=IMPERSONATE)
SESSION.headers.update(HEADERS)

# Rota pública e paginada de listagem de cada categoria (ver docstring do
# módulo). Substituiu a antiga rota `all2/`, que passou a redirecionar
# (HTTP 302) para a home em requisições sem sessão de navegador.
CATEGORIAS = {
    "acoes": "https://investidor10.com.br/acoes/",
    "fiis": "https://investidor10.com.br/fiis/",
    "stocks": "https://investidor10.com.br/stocks/",
    "bdrs": "https://investidor10.com.br/bdrs/",
    "etfs": "https://investidor10.com.br/etfs/",
}

TIMEOUT = 15
DELAY_ENTRE_REQUESTS = 2  # segundos, por educação com o servidor

# Política de retry com backoff exponencial para falhas transitórias.
MAX_TENTATIVAS = 3
BACKOFF_BASE = 2  # segundos: espera = BACKOFF_BASE * 2**(tentativa-1)
STATUS_RETENTAVEIS = {429, 500, 502, 503, 504}

# Limite de páginas por categoria -- salvaguarda contra loop infinito caso
# a condição de parada da paginação nunca seja atingida.
MAX_PAGINAS = 200

_sessao_aquecida = False


class RedirecionadoParaHomeError(RuntimeError):
    """
    Levantada quando a rota da categoria redireciona para fora da própria
    categoria (tipicamente para a home, "https://investidor10.com.br/").

    Isso indica que a resposta NÃO é uma listagem de ativos válida -- a
    home só tem alguns ativos em destaque e nunca deve ser tratada como
    coleta completa.
    """


def url_pertence_a_categoria(url: str, categoria: str) -> bool:
    """Confere se `url` ainda pertence à categoria esperada (path começa com
    ``/categoria``). Usado para detectar redirecionamento pra fora da rota
    pedida (ex: pra home), o que HTTP 200 + `resp.raise_for_status()` sozinhos
    não pegam, já que `requests` segue redirects por padrão."""
    caminho = urlparse(url).path.strip("/").lower()
    categoria = categoria.lower()
    return caminho == categoria or caminho.startswith(f"{categoria}/")


def _aquecer_sessao() -> None:
    """
    Faz uma visita inicial à home para a sessão receber os cookies que o
    site costuma exigir (proteção anti-bot/WAF) antes de aceitar requisições
    às páginas de listagem. Roda no máximo uma vez por processo; falhas aqui
    não são fatais, pois `buscar_pagina` já tem seu próprio retry.
    """
    global _sessao_aquecida
    if _sessao_aquecida:
        return
    try:
        SESSION.get("https://investidor10.com.br/", timeout=TIMEOUT)
    except curl_requests.exceptions.RequestException as e:
        logger.warning("[aquecimento] falha ao aquecer sessão (%s); seguindo mesmo assim.", e)
    _sessao_aquecida = True


def buscar_pagina(url: str, categoria: str, page: int | None = 1) -> str:
    """
    Faz o GET de uma página da listagem de `categoria`, com retry e backoff
    exponencial.

    Retenta em falhas de conexão/timeout, em respostas com status transitório
    (429, 500, 502, 503, 504) e em respostas que acabaram redirecionadas pra
    fora da categoria pedida (ver `RedirecionadoParaHomeError`) -- esse
    último caso pode ser uma instabilidade passageira da proteção anti-bot
    do site. Erros HTTP não-retentáveis (ex: 404) são levantados na hora.
    Levanta a última exceção se esgotar as tentativas.
    """
    params = {"page": page} if page else {}
    ultimo_erro: Exception | None = None

    for tentativa in range(1, MAX_TENTATIVAS + 1):
        espera = BACKOFF_BASE * (2 ** (tentativa - 1))
        try:
            resp = SESSION.get(url, params=params, timeout=TIMEOUT)
        except curl_requests.exceptions.RequestException as e:
            ultimo_erro = e
        else:
            if resp.status_code in STATUS_RETENTAVEIS:
                ultimo_erro = curl_requests.exceptions.HTTPError(
                    f"HTTP {resp.status_code} para {resp.url}", response=resp
                )
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    espera = max(espera, int(retry_after))
            elif not url_pertence_a_categoria(resp.url, categoria):
                ultimo_erro = RedirecionadoParaHomeError(
                    f"{url} (page={page}) redirecionou para {resp.url} -- "
                    f"esperado uma URL da categoria '{categoria}'. A home não "
                    f"é uma coleta válida."
                )
            else:
                resp.raise_for_status()  # 4xx não-retentável levanta agora
                return resp.text

        if tentativa == MAX_TENTATIVAS:
            break

        logger.warning(
            "[retry] tentativa %d/%d falhou (%s); aguardando %ds...",
            tentativa, MAX_TENTATIVAS, ultimo_erro, espera,
        )
        time.sleep(espera)

    raise ultimo_erro or RuntimeError("buscar_pagina falhou sem exceção registrada")


def _limpar_texto(texto: str) -> str:
    """Colapsa espaços/quebras de linha internos em um único espaço."""
    return re.sub(r"\s+", " ", texto).strip()


def extrair_ativos(html: str, categoria: str) -> list[dict] | None:
    """
    Extrai os ativos listados na tabela de uma página de `categoria`.

    Estrutura real confirmada em produção (capturada via diagnostico.py,
    exemplo de FIIs):

        <table id="rankigns" class="stripped" ...>   <!-- sic: "rankigns" -->
          <thead>
            <tr>
              <th data-name="ticker" ...>Ativos</th>
              <th data-name="net_worth" ...><div>Patrimônio Líquido</div></th>
              ...
            </tr>
          </thead>
          <tbody>
            <tr class="odd">
              <td data-column="ticker">
                <div class="logo ...">
                  <button ...>...</button>  <!-- botão de "seguir", antes do link -->
                  <a href="https://investidor10.com.br/fiis/kncr11/"
                     title="Kinea Rendimentos Imobiliários Fundos">
                    <span>KNCR11</span>
                  </a>
                </div>
              </td>
              <td data-name="net_worth" data-order="10978689824.66">
                <div><div class="money">10,98 B</div></div>
              </td>
              ...
            </tr>
          </tbody>
        </table>

    Dois detalhes importantes que já causaram um bug real (0 ativos
    extraídos apesar da tabela ser encontrada):
    - o link do ativo é uma URL **absoluta** (com esquema e host), não
      relativa -- o regex de reconhecimento precisa aceitar as duas formas;
    - a célula do ticker some tem `data-column="ticker"` (não `data-name`
      como as demais colunas), então ela é pulada ao montar os campos pelo
      `data-name` de cada `<td>` -- o que é o comportamento certo, pois seu
      conteúdo já vira `ticker`/`nome`.

    A tabela é localizada, em ordem de preferência: (1) por
    `id="rankigns"` (id visto em produção); (2) por conter algum link para
    `/{categoria}/<ticker>/` (absoluto ou relativo); (3) por ter, no
    `<thead>`, um primeiro `<th>` com texto "Ativos" (cobre o caso de uma
    tabela do formato certo mas sem nenhuma linha). Múltiplas estratégias
    porque `id`/classes CSS podem mudar sem aviso -- não é uma API estável.

    As demais colunas são mapeadas pelo atributo `data-name` de cada
    `<td>` (ex.: `net_worth`, `p_vp`, `dividend_yield_last_12_months`) em
    vez de posição/texto do cabeçalho -- mais estável a colunas ocultas ou
    reordenadas.

    Retorna `None` (não `[]`) quando nenhuma tabela reconhecível é
    encontrada, para que o chamador distinga "página sem tabela" (possível
    quebra do site/parser) de "tabela presente e vazia" (fim legítimo da
    paginação). Ver `coletar_categoria`.
    """
    soup = BeautifulSoup(html, "lxml")
    # Aceita href relativo ("/fiis/kncr11/") OU absoluto
    # ("https://investidor10.com.br/fiis/kncr11/") -- em produção o site usa
    # URL absoluta, mas isso pode mudar.
    href_regex = re.compile(
        rf"^(?:https?://(?:www\.)?investidor10\.com\.br)?"
        rf"/{re.escape(categoria)}/([A-Za-z0-9._-]+)/?(?:\?.*)?$",
        re.IGNORECASE,
    )

    tabela = soup.find("table", id="rankigns")

    if tabela is None:
        for tbl in soup.find_all("table"):
            if tbl.find("a", href=href_regex):
                tabela = tbl
                break

    if tabela is None:
        # Nenhuma tabela com link de ativo -- pode ser uma página real sem
        # itens (ex: fim legítimo da paginação, tabela presente mas vazia).
        # Como fallback, reconhece a tabela certa pelo cabeçalho "Ativos"
        # mesmo sem nenhuma linha de dado.
        for tbl in soup.find_all("table"):
            thead = tbl.find("thead")
            primeiro_th = thead.find("th") if thead else None
            if primeiro_th and _limpar_texto(primeiro_th.get_text()).lower() == "ativos":
                tabela = tbl
                break

    if tabela is None:
        return None

    corpo = tabela.find("tbody") or tabela
    resultados = []
    vistos = set()

    for tr in corpo.find_all("tr"):
        celula_ticker = (
            tr.find("td", attrs={"data-column": "ticker"})
            or tr.find("td", attrs={"data-name": "ticker"})
        )
        if celula_ticker is None:
            celulas = tr.find_all("td")
            celula_ticker = celulas[0] if celulas else None
        if celula_ticker is None:
            continue

        link = celula_ticker.find("a", href=href_regex)
        if not link:
            continue

        href = str(link.get("href", ""))
        m = href_regex.match(href)
        ticker = m.group(1).upper() if m else _limpar_texto(link.get_text()).upper()
        if not ticker or ticker in vistos:
            continue

        titulo = link.get("title")
        nome = _limpar_texto(str(titulo) if titulo else link.get_text(" ", strip=True))
        caminho = urlparse(href).path or href

        item: dict = {"ticker": ticker, "nome": nome, "url_relativa": caminho}

        for td in tr.find_all("td"):
            chave = td.get("data-name")
            if not chave:
                continue
            chave = str(chave)
            item[chave] = _limpar_texto(td.get_text(" ", strip=True))

        vistos.add(ticker)
        resultados.append(item)

    return resultados


def coletar_categoria(categoria: str) -> list[dict]:
    """
    Busca e extrai todos os ativos de uma categoria (ex: 'fiis'), paginando
    até o fim.

    A cada página, ignora tickers já vistos em páginas anteriores; quando uma
    página não traz nenhum ticker inédito (lista vazia, só duplicatas, ou a
    tabela não é encontrada), entende que chegou ao fim e para -- exceto na
    página 1: se a própria primeira página não tiver a tabela reconhecível,
    isso indica falha real (parser desatualizado, bloqueio, ou resposta
    inesperada) e a função levanta um erro em vez de devolver uma coleta
    parcial/vazia como se fosse sucesso.
    """
    url = CATEGORIAS[categoria]
    _aquecer_sessao()

    todos: list[dict] = []
    vistos: set[str] = set()

    for page in range(1, MAX_PAGINAS + 1):
        html = buscar_pagina(url, categoria, page=page)
        ativos = extrair_ativos(html, categoria)

        if page == 1 and not ativos:
            # None (tabela não encontrada) OU [] (tabela encontrada mas sem
            # nenhuma linha reconhecida) na primeira página nunca é um
            # resultado legítimo para "todos os ativos de uma categoria" --
            # tratar como sucesso aqui é exatamente o bug que já causou
            # coleta incompleta no passado (all2/ redirecionando pra home).
            motivo = "nenhuma tabela reconhecível" if ativos is None else "tabela encontrada, mas 0 linhas extraídas"
            raise ValueError(
                f"Coleta de '{categoria}' falhou na página 1 de {url} "
                f"({motivo}) -- a estrutura do HTML pode ter mudado, ou o "
                f"site pode estar servindo uma resposta diferente para "
                f"requisições automatizadas. Rode diagnostico.py e inspecione "
                f"diagnostico_{categoria}.html manualmente."
            )

        if ativos is None:
            break

        novos = [a for a in ativos if a["ticker"] not in vistos]
        if not novos:
            break

        vistos.update(a["ticker"] for a in novos)
        todos.extend(novos)

        if page < MAX_PAGINAS:
            time.sleep(DELAY_ENTRE_REQUESTS)

    return todos
