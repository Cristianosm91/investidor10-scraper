const payloadEl = document.getElementById("dashboard-data");
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
