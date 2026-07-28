# Investidor10 — Extração de Dados

## 1. Visão geral
Este projeto coleta dados de ativos do site [Investidor10](https://investidor10.com.br)
(ações, FIIs, stocks, BDRs e ETFs) a partir da rota interna `all2/` e salva os
resultados localmente em arquivos JSON, prontos para análise ou para alimentar
um painel visual.

O núcleo da coleta faz paginação automática (percorre todas as páginas de cada
categoria) e usa retry com backoff exponencial para tolerar instabilidades de
rede e limites de requisição (HTTP 429/5xx).

## 2. Estrutura de pastas
```
investidor10-scraper/
├── src/
│   ├── investidor10_scraper.py        # módulo: busca (com retry) e extração dos ativos
│   ├── coletar_dados.py               # coleta e salva os JSON em data/
│   ├── gerar_dashboard_investidor10.py # gera o dashboard (HTML + CSS + JS)
│   └── diagnostico.py                 # inspeção do HTML bruto (debug de bloqueios)
├── templates/
│   └── dashboard.html                 # painel gerado (não versionado)
├── static/
│   ├── css/style.css                  # gerado pelo script (CSS embutido no .py)
│   └── js/scripts.js                  # gerado pelo script (JS embutido no .py)
├── data/                              # JSON gerados pela coleta (não versionado)
├── requirements.txt
└── .gitignore
```

- `data/` e `templates/dashboard.html` são criados automaticamente e ficam fora
  do controle de versão (ver `.gitignore`).
- Os arquivos em `static/` são **gerados** por `gerar_dashboard_investidor10.py`:
  o CSS e o JS ficam embutidos no próprio script e são escritos ao rodá-lo.

## 3. Requisitos e instalação
- Python 3.10 ou superior (o código usa a sintaxe de tipos `int | None`).
- Dependências principais: `requests`, `beautifulsoup4`, `lxml`.

```bash
pip install -r requirements.txt
```

## 4. Coleta de dados
Execute o script principal a partir da raiz do projeto:

```bash
python src/coletar_dados.py
```

O que acontece:
1. Percorre todas as categorias definidas em `CATEGORIAS`
   (`acoes`, `fiis`, `stocks`, `bdrs`, `etfs`).
2. Para cada categoria, pagina até o fim e remove tickers repetidos.
3. Salva um arquivo por categoria em `data/` (ex.: `data/acoes.json`,
   `data/fiis.json`).
4. Grava também `data/_metadata.json` com data/hora da coleta e o total de
   ativos por categoria (ou o erro, caso alguma categoria falhe).

Parâmetros de comportamento ficam no topo de
`src/investidor10_scraper.py` e podem ser ajustados:

| Constante | Padrão | Função |
|-----------|--------|--------|
| `TIMEOUT` | `15` | timeout (s) de cada requisição |
| `DELAY_ENTRE_REQUESTS` | `2` | pausa (s) entre páginas/categorias |
| `MAX_TENTATIVAS` | `3` | tentativas por requisição antes de falhar |
| `BACKOFF_BASE` | `2` | base (s) do backoff exponencial |
| `MAX_PAGINAS` | `100` | teto de páginas por categoria (salvaguarda) |

## 5. Diagnóstico
Se a coleta vier vazia ou o site estiver bloqueando, rode o diagnóstico para
inspecionar a resposta crua:

```bash
python src/diagnostico.py
```

Ele imprime status HTTP, tamanho da resposta, procura pistas de bloqueio
(Cloudflare, captcha etc.), verifica se tickers conhecidos aparecem no HTML e
salva o conteúdo completo em `diagnostico_fiis.html` para inspeção manual.

## 6. Dashboard
Depois da coleta, gere o painel a partir dos JSON de `data/`:

```bash
python src/gerar_dashboard_investidor10.py
```

O script:
1. Escreve `static/css/style.css` (CSS embutido no próprio `.py`).
2. Escreve `static/js/scripts.js` (JS embutido no próprio `.py`).
3. Lê os JSON de `data/`, infere as colunas de cada categoria e gera
   `templates/dashboard.html` com os dados embutidos.

Em seguida, abra o painel no navegador:

```bash
# Windows
start templates/dashboard.html
```

O dashboard permite navegar entre categorias em abas, buscar por ticker/nome,
ordenar por qualquer coluna, ajustar o tamanho da página e filtrar por
indicadores no painel lateral. Se rodar sem dados em `data/`, o HTML é gerado
vazio — rode `coletar_dados.py` primeiro.

## 7. Observações
- A rota `all2/` é interna do site e pode mudar sem aviso; se a extração parar
  de funcionar, comece pelo `diagnostico.py`.
- Respeite o site: mantenha o `DELAY_ENTRE_REQUESTS` e evite execuções em
  paralelo contra o mesmo alvo.
