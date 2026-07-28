"""
Gera o dashboard HTML do projeto Investidor10 a partir dos dados coletados
em ./data/ (acoes.json, fiis.json, stocks.json, bdrs.json, etfs.json).

Segue a estrutura de pastas:
    projeto/
      scripts/gerar_dashboard.py   <- este arquivo
      data/*.json
      templates/dashboard.html     <- gerado
      static/css/style.css         <- gerado (embutido neste script)
      static/js/scripts.js         <- gerado (embutido neste script)

Uso:
    python gerar_dashboard.py
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_FILE = ROOT / "templates" / "dashboard.html"

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


JS_CONTENT = r'''const payloadEl = document.getElementById("dashboard-data");
const payload = payloadEl ? JSON.parse(payloadEl.textContent || "{}") : {};
const DADOS = payload.dados || {};
const NOMES_CATEGORIA = payload.nomes || {};
const METADATA = payload.metadata || {};
const SCHEMA = payload.schema || {};

let categoriaAtual = Object.keys(DADOS).find((categoria) => (DADOS[categoria] || []).length > 0) || Object.keys(DADOS)[0] || "";
let ordenacao = { campo: null, direcao: 1 };
let filtrosAtivos = {}; // { campo: { min: number|null, max: number|null } }
let painelAberto = false;
let tamanhoPagina = 50; // 50 | 100 | 150 | 200 | 250 | "todos"
let paginaAtual = 1;

function pareceNumerico(valor) {
  if (valor == null) return false;
  const s = String(valor).trim();
  if (s === "" || s === "-") return false;
  // precisa ser a string INTEIRA nesse formato (nao so conter um digito em algum lugar) --
  // evita falsos positivos tipo "WIZC3" ou "PETR4", que contem digito mas nao sao numeros
  return /^-?\s*(R\$)?\s*\d[\d.,]*\s*%?\s*[BMKbmk]?$/.test(s);
}

function paraNumero(valor) {
  if (valor == null) return NaN;
  let s = String(valor).trim();
  if (s === "-" || s === "") return NaN;

  const negativo = s.trim().startsWith("-");
  s = s.replace(/[R$%\s]/g, "").replace(/^-/, "");

  let multiplicador = 1;
  if (/[Bb]$/.test(s)) {
    multiplicador = 1e9;
    s = s.slice(0, -1);
  } else if (/[Mm]$/.test(s)) {
    multiplicador = 1e6;
    s = s.slice(0, -1);
  } else if (/[Kk]$/.test(s)) {
    multiplicador = 1e3;
    s = s.slice(0, -1);
  }

  if (s.includes(",")) {
    s = s.replace(/\./g, "").replace(",", ".");
  }

  const n = parseFloat(s);
  if (isNaN(n)) return NaN;
  return (negativo ? -Math.abs(n) : n) * multiplicador;
}

function ehCampoVariacao(campo) {
  return /varia[cç][aã]o/i.test(campo);
}

function colunasDaCategoria(categoria) {
  const schemaCategoria = SCHEMA[categoria];
  if (schemaCategoria && schemaCategoria.length) return schemaCategoria;

  // fallback (categoria sem schema pré-calculado): monta a partir dos dados
  const itens = DADOS[categoria] || [];
  const vistas = new Set();
  const colunas = [];
  for (const item of itens) {
    for (const chave of Object.keys(item)) {
      if (vistas.has(chave)) continue;
      vistas.add(chave);
      colunas.push({ chave, label: chave, percentual: false });
    }
  }
  return colunas;
}

function colunasNumericas(categoria) {
  const itens = DADOS[categoria] || [];
  const colunas = colunasDaCategoria(categoria);
  const amostra = itens.slice(0, 60);
  return colunas.filter((col) => amostra.some((item) => pareceNumerico(item[col.chave])));
}

function formatarValorFiltro(valor) {
  if (valor == null || isNaN(valor)) return "";
  return String(Math.round(valor * 100) / 100);
}

function formatarNumeroBR(n, casas) {
  return n.toFixed(casas).replace(".", ",");
}

function formatarCelula(col, valor) {
  if (valor == null || valor === "") return "\u2013";
  const bruto = String(valor);

  // campos de variação (alta/baixa de preço) -- únicos que recebem cor
  if (ehCampoVariacao(col.chave)) {
    const n = paraNumero(bruto);
    if (!isNaN(n)) {
      const classe = n > 0 ? "pos" : n < 0 ? "neg" : "";
      const sinal = n > 0 ? "+" : "";
      return `<span class="${classe}">${sinal}${formatarNumeroBR(n, 2)}%</span>`;
    }
  }

  // campos numéricos marcados como percentuais no schema (ex: DY, ROE, margens) --
  // vêm como número cru da fonte (ex: 12.4) e precisam do sufixo "%", sem cor
  if (col.percentual) {
    const n = paraNumero(bruto);
    if (!isNaN(n)) {
      return `${formatarNumeroBR(n, 2)}%`;
    }
  }

  // campos que já vêm formatados como string com "%" (ex: Investidor10) -- corrige
  // eventuais "%%" duplicados vindos da coleta, sem mexer no restante do valor
  if (bruto.includes("%")) {
    return bruto.replace(/%{2,}/g, "%");
  }

  return bruto;
}

function formatarDataHora(iso) {
  if (!iso) return "desconhecido";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const dataFmt = d.toLocaleDateString("pt-BR");
  const horaFmt = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return `${dataFmt} às ${horaFmt}`;
}

function atualizarMeta() {
  const metaEl = document.querySelector("header.topbar .meta");
  if (!metaEl) return;
  metaEl.textContent = `fonte: dados locais \u00b7 atualizado em ${formatarDataHora(METADATA.coletado_em)}`;
}

function renderizarTabs() {
  const nav = document.getElementById("tabs");
  if (!nav) return;
  nav.innerHTML = "";

  for (const categoria of Object.keys(DADOS)) {
    const btn = document.createElement("button");
    btn.textContent = `${NOMES_CATEGORIA[categoria] || categoria} (${(DADOS[categoria] || []).length})`;
    btn.className = categoria === categoriaAtual ? "active" : "";
    btn.onclick = () => {
      categoriaAtual = categoria;
      ordenacao = { campo: null, direcao: 1 };
      filtrosAtivos = {};
      paginaAtual = 1;
      document.getElementById("busca").value = "";
      renderizarTudo();
    };
    nav.appendChild(btn);
  }
}

function renderizarMarquee() {
  const track = document.getElementById("marquee");
  if (!track) return;

  const campoVariacao = colunasDaCategoria(categoriaAtual).find((c) => ehCampoVariacao(c.chave))?.chave;
  const itens = campoVariacao ? (DADOS[categoriaAtual] || []).filter((item) => pareceNumerico(item[campoVariacao])) : [];
  const ordenados = [...itens].sort((a, b) => Math.abs(paraNumero(b[campoVariacao])) - Math.abs(paraNumero(a[campoVariacao])));
  const destaques = ordenados.slice(0, 14);

  if (destaques.length === 0) {
    track.innerHTML = "";
    return;
  }

  track.innerHTML = destaques.map((item) => {
    const n = paraNumero(item[campoVariacao]);
    const classe = n >= 0 ? "up" : "down";
    const sinal = n >= 0 ? "+" : "";
    return `<span class="marquee-item"><span class="tk">${item.ticker}</span><span class="${classe}">${sinal}${formatarNumeroBR(n, 1)}%</span></span>`;
  }).join("");
}

function renderizarCabecalho(colunas) {
  const tr = document.getElementById("cabecalho");
  if (!tr) return;
  tr.innerHTML = "";

  for (const col of colunas) {
    const th = document.createElement("th");
    const seta = ordenacao.campo === col.chave ? (ordenacao.direcao === 1 ? "\u25b2" : "\u25bc") : "";
    th.innerHTML = `${col.label}<span class="arrow">${seta}</span>`;
    if (ordenacao.campo === col.chave) th.classList.add("sorted");
    // só a primeira coluna (ticker) fica fixa ao rolar horizontalmente --
    // duas colunas fixas na mesma posição causavam sobreposição de texto
    if (col.chave === "ticker") th.classList.add("col-fixa");

    th.onclick = () => {
      if (ordenacao.campo === col.chave) {
        ordenacao.direcao *= -1;
      } else {
        ordenacao = { campo: col.chave, direcao: 1 };
      }
      renderizarTudo();
    };

    tr.appendChild(th);
  }
}

function contarFiltrosAtivos() {
  return Object.values(filtrosAtivos).filter((f) => f && (f.min != null || f.max != null)).length;
}

function renderizarBadgeFiltros() {
  const badge = document.getElementById("badge-filtros");
  if (!badge) return;
  const n = contarFiltrosAtivos();
  badge.textContent = String(n);
  badge.hidden = n === 0;
}

function renderizarPainelFiltros() {
  const lista = document.getElementById("filtros-lista");
  const painel = document.getElementById("filtros-painel");
  if (!lista || !painel) return;

  painel.hidden = !painelAberto;
  if (!painelAberto) return;

  const numericas = colunasNumericas(categoriaAtual);
  lista.innerHTML = "";

  for (const col of numericas) {
    const atual = filtrosAtivos[col.chave] || {};

    const linha = document.createElement("div");
    linha.className = "filtro-linha";

    const label = document.createElement("label");
    label.textContent = col.label;

    const grupo = document.createElement("div");
    grupo.className = "filtro-inputs";

    const inputMin = document.createElement("input");
    inputMin.type = "number";
    inputMin.placeholder = "min";
    inputMin.value = atual.min != null ? formatarValorFiltro(atual.min) : "";

    const inputMax = document.createElement("input");
    inputMax.type = "number";
    inputMax.placeholder = "max";
    inputMax.value = atual.max != null ? formatarValorFiltro(atual.max) : "";

    const aplicar = () => {
      const min = inputMin.value === "" ? null : parseFloat(inputMin.value);
      const max = inputMax.value === "" ? null : parseFloat(inputMax.value);
      if (min == null && max == null) {
        delete filtrosAtivos[col.chave];
      } else {
        filtrosAtivos[col.chave] = { min, max };
      }
      renderizarBadgeFiltros();
      paginaAtual = 1;
      const colunas = colunasDaCategoria(categoriaAtual);
      renderizarLinhas(colunas);
    };

    inputMin.addEventListener("input", aplicar);
    inputMax.addEventListener("input", aplicar);

    grupo.appendChild(inputMin);
    grupo.appendChild(inputMax);
    linha.appendChild(label);
    linha.appendChild(grupo);
    lista.appendChild(linha);
  }
}

function aplicarFiltrosNumericos(itens) {
  const campos = Object.keys(filtrosAtivos);
  if (campos.length === 0) return itens;

  return itens.filter((item) => {
    for (const campo of campos) {
      const filtro = filtrosAtivos[campo];
      if (!filtro) continue;
      const valor = paraNumero(item[campo]);
      if (isNaN(valor)) return false;
      if (filtro.min != null && valor < filtro.min) return false;
      if (filtro.max != null && valor > filtro.max) return false;
    }
    return true;
  });
}

function calcularItensFiltrados() {
  const termo = document.getElementById("busca").value.trim().toLowerCase();
  let itens = [...(DADOS[categoriaAtual] || [])];

  if (termo) {
    itens = itens.filter((item) => Object.values(item).some((valor) => String(valor ?? "").toLowerCase().includes(termo)));
  }

  itens = aplicarFiltrosNumericos(itens);

  if (ordenacao.campo) {
    const campo = ordenacao.campo;
    const amostraNumerica = itens.some((item) => pareceNumerico(item[campo]));

    itens.sort((a, b) => {
      let va = a[campo];
      let vb = b[campo];
      if (amostraNumerica) {
        va = paraNumero(va);
        vb = paraNumero(vb);
        if (isNaN(va)) va = -Infinity;
        if (isNaN(vb)) vb = -Infinity;
        return (va - vb) * ordenacao.direcao;
      }
      return String(va ?? "").localeCompare(String(vb ?? "")) * ordenacao.direcao;
    });
  }

  return itens;
}

function renderizarPaginacao(totalFiltrado, totalPaginas) {
  const nav = document.getElementById("paginacao");
  if (!nav) return;

  if (tamanhoPagina === "todos" || totalPaginas <= 1) {
    nav.innerHTML = "";
    return;
  }

  nav.innerHTML = "";

  const btnAnterior = document.createElement("button");
  btnAnterior.textContent = "Anterior";
  btnAnterior.disabled = paginaAtual <= 1;
  btnAnterior.onclick = () => {
    paginaAtual = Math.max(1, paginaAtual - 1);
    const colunas = colunasDaCategoria(categoriaAtual);
    renderizarLinhas(colunas);
  };

  const info = document.createElement("span");
  info.className = "pagina-info";
  info.textContent = `Página ${paginaAtual} de ${totalPaginas}`;

  const btnProxima = document.createElement("button");
  btnProxima.textContent = "Próxima";
  btnProxima.disabled = paginaAtual >= totalPaginas;
  btnProxima.onclick = () => {
    paginaAtual = Math.min(totalPaginas, paginaAtual + 1);
    const colunas = colunasDaCategoria(categoriaAtual);
    renderizarLinhas(colunas);
  };

  nav.appendChild(btnAnterior);
  nav.appendChild(info);
  nav.appendChild(btnProxima);
}

function renderizarLinhas(colunas) {
  const itens = calcularItensFiltrados();
  const totalFiltrado = itens.length;

  const tamanhoEfetivo = tamanhoPagina === "todos" ? totalFiltrado || 1 : tamanhoPagina;
  const totalPaginas = Math.max(1, Math.ceil(totalFiltrado / tamanhoEfetivo));
  if (paginaAtual > totalPaginas) paginaAtual = totalPaginas;
  if (paginaAtual < 1) paginaAtual = 1;

  const inicio = totalFiltrado === 0 ? 0 : (paginaAtual - 1) * tamanhoEfetivo;
  const fim = Math.min(totalFiltrado, inicio + tamanhoEfetivo);
  const itensPagina = tamanhoPagina === "todos" ? itens : itens.slice(inicio, fim);

  const corpo = document.getElementById("corpo");
  const vazio = document.getElementById("vazio");
  if (!corpo || !vazio) return;
  corpo.innerHTML = "";

  if (itensPagina.length === 0) {
    vazio.style.display = "block";
  } else {
    vazio.style.display = "none";
    const frag = document.createDocumentFragment();
    for (const item of itensPagina) {
      const tr = document.createElement("tr");
      tr.innerHTML = colunas.map((col) => {
        const numerica = pareceNumerico(item[col.chave]) && !ehCampoVariacao(col.chave) && col.chave !== "ticker";
        const classes = [
          col.chave === "ticker" ? "ticker col-fixa" : "",
          (col.chave === "nome" || col.chave === "companyname") ? "nome" : "",
          numerica ? "num" : "",
        ].filter(Boolean).join(" ");
        return `<td class="${classes}">${formatarCelula(col, item[col.chave])}</td>`;
      }).join("");
      frag.appendChild(tr);
    }
    corpo.appendChild(frag);
  }

  const totalCategoria = (DADOS[categoriaAtual] || []).length;
  const contagemEl = document.getElementById("contagem");
  if (contagemEl) {
    if (totalFiltrado === 0) {
      contagemEl.textContent = `0 de ${totalCategoria} ativos`;
    } else if (tamanhoPagina === "todos") {
      contagemEl.textContent = `${totalFiltrado} de ${totalCategoria} ativos`;
    } else {
      contagemEl.textContent = `${inicio + 1}\u2013${fim} de ${totalFiltrado} ativos`;
    }
  }

  renderizarPaginacao(totalFiltrado, totalPaginas);
}

function renderizarTudo() {
  atualizarMeta();
  renderizarTabs();
  renderizarMarquee();
  renderizarBadgeFiltros();
  renderizarPainelFiltros();
  const colunas = colunasDaCategoria(categoriaAtual);
  renderizarCabecalho(colunas);
  renderizarLinhas(colunas);
}

const campoBusca = document.getElementById("busca");
if (campoBusca) {
  campoBusca.addEventListener("input", () => {
    paginaAtual = 1;
    const colunas = colunasDaCategoria(categoriaAtual);
    renderizarLinhas(colunas);
  });
}

const seletorTamanho = document.getElementById("tamanho-pagina");
if (seletorTamanho) {
  seletorTamanho.addEventListener("change", () => {
    tamanhoPagina = seletorTamanho.value === "todos" ? "todos" : parseInt(seletorTamanho.value, 10);
    paginaAtual = 1;
    const colunas = colunasDaCategoria(categoriaAtual);
    renderizarLinhas(colunas);
  });
}

const btnFiltros = document.getElementById("btn-filtros");
if (btnFiltros) {
  btnFiltros.addEventListener("click", () => {
    painelAberto = !painelAberto;
    renderizarPainelFiltros();
  });
}

const btnLimparFiltros = document.getElementById("btn-limpar-filtros");
if (btnLimparFiltros) {
  btnLimparFiltros.addEventListener("click", () => {
    filtrosAtivos = {};
    paginaAtual = 1;
    renderizarBadgeFiltros();
    renderizarPainelFiltros();
    const colunas = colunasDaCategoria(categoriaAtual);
    renderizarLinhas(colunas);
  });
}

renderizarTudo();
'''


def escrever_css():
    """Escreve o CSS embutido acima em static/css/style.css."""
    destino = ROOT / "static" / "css" / "style.css"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(CSS_CONTENT, encoding="utf-8")
    print(f"CSS gerado: {destino}")


def escrever_js():
    """Escreve o JS embutido acima em static/js/scripts.js."""
    destino = ROOT / "static" / "js" / "scripts.js"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(JS_CONTENT, encoding="utf-8")
    print(f"JS gerado: {destino}")


def main():
    escrever_css()
    escrever_js()

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
