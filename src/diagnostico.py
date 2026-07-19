"""
Script de diagnóstico: salva o HTML bruto recebido do Investidor10
e imprime pistas sobre por que o parser não encontrou nada.
"""

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

URL = "https://investidor10.com.br/fiis/all2/"

resp = requests.get(URL, headers=HEADERS, params={"page": 1}, timeout=15)

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
with open("diagnostico_fiis.html", "w", encoding="utf-8") as f:
    f.write(resp.text)
print("\nHTML completo salvo em: diagnostico_fiis.html")
