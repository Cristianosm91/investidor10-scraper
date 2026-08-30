"""
Coleta os dados de todas as categorias (ações, FIIs, BDRs, stocks, ETFs)
e salva localmente em arquivos JSON dentro da pasta do projeto.

Uso:
    python src/coletar_dados.py
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# garante que o módulo irmão seja importado independentemente do diretório atual
sys.path.insert(0, str(Path(__file__).resolve().parent))

from investidor10_scraper import CATEGORIAS, DELAY_ENTRE_REQUESTS, coletar_categoria

logger = logging.getLogger(__name__)

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
        logger.info("Coletando %s...", categoria)
        try:
            itens = coletar_categoria(categoria)
        except Exception as e:
            logger.error("  [ERRO] Falha ao coletar %s: %s", categoria, e)
            metadata["categorias"][categoria] = {"total": 0, "erro": str(e)}
            time.sleep(DELAY_ENTRE_REQUESTS)
            continue

        caminho = PASTA_DADOS / f"{categoria}.json"
        salvar_json(caminho, itens)

        logger.info("  %d ativos salvos em %s", len(itens), caminho)
        metadata["categorias"][categoria] = {"total": len(itens)}

        time.sleep(DELAY_ENTRE_REQUESTS)

    salvar_json(PASTA_DADOS / "_metadata.json", metadata)
    logger.info("\nColeta concluída em %s.", metadata["coletado_em"])
    logger.info("Metadados salvos em %s", PASTA_DADOS / "_metadata.json")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
