"""
Script de diagnóstico: salva o HTML bruto recebido do Investidor10
e imprime pistas sobre por que o parser não encontrou nada.

Uso:
    python src/diagnostico.py
"""

import sys
from pathlib import Path

import requests

# garante que o módulo irmão seja importado independentemente do diretório atual
sys.path.insert(0, str(Path(__file__).resolve().parent))

from investidor10_scraper import CATEGORIAS, HEADERS, TIMEOUT

ROOT = Path(__file__).resolve().parent.parent
URL = CATEGORIAS["fiis"]
ARQUIVO_SAIDA = ROOT / "diagnostico_fiis.html"


def main():
    resp = requests.get(URL, headers=HEADERS, params={"page": 1}, timeout=TIMEOUT)

    print(f"Status code: {resp.status_code}")
    print(f"Tamanho da resposta: {len(resp.text)} caracteres")
    print(f"Content-Type: {resp.headers.get('Content-Type')}")
    print()

    # pistas de bloqueio comum (Cloudflare, captcha, etc.)
    pistas = ["captcha", "Just a moment", "cloudflare", "cf-browser-verification",
              "Access denied", "Are you human", "checking your browser"]
    for pista in pistas:
        if pista.lower() in resp.text.lower():
            print(f"[PISTA DE BLOQUEIO] Encontrado: '{pista}'")

    # verifica se algum ticker conhecido aparece no HTML bruto
    for ticker in ["KNCR11", "HGLG11", "MXRF11"]:
        presente = ticker in resp.text
        print(f"Ticker '{ticker}' presente no HTML? {presente}")

    print()
    print("Primeiros 1500 caracteres da resposta:")
    print(resp.text[:1500])

    print()
    print("Últimos 1000 caracteres da resposta:")
    print(resp.text[-1000:])

    # salva o HTML completo pra inspeção manual, se precisar
    with open(ARQUIVO_SAIDA, "w", encoding="utf-8") as f:
        f.write(resp.text)
    print(f"\nHTML completo salvo em: {ARQUIVO_SAIDA}")


if __name__ == "__main__":
    main()
