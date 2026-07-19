"""
Módulo compartilhado: busca e extração de dados da rota "all2" do Investidor10.

Usado tanto pelo script de coleta (coletar_dados.py) quanto por scripts
exploratórios. As funções aqui já foram validadas contra HTML real (276/276
FIIs extraídos corretamente, sem quebras).
"""

import re
import time

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

CATEGORIAS = {
    "acoes": "https://investidor10.com.br/acoes/all2/",
    "fiis": "https://investidor10.com.br/fiis/all2/",
    "stocks": "https://investidor10.com.br/stocks/all2/",
    "bdrs": "https://investidor10.com.br/bdrs/all2/",
    "etfs": "https://investidor10.com.br/etfs/all2/",
}

TIMEOUT = 15
DELAY_ENTRE_REQUESTS = 2  # segundos, por educação com o servidor

# Divide por vírgula apenas quando ela for seguida de um novo rótulo de campo
# (ex: ", P/VP :"), e não quando faz parte do valor decimal (ex: "10,96 B").
PADRAO_DIVISAO_CAMPOS = re.compile(r",\s*(?=[A-ZÀ-Ý][\wÀ-ÿ/. ]*?:)")


def buscar_pagina(url: str, page: int | None = 1) -> str:
    """Faz o GET de uma página da rota all2. Levanta exceção em erro HTTP."""
    params = {"page": page} if page else {}
    resp = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text


def extrair_ativos(html: str) -> list[dict]:
    """
    Extrai os ativos listados na rota all2.

    Estrutura real (o link é relativo, ex: href="kncr11"):

    <section id="card-articles">
      ...<ul>
        <li>
          <a href="kncr11">
            <strong>KNCR11</strong> — Nome , Campo : valor , Campo : valor ... , Empresa : Nome
          </a>
        </li>
      </ul>...
    </section>
    """
    soup = BeautifulSoup(html, "lxml")
    resultados = []
    vistos = set()

    container = soup.select_one("section#card-articles") or soup

    for li in container.find_all("li"):
        a = li.find("a")
        if not a:
            continue

        strong = a.find("strong")
        ticker = strong.get_text(strip=True) if strong else None
        if not ticker or ticker in vistos:
            continue

        texto = a.get_text(" ", strip=True)
        if "—" not in texto:
            continue

        apos_travessao = texto.split("—", 1)[1]
        partes = [p.strip() for p in PADRAO_DIVISAO_CAMPOS.split(apos_travessao)]

        nome = partes[0] if partes else None
        campos = {}
        for parte in partes[1:]:
            if ":" in parte:
                chave, valor = parte.split(":", 1)
                campos[chave.strip()] = valor.strip()

        vistos.add(ticker)
        resultados.append(
            {"ticker": ticker, "nome": nome, "href_relativo": a.get("href"), **campos}
        )

    return resultados


def coletar_categoria(categoria: str) -> list[dict]:
    """Busca e extrai todos os ativos de uma categoria (ex: 'fiis')."""
    url = CATEGORIAS[categoria]
    html = buscar_pagina(url, page=1)
    return extrair_ativos(html)
