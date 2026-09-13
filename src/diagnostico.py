"""
Script de diagnóstico: verifica rapidamente todas as categorias e salva o
HTML bruto de uma delas para inspeção manual.

Detecta os dois problemas que já ocorreram em produção:
1) a rota redirecionar (HTTP 302) para a home em vez de devolver a listagem
   de ativos -- a lib de HTTP segue o redirect e devolve status 200, então
   só olhar `status_code` não é suficiente; é preciso comparar a URL final
   (`resp.url`) com a categoria pedida.
2) a resposta vir com status 200, na categoria certa, mas com a tabela de
   ativos vazia (0 linhas) -- por isso este script também roda o parser de
   verdade (`extrair_ativos`) e mostra quantos ativos ele conseguiu extrair.

Usa a mesma sessão do scraper (`investidor10_scraper.SESSION`), que já
imita um navegador real via `curl_cffi` (ver docstring de
investidor10_scraper.py) -- rodar este diagnóstico com uma sessão diferente
da usada pela coleta de verdade tornaria os resultados não comparáveis.

Uso:
    python src/diagnostico.py            # dump detalhado de 'fiis'
    python src/diagnostico.py acoes      # dump detalhado de 'acoes'
"""

import sys
from pathlib import Path

from bs4 import BeautifulSoup

# garante que o módulo irmão seja importado independentemente do diretório atual
sys.path.insert(0, str(Path(__file__).resolve().parent))

from investidor10_scraper import (
    CATEGORIAS,
    IMPERSONATE,
    SESSION,
    TIMEOUT,
    curl_requests,
    extrair_ativos,
    url_pertence_a_categoria,
)

ROOT = Path(__file__).resolve().parent.parent

PISTAS_BLOQUEIO = [
    "captcha", "Just a moment", "cloudflare", "cf-browser-verification",
    "Access denied", "Are you human", "checking your browser",
]


def checar_categoria(categoria: str, url: str):
    """Faz um GET simples (sem retry) e imprime um resumo do status."""
    resp = SESSION.get(url, params={"page": 1}, timeout=TIMEOUT)
    redirecionou_pra_fora = not url_pertence_a_categoria(resp.url, categoria)

    print(f"[{categoria}] status={resp.status_code}  url_final={resp.url}")
    if resp.history:
        cadeia = " -> ".join(str(r.status_code) for r in resp.history)
        print(f"          redirecionamentos: {cadeia} -> {resp.status_code}")
    if redirecionou_pra_fora:
        print(f"          [ALERTA] saiu da categoria '{categoria}' -- provável "
              f"redirecionamento pra home. NÃO é uma coleta válida.")

    total_tables = len(BeautifulSoup(resp.text, "lxml").find_all("table"))
    ativos = extrair_ativos(resp.text, categoria)
    if ativos is None:
        print(f"          [ALERTA] parser não encontrou tabela reconhecível "
              f"({total_tables} <table> no HTML).")
    elif len(ativos) == 0:
        print(f"          [ALERTA] tabela encontrada mas com 0 ativos extraídos "
              f"({total_tables} <table> no HTML) -- provável bloqueio "
              f"anti-bot servindo uma versão sem dados, ou parser desatualizado.")
    else:
        print(f"          OK: {len(ativos)} ativos extraídos na página 1 "
              f"(ex.: {ativos[0]['ticker']}).")

    print(f"          tamanho={len(resp.text)} chars  "
          f"content-type={resp.headers.get('Content-Type')}")
    return resp


def main():
    categoria_detalhada = sys.argv[1] if len(sys.argv) > 1 else "fiis"
    if categoria_detalhada not in CATEGORIAS:
        print(f"Categoria desconhecida: {categoria_detalhada!r}. "
              f"Opções: {', '.join(CATEGORIAS)}")
        sys.exit(1)

    print(f"(user-agent/TLS imitados: curl_cffi impersonate={IMPERSONATE!r})\n")
    print("== Checagem rápida de todas as categorias (page=1) ==\n")
    respostas = {}
    for categoria, url in CATEGORIAS.items():
        try:
            respostas[categoria] = checar_categoria(categoria, url)
        except curl_requests.exceptions.RequestException as e:
            print(f"[{categoria}] [ERRO] {e}")
        print()

    print(f"== Dump detalhado de '{categoria_detalhada}' ==\n")
    resp = respostas.get(categoria_detalhada)
    if resp is None:
        print("Não foi possível obter essa categoria (ver erro acima).")
        sys.exit(1)

    for pista in PISTAS_BLOQUEIO:
        if pista.lower() in resp.text.lower():
            print(f"[PISTA DE BLOQUEIO] Encontrado: '{pista}'")

    # verifica se algum ticker conhecido aparece no HTML bruto (apenas para 'fiis')
    if categoria_detalhada == "fiis":
        for ticker in ["KNCR11", "HGLG11", "MXRF11"]:
            print(f"Ticker '{ticker}' presente no HTML? {ticker in resp.text}")

    print()
    print("Primeiros 1500 caracteres da resposta:")
    print(resp.text[:1500])

    print()
    print("Últimos 1000 caracteres da resposta:")
    print(resp.text[-1000:])

    arquivo_saida = ROOT / f"diagnostico_{categoria_detalhada}.html"
    with open(arquivo_saida, "w", encoding="utf-8") as f:
        f.write(resp.text)
    print(f"\nHTML completo salvo em: {arquivo_saida}")


if __name__ == "__main__":
    main()
