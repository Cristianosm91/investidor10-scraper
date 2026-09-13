"""
Teste de integração com um servidor HTTP local (loopback) real -- não é
mock. Isso valida de verdade o comportamento de rede da sessão curl_cffi
(redirecionamento, cookies, parsing sobre uma resposta que trafegou pela
pilha TCP/HTTP de verdade), coisa que os testes com monkeypatch não cobrem.

Não substitui testar contra o Investidor10 real (o ambiente onde este
projeto foi corrigido não tem acesso de rede a investidor10.com.br), mas
prova que a sessão configurada em `investidor10_scraper.SESSION`
(`curl_cffi`, impersonate=chrome) funciona corretamente para: seguir
redirect, expor `resp.url`/`resp.history` do jeito que `buscar_pagina`
espera, e que `coletar_categoria` processa tudo isso ponta a ponta contra
um servidor de verdade.
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import investidor10_scraper as scraper

TABELA_HTML = """
<html><body>
<table>
  <thead><tr><th>Ativos</th><th>Patrimônio Líquido</th></tr></thead>
  <tbody>
    <tr><td><a href="/fiis/kncr11/" title="Kinea Rendimentos">KNCR11 - Kinea Rendimentos KNCR11</a></td><td>10,98 B</td></tr>
    <tr><td><a href="/fiis/hglg11/" title="Patria Log">HGLG11 - Patria Log HGLG11</a></td><td>7,59 B</td></tr>
  </tbody>
</table>
</body></html>
"""

HOME_HTML = "<html><body><p>Home -- mais buscados</p></body></html>"


def _fazer_handler(porta: int):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/fiis/all2"):
                # Reproduz o bug real: redireciona pra home.
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{porta}/")
                self.end_headers()
            elif self.path.startswith("/fiis"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(TABELA_HTML.encode("utf-8"))
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(HOME_HTML.encode("utf-8"))

        def log_message(self, *args):  # silencia log do servidor no pytest
            pass

    return Handler


@pytest.fixture()
def servidor_local():
    servidor = HTTPServer(("127.0.0.1", 0), _fazer_handler(0))
    porta = servidor.server_address[1]
    # recria o handler agora que sabemos a porta real (pra montar a URL de redirect)
    servidor.RequestHandlerClass = _fazer_handler(porta)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{porta}"
    finally:
        servidor.shutdown()
        thread.join(timeout=5)


def test_curl_cffi_segue_redirect_real_e_e_detectado(servidor_local):
    """Bate de verdade (via rede loopback) na rota que redireciona, igual ao
    bug original com all2/, e confere que buscar_pagina detecta e levanta
    RedirecionadoParaHomeError -- usando a sessão curl_cffi real, sem mock."""
    url_redirecionada = f"{servidor_local}/fiis/all2/"

    with pytest.raises(scraper.RedirecionadoParaHomeError):
        scraper.buscar_pagina(url_redirecionada, "fiis", page=1)


def test_curl_cffi_busca_e_parseia_tabela_real(servidor_local):
    """Bate de verdade na rota "boa" e confere que o HTML volta certinho e o
    parser extrai os ativos -- valida a sessão curl_cffi ponta a ponta
    (rede real + parsing), sem depender do site de produção."""
    url = f"{servidor_local}/fiis/"

    html = scraper.buscar_pagina(url, "fiis", page=1)
    ativos = scraper.extrair_ativos(html, "fiis")

    assert ativos is not None
    assert [a["ticker"] for a in ativos] == ["KNCR11", "HGLG11"]


def test_coletar_categoria_ponta_a_ponta_contra_servidor_real(servidor_local, monkeypatch):
    """coletar_categoria completo (rede real via curl_cffi) contra o servidor
    local: página 1 tem 2 ativos, todas as páginas seguintes repetem os
    mesmos 2 -> paginação para sozinha, sem erro."""
    categoria_temp = dict(scraper.CATEGORIAS)
    categoria_temp["fiis"] = f"{servidor_local}/fiis/"
    monkeypatch.setattr(scraper, "CATEGORIAS", categoria_temp)
    monkeypatch.setattr(scraper, "_aquecer_sessao", lambda: None)
    monkeypatch.setattr(scraper.time, "sleep", lambda *_a, **_k: None)

    resultado = scraper.coletar_categoria("fiis")
    assert len(resultado) == 2
    assert {a["ticker"] for a in resultado} == {"KNCR11", "HGLG11"}
