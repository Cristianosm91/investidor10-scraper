"""
Testes de gerar_dashboard_investidor10.py -- cobrem especificamente a
regressão real causada pela correção do scraper: quando o campo do link do
ativo foi renomeado de `href_relativo` para `url_relativa` (ver
investidor10_scraper.py), o dashboard passou a exibir esse campo bruto como
coluna visível na tabela, em vez de escondê-lo como sempre fez com o nome
antigo.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gerar_dashboard_investidor10 as dash


def test_url_relativa_fica_oculta_do_schema():
    dados = {
        "acoes": [
            {
                "ticker": "PETR4",
                "nome": "Petrobras",
                "url_relativa": "/acoes/petr4/",
                "variation_12_months": "65,59%",
            }
        ]
    }
    schema = dash.calcular_schema(dados)
    chaves = {col["chave"] for col in schema["acoes"]}
    assert "url_relativa" not in chaves
    assert "href_relativo" not in chaves  # nome antigo -- compatibilidade
    assert "ticker" in chaves
    assert "variation_12_months" in chaves


def test_labels_conhecidos_ficam_em_portugues():
    assert dash.formatar_label("variation_12_months") == "Variação 12M"
    assert dash.formatar_label("p_vp") == "P/VP"
    assert dash.formatar_label("net_worth") == "Patrimônio Líquido"


def test_chave_desconhecida_cai_no_fallback_titulo():
    # campo novo que o site venha a adicionar no futuro, sem mapeamento
    # explícito em LABELS -- não deve quebrar, só formata de forma razoável.
    assert dash.formatar_label("algum_campo_novo") == "Algum Campo Novo"
