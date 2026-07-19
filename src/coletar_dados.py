"""
Coleta os dados de todas as categorias (ações, FIIs, BDRs, stocks, ETFs)
e salva localmente em arquivos JSON dentro da pasta do projeto.

Uso:
    python src/coletar_dados.py
"""

import json
import time
from datetime import datetime
from pathlib import Path

import requests

from investidor10_scraper import CATEGORIAS, DELAY_ENTRE_REQUESTS, coletar_categoria

ROOT = Path(__file__).resolve().parent.parent
PASTA_DADOS = ROOT / "data"


def salvar_json(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def main():
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    metadata = {
        "coletado_em": datetime.now().isoformat(timespec="seconds"),
        "categorias": {},
    }

    for categoria in CATEGORIAS:
        print(f"Coletando {categoria}...")
        try:
            itens = coletar_categoria(categoria)
        except requests.RequestException as e:
            print(f"  [ERRO] Falha ao coletar {categoria}: {e}")
            metadata["categorias"][categoria] = {"total": 0, "erro": str(e)}
            time.sleep(DELAY_ENTRE_REQUESTS)
            continue

        caminho = PASTA_DADOS / f"{categoria}.json"
        salvar_json(caminho, itens)

        print(f"  {len(itens)} ativos salvos em {caminho}")
        metadata["categorias"][categoria] = {"total": len(itens)}

        time.sleep(DELAY_ENTRE_REQUESTS)

    salvar_json(PASTA_DADOS / "_metadata.json", metadata)
    print(f"\nColeta concluída em {metadata['coletado_em']}.")
    print(f"Metadados salvos em {PASTA_DADOS / '_metadata.json'}")


if __name__ == "__main__":
    main()
