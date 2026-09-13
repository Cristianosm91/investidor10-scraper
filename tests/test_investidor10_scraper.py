"""
Testes do módulo investidor10_scraper.py.

Cobrem justamente a regressão real que motivou a correção:
- a rota redirecionar (HTTP 302 seguido pelo `requests`) para fora da
  categoria pedida (ex: pra home) precisa ser detectada como falha, nunca
  como coleta válida;
- a home (com poucos ativos em destaque) não pode ser parseada como se
  fosse a listagem completa;
- o parser precisa encontrar a tabela real e parar a paginação de forma
  correta, sem tratar dados parciais como sucesso.
"""

from pathlib import Path

import pytest

import investidor10_scraper as scraper
from investidor10_scraper import curl_requests

FIXTURES = Path(__file__).parent / "fixtures"


def ler_fixture(nome: str) -> str:
    return (FIXTURES / nome).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# url_pertence_a_categoria
# --------------------------------------------------------------------------

def test_url_pertence_a_categoria_aceita_url_da_propria_categoria():
    assert scraper.url_pertence_a_categoria(
        "https://investidor10.com.br/fiis/?page=2", "fiis"
    )
    assert scraper.url_pertence_a_categoria(
        "https://investidor10.com.br/fiis", "fiis"
    )


def test_url_pertence_a_categoria_rejeita_home():
    assert not scraper.url_pertence_a_categoria(
        "https://investidor10.com.br/", "fiis"
    )


def test_url_pertence_a_categoria_rejeita_outra_categoria():
    assert not scraper.url_pertence_a_categoria(
        "https://investidor10.com.br/acoes/", "fiis"
    )


# --------------------------------------------------------------------------
# extrair_ativos
# --------------------------------------------------------------------------

def test_extrair_ativos_tabela_valida_extrai_todos_os_campos():
    html = ler_fixture("fiis_pagina_valida.html")
    ativos = scraper.extrair_ativos(html, "fiis")

    assert ativos is not None
    assert len(ativos) == 2

    kncr = ativos[0]
    assert kncr["ticker"] == "KNCR11"
    assert kncr["nome"] == "Kinea Rendimentos Imobiliários Fundos"
    assert kncr["url_relativa"] == "/fiis/kncr11/"
    assert kncr["net_worth"] == "10,98 B"
    assert kncr["p_vp"] == "1,04"
    assert kncr["dividend_yield_last_12_months"] == "13,23%"

    assert ativos[1]["ticker"] == "HGLG11"


def test_extrair_ativos_nao_confunde_menu_com_tabela():
    """O menu de navegação também tem <a href="/fiis/...">; o parser deve
    olhar só pra dentro de <table>, não pra qualquer <a> da página."""
    html = ler_fixture("fiis_pagina_valida.html")
    ativos = scraper.extrair_ativos(html, "fiis")
    tickers = {a["ticker"] for a in ativos}
    # a âncora do menu aponta pro mesmo KNCR11, então isso por si só não prova
    # o comportamento -- o que importa é não haver duplicata nem contagem "3"
    assert len(ativos) == 2
    assert tickers == {"KNCR11", "HGLG11"}


def test_extrair_ativos_retorna_none_quando_tabela_nao_encontrada():
    """A home redirecionada não deve ser confundida com uma listagem válida:
    sem <table> reconhecível, a função deve sinalizar isso com None (não []),
    para o chamador diferenciar de 'fim legítimo da paginação'."""
    html = ler_fixture("homepage_redirecionada.html")
    assert scraper.extrair_ativos(html, "fiis") is None


def test_extrair_ativos_tabela_vazia_retorna_lista_vazia():
    html = ler_fixture("fiis_pagina_sem_novos.html")
    ativos = scraper.extrair_ativos(html, "fiis")
    assert ativos == []


# --------------------------------------------------------------------------
# buscar_pagina -- detecção de redirecionamento e retry
# --------------------------------------------------------------------------

class _RespostaFalsa:
    def __init__(self, url, status_code=200, text="", headers=None, history=None):
        self.url = url
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.history = history or []

    def raise_for_status(self):
        if self.status_code >= 400:
            raise curl_requests.exceptions.HTTPError(f"HTTP {self.status_code}")


def test_buscar_pagina_sucesso_sem_redirecionamento(monkeypatch):
    resposta = _RespostaFalsa(url="https://investidor10.com.br/fiis/?page=1", text="ok")
    monkeypatch.setattr(scraper.SESSION, "get", lambda *a, **k: resposta)

    html = scraper.buscar_pagina(scraper.CATEGORIAS["fiis"], "fiis", page=1)
    assert html == "ok"


def test_buscar_pagina_levanta_erro_apos_esgotar_tentativas_em_redirecionamento(monkeypatch):
    """Simula exatamente o bug relatado: toda tentativa acaba redirecionada
    pra home. Depois de esgotar as tentativas, deve levantar
    RedirecionadoParaHomeError -- nunca devolver o HTML da home como se
    fosse sucesso."""
    resposta_home = _RespostaFalsa(
        url="https://investidor10.com.br/",
        status_code=200,
        text="<html>home</html>",
        history=[_RespostaFalsa(url=scraper.CATEGORIAS["fiis"], status_code=302)],
    )
    monkeypatch.setattr(scraper.SESSION, "get", lambda *a, **k: resposta_home)
    monkeypatch.setattr(scraper.time, "sleep", lambda *_a, **_k: None)  # não esperar no teste

    with pytest.raises(scraper.RedirecionadoParaHomeError):
        scraper.buscar_pagina(scraper.CATEGORIAS["fiis"], "fiis", page=1)


def test_buscar_pagina_recupera_apos_redirecionamento_transitorio(monkeypatch):
    """Se a 1ª tentativa cai na home mas a 2ª funciona, o retry deve se
    recuperar e devolver o HTML correto (sem propagar erro)."""
    chamadas = {"n": 0}

    def get_fake(*_a, **_k):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            return _RespostaFalsa(url="https://investidor10.com.br/", text="home")
        return _RespostaFalsa(url="https://investidor10.com.br/fiis/?page=1", text="listagem real")

    monkeypatch.setattr(scraper.SESSION, "get", get_fake)
    monkeypatch.setattr(scraper.time, "sleep", lambda *_a, **_k: None)

    html = scraper.buscar_pagina(scraper.CATEGORIAS["fiis"], "fiis", page=1)
    assert html == "listagem real"
    assert chamadas["n"] == 2


# --------------------------------------------------------------------------
# coletar_categoria -- paginação e "sem dados parciais tratados como sucesso"
# --------------------------------------------------------------------------

def test_coletar_categoria_para_a_paginacao_ao_nao_achar_tickers_novos(monkeypatch):
    paginas = {
        1: ler_fixture("fiis_pagina_valida.html"),
        2: ler_fixture("fiis_pagina_valida.html"),  # mesmos tickers -> duplicata
    }
    chamadas = []

    def buscar_fake(_url, _categoria, page):
        chamadas.append(page)
        return paginas[page]

    monkeypatch.setattr(scraper, "buscar_pagina", buscar_fake)
    monkeypatch.setattr(scraper, "_aquecer_sessao", lambda: None)
    monkeypatch.setattr(scraper.time, "sleep", lambda *_a, **_k: None)

    resultado = scraper.coletar_categoria("fiis")

    assert len(resultado) == 2  # não duplica entre páginas
    assert chamadas == [1, 2]  # parou na página 2 (sem tickers novos), não foi até 200


def test_coletar_categoria_levanta_erro_se_pagina_1_nao_tem_tabela(monkeypatch):
    """Reproduz o cenário relatado: a página 1 vem redirecionada/sem a
    estrutura esperada. Isso deve ser um erro explícito -- nunca um
    resultado vazio silenciosamente tratado como 'coleta concluída'."""

    def buscar_fake(_url, _categoria, page):
        return ler_fixture("homepage_redirecionada.html")

    monkeypatch.setattr(scraper, "buscar_pagina", buscar_fake)
    monkeypatch.setattr(scraper, "_aquecer_sessao", lambda: None)

    with pytest.raises(ValueError):
        scraper.coletar_categoria("fiis")


def test_coletar_categoria_nao_trata_ausencia_de_tabela_na_pagina_2_como_erro(monkeypatch):
    """Página 1 válida, página 2 sem tabela (ex: fim real da paginação) --
    isso é um fim normal, não deve levantar exceção."""
    paginas = {
        1: ler_fixture("fiis_pagina_valida.html"),
        2: ler_fixture("homepage_redirecionada.html"),
    }

    def buscar_fake(_url, _categoria, page):
        return paginas[page]

    monkeypatch.setattr(scraper, "buscar_pagina", buscar_fake)
    monkeypatch.setattr(scraper, "_aquecer_sessao", lambda: None)
    monkeypatch.setattr(scraper.time, "sleep", lambda *_a, **_k: None)

    resultado = scraper.coletar_categoria("fiis")
    assert len(resultado) == 2
