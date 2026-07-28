"""
Gera o dashboard HTML do projeto Investidor10 a partir dos dados coletados
em ./data/ (acoes.json, fiis.json, stocks.json, bdrs.json, etfs.json).

Segue a estrutura de pastas:
    projeto/
      scripts/gerar_dashboard.py   <- este arquivo
      data/*.json
      templates/dashboard.html     <- gerado
      static/css/style.css         <- referenciado, não embutido
      static/js/scripts.js         <- referenciado, não embutido

Uso:
    python gerar_dashboard.py
"""

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_FILE = ROOT / "templates" / "dashboard.html"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

NOMES_CATEGORIA = {
    "acoes": "Ações",
    "fiis": "FIIs",
    "stocks": "Stocks",
    "bdrs": "BDRs",
    "etfs": "ETFs",
}

# Os dados do Investidor10 já vêm com rótulos legíveis em português
# (ex: "Patrimônio Líquido", "Dividend Yield"), então o mapeamento aqui
# só cobre as chaves internas do próprio scraper.
LABELS = {
    "ticker": "Ticker",
    "nome": "Empresa",
}

CAMPOS_OCULTOS_EXPLICITOS = {"href_relativo", "empresa"}
PADRAO_ID_INTERNO = re.compile(r"^[a-z]+id$")

PRIORIDADE_COLUNAS = ["ticker", "nome"]

# Campos que vêm como número cru (sem "%") mas representam percentual --
# precisam do sufixo "%" na exibição (formatado no scripts.js via essa flag).
PADRAO_CAMPO_PERCENTUAL_BRUTO = re.compile(r"upside", re.IGNORECASE)


def eh_campo_percentual_bruto(chave: str) -> bool:
    return bool(PADRAO_CAMPO_PERCENTUAL_BRUTO.search(chave))


def eh_campo_oculto(chave: str) -> bool:
    chave_lower = chave.lower()
    return chave_lower in CAMPOS_OCULTOS_EXPLICITOS or bool(PADRAO_ID_INTERNO.match(chave_lower))


def formatar_label(chave: str) -> str:
    if chave in LABELS:
        return LABELS[chave]
    if chave.lower() in LABELS:
        return LABELS[chave.lower()]
    # chaves que já vêm com maiúscula/acento (padrão do Investidor10) passam direto
    if chave != chave.lower():
        return chave
    # fallback para chaves cruas desconhecidas: "algum_campo" -> "Algum Campo"
    return chave.replace("_", " ").strip().title()


def carregar_dados():
    dados = {}
    for categoria in NOMES_CATEGORIA:
        caminho = DATA_DIR / f"{categoria}.json"
        if caminho.exists():
            with open(caminho, encoding="utf-8") as f:
                dados[categoria] = json.load(f)
        else:
            dados[categoria] = []

    metadata_caminho = DATA_DIR / "_metadata.json"
    metadata = {}
    if metadata_caminho.exists():
        with open(metadata_caminho, encoding="utf-8") as f:
            metadata = json.load(f)

    return dados, metadata


def calcular_schema(dados: dict) -> dict:
    schema = {}
    for categoria, itens in dados.items():
        vistas = set()
        colunas = []

        for chave in PRIORIDADE_COLUNAS:
            if any(chave in item for item in itens) and chave not in vistas and not eh_campo_oculto(chave):
                vistas.add(chave)
                colunas.append(chave)

        for item in itens:
            for chave in item.keys():
                if chave in vistas or eh_campo_oculto(chave):
                    continue
                vistas.add(chave)
                colunas.append(chave)

        schema[categoria] = [
            {"chave": c, "label": formatar_label(c), "percentual": eh_campo_percentual_bruto(c)}
            for c in colunas
        ]

    return schema


def montar_html(dados: dict, metadata: dict) -> str:
    schema = calcular_schema(dados)
    payload = {
        "dados": dados,
        "metadata": metadata,
        "nomes": NOMES_CATEGORIA,
        "schema": schema,
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    coletado_em = metadata.get("coletado_em", "desconhecido")

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Painel Investidor10</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../static/css/style.css">
</head>
<body>
  <header class="topbar">
    <div class="topbar-title">
      <h1>Painel Investidor10</h1>
      <div class="meta">fonte: dados locais &middot; coletado em {coletado_em}</div>
    </div>
    <button id="btn-filtros" class="btn-filtros" type="button">
      <span class="ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><line x1="4" y1="21" x2="4" y2="14"></line><line x1="4" y1="10" x2="4" y2="3"></line><line x1="12" y1="21" x2="12" y2="12"></line><line x1="12" y1="8" x2="12" y2="3"></line><line x1="20" y1="21" x2="20" y2="16"></line><line x1="20" y1="12" x2="20" y2="3"></line><line x1="1" y1="14" x2="7" y2="14"></line><line x1="9" y1="8" x2="15" y2="8"></line><line x1="17" y1="16" x2="23" y2="16"></line></svg></span> Filtros <span class="badge" id="badge-filtros" hidden>0</span>
    </button>
  </header>

  <div class="marquee-wrap"><div class="marquee-track" id="marquee"></div></div>

  <nav class="tabs" id="tabs"></nav>

  <div class="controls">
    <input type="text" id="busca" placeholder="Filtrar por ticker, nome ou segmento...">
    <div class="controls-right">
      <label class="pagina-tamanho-label">Exibir
        <select id="tamanho-pagina">
          <option value="50" selected>50</option>
          <option value="100">100</option>
          <option value="150">150</option>
          <option value="200">200</option>
          <option value="250">250</option>
          <option value="todos">Todos</option>
        </select>
      </label>
      <div class="count" id="contagem"></div>
    </div>
  </div>

  <div class="layout">
    <aside class="filtros-painel" id="filtros-painel" hidden>
      <div class="filtros-header">
        <span>Filtros por indicador</span>
        <button id="btn-limpar-filtros" type="button">Limpar</button>
      </div>
      <div class="filtros-lista" id="filtros-lista"></div>
    </aside>

    <div class="tabela-coluna">
      <div class="table-wrap">
        <table id="tabela">
          <thead><tr id="cabecalho"></tr></thead>
          <tbody id="corpo"></tbody>
        </table>
        <div class="empty-state" id="vazio" style="display:none;">Nenhum ativo encontrado para esse filtro.</div>
      </div>
      <nav class="paginacao" id="paginacao"></nav>
    </div>
  </div>

  <script type="application/json" id="dashboard-data">{payload_json}</script>
  <script src="../static/js/scripts.js"></script>
</body>
</html>
"""


# CSS embutido diretamente no script -- rodar este arquivo CRIA o style.css,
# não depende de nenhum arquivo externo de origem.
CSS_CONTENT = '''/* Tema baseado no dashboard-modern-theme.css enviado (slate escuro + azul,
   sem verde). As peças que não estavam no arquivo original (marquee,
   painel de filtros, células numéricas, responsivo) foram completadas
   seguindo as mesmas convenções (raio 18px/999px, hairlines sutis,
   destaque em --primary). */

:root {
  --bg: #0c0f18;
  --bg-elevated: #0e1015;
  --bg-card: #1b2129;
  --bg-row-alt: #151b22;
  --hairline: #2a3443;
  --hairline-bright: #374356;

  --text: #f8fafc;
  --text-dim: #cbd5e1;
  --text-faint: #94a3b8;

  --primary: #3b82f6;
  --primary-soft: rgba(59, 130, 246, .12);
  --primary-dim: #2563eb;

  --positive: #60a5fa;
  --red: #ef4444;

  --radius: 18px;
  --shadow: 0 8px 30px rgba(0, 0, 0, .25);

  --font-ui: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'IBM Plex Mono', ui-monospace, monospace;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-ui);
  font-size: 14px;
  -webkit-font-smoothing: antialiased;
}

::selection { background: var(--primary); color: #fff; }

/* ---------- topbar ---------- */

header.topbar {
  background: var(--bg-card);
  border-bottom: 1px solid var(--hairline);
  padding: 24px 32px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 14px;
}

header.topbar h1 {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.01em;
  margin: 0 0 4px;
  color: var(--text);
}

header.topbar .meta {
  font-size: 11.5px;
  color: var(--text-faint);
  font-family: var(--font-mono);
}

.btn-filtros {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: var(--primary-soft);
  color: var(--primary);
  border: none;
  border-radius: 999px;
  padding: 11px 18px;
  font-family: var(--font-ui);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: .2s;
}

.btn-filtros:hover { background: var(--primary-dim); color: #fff; }
.btn-filtros .ico { display: inline-flex; align-items: center; opacity: 0.85; }

.btn-filtros .badge {
  background: var(--primary);
  color: #fff;
  font-size: 10.5px;
  font-weight: 700;
  border-radius: 999px;
  min-width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 5px;
}

/* ---------- marquee ---------- */

.marquee-wrap {
  background: var(--bg-card);
  border-bottom: 1px solid var(--hairline);
  overflow: hidden;
  white-space: nowrap;
  padding: 8px 0;
}

.marquee-track {
  display: inline-block;
  padding-left: 100%;
  animation: marquee 42s linear infinite;
  font-family: var(--font-mono);
}

.marquee-wrap:hover .marquee-track { animation-play-state: paused; }

@keyframes marquee {
  0% { transform: translateX(0); }
  100% { transform: translateX(-100%); }
}

.marquee-item { display: inline-block; padding: 0 22px; font-size: 12px; }
.marquee-item .tk { color: var(--text); font-weight: 600; margin-right: 6px; }
.marquee-item .up { color: var(--positive); }
.marquee-item .down { color: var(--red); }

/* ---------- tabs ---------- */

nav.tabs {
  display: flex;
  padding: 16px 32px 0;
  gap: 6px;
  overflow-x: auto;
}

nav.tabs button {
  background: none;
  border: 1px solid transparent;
  border-radius: 999px;
  color: var(--text-faint);
  font-family: var(--font-ui);
  font-size: 12.5px;
  font-weight: 500;
  padding: 8px 16px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s ease;
}

nav.tabs button:hover { background: var(--bg-row-alt); color: var(--text); }

nav.tabs button.active {
  background: var(--primary);
  color: #fff;
  font-weight: 600;
}

/* ---------- controls ---------- */

.controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 32px 12px;
  flex-wrap: wrap;
}

.controls input[type="text"] {
  background: var(--bg-elevated);
  border: 1px solid var(--hairline);
  color: var(--text);
  border-radius: 12px;
  font-family: var(--font-ui);
  font-size: 12.5px;
  padding: 10px 14px;
  width: 300px;
  max-width: 100%;
  outline: none;
}

.controls input[type="text"]::placeholder { color: var(--text-faint); }

.controls input[type="text"]:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 4px rgba(59, 130, 246, .15);
  outline: none;
}

.controls .count {
  color: var(--text-faint);
  font-size: 11.5px;
  font-family: var(--font-mono);
}

.controls-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.pagina-tamanho-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11.5px;
  color: var(--text-faint);
}

.pagina-tamanho-label select {
  background: var(--bg-elevated);
  border: 1px solid var(--hairline);
  color: var(--text);
  border-radius: 8px;
  font-family: var(--font-ui);
  font-size: 12px;
  padding: 6px 10px;
  outline: none;
  cursor: pointer;
}

.pagina-tamanho-label select:focus { border-color: var(--primary); }

.paginacao {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 16px 0 0;
}

.paginacao button {
  background: var(--bg-elevated);
  border: 1px solid var(--hairline);
  color: var(--text);
  border-radius: 8px;
  font-family: var(--font-ui);
  font-size: 12px;
  padding: 7px 14px;
  cursor: pointer;
  transition: .15s;
}

.paginacao button:hover:not(:disabled) { border-color: var(--primary); color: var(--primary); }
.paginacao button:disabled { opacity: 0.35; cursor: default; }

.paginacao .pagina-info {
  font-size: 11.5px;
  color: var(--text-faint);
  font-family: var(--font-mono);
}

/* ---------- layout: painel de filtros + tabela ---------- */

.layout {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  padding: 0 32px 40px;
}

.tabela-coluna {
  flex: 1;
  min-width: 0;
}

.filtros-painel {
  background: var(--bg-card);
  border: 1px solid var(--hairline);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  flex: 0 0 260px;
  overflow: hidden;
  position: sticky;
  top: 16px;
}

.filtros-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  border-bottom: 1px solid var(--hairline);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.filtros-header button {
  background: none;
  border: none;
  color: var(--primary);
  font-family: var(--font-ui);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  text-transform: none;
  letter-spacing: normal;
}

.filtros-header button:hover { color: var(--primary-dim); }

.filtros-lista {
  max-height: 70vh;
  overflow-y: auto;
  padding: 6px 14px 14px;
}

.filtro-linha {
  padding: 9px 0;
  border-bottom: 1px solid var(--hairline);
}

.filtro-linha:last-child { border-bottom: none; }

.filtro-linha label {
  display: block;
  font-size: 11.5px;
  color: var(--text-dim);
  margin-bottom: 6px;
}

.filtro-inputs { display: flex; gap: 6px; }

.filtro-inputs input {
  width: 0;
  flex: 1;
  background: var(--bg-elevated);
  border: 1px solid var(--hairline);
  color: var(--text);
  border-radius: 8px;
  font-family: var(--font-mono);
  font-size: 11.5px;
  padding: 6px 8px;
  outline: none;
}

.filtro-inputs input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, .15);
  outline: none;
}

.filtro-inputs input::-webkit-outer-spin-button,
.filtro-inputs input::-webkit-inner-spin-button { opacity: 0.4; }

/* ---------- tabela ---------- */

.table-wrap {
  background: var(--bg-card);
  border: 1px solid var(--hairline);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  flex: 1;
  min-width: 0;
  overflow-x: auto;
}

table { border-collapse: collapse; width: 100%; min-width: 720px; }

thead th {
  position: sticky;
  top: 0;
  background: #131821;
  text-align: left;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-faint);
  padding: 12px 16px;
  border-bottom: 1px solid var(--hairline);
  cursor: pointer;
  white-space: nowrap;
  user-select: none;
  transition: color 0.15s ease;
}

thead th:first-child { border-top-left-radius: var(--radius); }
thead th:hover { color: var(--primary); }
thead th.sorted { color: var(--primary); }
thead th.col-fixa { position: sticky; left: 0; background: #131821; z-index: 2; min-width: 92px; }
thead th .arrow { font-size: 9px; margin-left: 4px; opacity: 0.7; }

tbody td {
  padding: 10px 16px;
  border-bottom: 1px solid var(--hairline);
  white-space: nowrap;
  font-size: 13px;
}

tbody td.num { font-family: var(--font-mono); text-align: right; font-variant-numeric: tabular-nums; }
tbody td.ticker { font-family: var(--font-mono); color: var(--primary); font-weight: 600; }
tbody td.col-fixa { position: sticky; left: 0; z-index: 1; min-width: 92px; }
tbody td.nome {
  color: var(--text-dim);
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
}

tbody tr:nth-child(even) { background: var(--bg-row-alt); }
tbody tr:nth-child(even) td.col-fixa { background: var(--bg-row-alt); }
tbody tr:nth-child(odd) td.col-fixa { background: var(--bg-card); }
tbody tr:hover { background: var(--primary-soft); }
tbody tr:hover td.col-fixa { background: #182230; }

.pos { color: var(--positive); }
.neg { color: var(--red); }

.empty-state {
  padding: 60px 24px;
  text-align: center;
  color: var(--text-faint);
  font-size: 12.5px;
}

/* ---------- responsivo ---------- */

@media (max-width: 900px) {
  .layout { flex-direction: column; }
  .filtros-painel { position: static; width: 100%; flex: none; }
  .filtros-lista { max-height: 320px; }
  header.topbar { padding: 16px 18px; }
  nav.tabs, .controls, .layout { padding-left: 18px; padding-right: 18px; }
}
'''


def escrever_css():
    """Escreve o CSS embutido acima em static/css/style.css."""
    destino = ROOT / "static" / "css" / "style.css"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(CSS_CONTENT, encoding="utf-8")
    print(f"CSS gerado: {destino}")


def copiar_js():
    """
    O JS ainda vem de scripts/assets/scripts.js (copiado, não embutido) --
    é puro comportamento/lógica, não muda com tema visual, então não precisa
    ser regerado a cada ajuste de cor.
    """
    origem_js = ASSETS_DIR / "scripts.js"
    destino_js = ROOT / "static" / "js" / "scripts.js"

    if not origem_js.exists():
        print(f"[AVISO] Não encontrei {origem_js}. Coloque scripts.js lá antes de rodar de novo.")
        return

    destino_js.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origem_js, destino_js)
    print(f"JS copiado: {destino_js}")


def main():
    escrever_css()
    copiar_js()

    dados, metadata = carregar_dados()
    total = sum(len(v) for v in dados.values())
    if total == 0:
        print("[AVISO] Nenhum dado encontrado em ./data/. Rode coletar_dados.py primeiro.")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(montar_html(dados, metadata), encoding="utf-8")
    print(f"Dashboard gerado: {OUTPUT_FILE.resolve()}")
    print(f"Total de ativos embutidos: {total}")


if __name__ == "__main__":
    main()
