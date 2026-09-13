import sys
from pathlib import Path

# garante que "import investidor10_scraper" funcione ao rodar pytest da raiz
# do projeto, sem precisar instalar o pacote.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
