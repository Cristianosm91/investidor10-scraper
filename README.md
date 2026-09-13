# Investidor10 — Extração de Dados

## 1. Visão geral
Este projeto coleta dados de ativos do site [Investidor10](https://investidor10.com.br)
(ações, FIIs, stocks, BDRs e ETFs) a partir da listagem pública e paginada de
cada categoria (ex.: `https://investidor10.com.br/fiis/?page=2`) e salva os
resultados localmente em arquivos JSON, prontos para análise ou para alimentar
um painel visual.

O núcleo da coleta faz paginação automática (percorre todas as páginas de cada
categoria) e usa retry com backoff exponencial para tolerar instabilidades de
rede e limites de requisição (HTTP 429/5xx), além de detectar explicitamente
quando a resposta foi redirecionada pra fora da categoria pedida (ver seção 7).

> **Mudança de rota (histórico):** até certo ponto o projeto usava a rota
> interna `/{categoria}/all2/`, que devolvia todos os ativos em uma página só
> (paginada via `?page=`). Essa rota passou a redirecionar (HTTP 302) para a
> home em requisições sem sessão de navegador — provavelmente uma restrição
> nova do site. A home só lista alguns ativos em destaque, então tratar esse
> redirecionamento como coleta válida gerava resultados incompletos e
> silenciosos. O projeto foi migrado para a listagem pública paginada de cada
> categoria (a mesma que aparece pro usuário logado ou não em
> `/fiis/`, `/acoes/`, etc.), que se mostrou estável e sem redirecionamento.
>
> **Mudança de transporte HTTP (histórico):** depois da migração de rota
> acima, a coleta em produção continuou vindo com **0 ativos em todas as
> categorias**, sem erro de redirecionamento e sem status HTTP de erro — a
> resposta vinha 200, na URL certa, mas com a tabela sem nenhuma linha. Isso
> não é uma questão de rota, e sim de **como a requisição é feita**: o site
> aparenta identificar tráfego automatizado pela "assinatura" de TLS/HTTP da
> biblioteca `requests`/`urllib3` (fingerprint JA3), que é bem diferente da de
> um navegador real mesmo enviando os mesmos headers. Por isso o projeto
> passou a usar `curl_cffi`, que faz o handshake TLS/HTTP imitando um Chrome
> de verdade. Ver seção 8 para os detalhes e o que fazer se isso não bastar.

## 2. Estrutura de pastas
```
investidor10-scraper/
├── src/
│   ├── investidor10_scraper.py        # módulo: busca (com retry) e extração dos ativos
│   ├── coletar_dados.py               # coleta e salva os JSON em data/
│   ├── gerar_dashboard_investidor10.py # gera o dashboard (HTML + CSS + JS)
│   └── diagnostico.py                 # inspeção do HTML bruto (debug de bloqueios/redirecionamentos)
├── tests/
│   ├── conftest.py                          # coloca src/ no sys.path para os testes
│   ├── fixtures/                            # HTML de exemplo (página válida, home, tabela vazia)
│   ├── test_investidor10_scraper.py         # testes de busca (mockada), parser e paginação
│   └── test_integracao_http_local.py        # idem, mas contra um servidor HTTP real (loopback)
├── templates/
│   └── dashboard.html                 # painel gerado (não versionado)
├── static/
│   ├── css/style.css                  # gerado pelo script (CSS embutido no .py)
│   └── js/scripts.js                  # gerado pelo script (JS embutido no .py)
├── data/                              # JSON gerados pela coleta (não versionado)
├── requirements.txt
├── requirements-dev.txt               # dependências de teste (pytest)
└── .gitignore
```

- `data/` e `templates/dashboard.html` são criados automaticamente e ficam fora
  do controle de versão (ver `.gitignore`).
- Os arquivos em `static/` são **gerados** por `gerar_dashboard_investidor10.py`:
  o CSS e o JS ficam embutidos no próprio script e são escritos ao rodá-lo.

## 3. Requisitos e instalação
- Python 3.10 ou superior (o código usa a sintaxe de tipos `int | None`).
- Dependências principais: `curl_cffi` (requisições HTTP imitando um
  navegador real — ver seção 8), `beautifulsoup4`, `lxml`.
- Não precisa de navegador/driver instalado à parte (não usa Playwright nem
  Selenium) — `curl_cffi` já vem com o necessário no próprio pacote pip.

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
| `MAX_PAGINAS` | `200` | teto de páginas por categoria (salvaguarda) |

Se `coletar_categoria` não encontrar a tabela de ativos já na primeira página
de uma categoria, ela levanta `ValueError` em vez de devolver uma lista vazia
— isso evita que um bloqueio/redirecionamento silencioso seja registrado como
"0 ativos coletados com sucesso". `coletar_dados.py` já captura esse erro por
categoria (sem abortar as demais) e grava a mensagem em `_metadata.json`.

## 5. Diagnóstico
Se a coleta vier vazia, incompleta ou o site estiver bloqueando/redirecionando,
rode o diagnóstico:

```bash
python src/diagnostico.py            # checa todas as categorias + dump de 'fiis'
python src/diagnostico.py acoes      # dump detalhado de 'acoes'
```

Ele faz uma checagem rápida (status HTTP, URL final, se houve
redirecionamento **e quantos ativos o parser de verdade conseguiu extrair**)
em todas as categorias, além de um dump detalhado de uma categoria: procura
pistas de bloqueio (Cloudflare, captcha etc.), verifica se tickers conhecidos
aparecem no HTML (para FIIs) e salva o conteúdo completo em
`diagnostico_<categoria>.html` para inspeção manual.

**Sinais de alerta:**
- `status=200` + `[ALERTA] saiu da categoria`: a resposta foi redirecionada
  (normalmente para a home) — mesmo problema que já ocorreu com a rota antiga
  `all2/` (ver seção 1).
- `status=200`, URL certa, mas `[ALERTA] tabela encontrada mas com 0 ativos
  extraídos`: a página carregou, mas sem os dados — foi o segundo problema já
  visto em produção (ver seção 8, "Bloqueio por fingerprint").

Em ambos os casos, `coletar_categoria` já trata isso como falha (levanta
`ValueError` se acontecer na página 1), nunca como sucesso parcial.

## 6. Testes
```bash
pip install -r requirements-dev.txt
pytest tests/
```

Dois grupos de teste:
- `test_investidor10_scraper.py`: usa HTML de exemplo (`tests/fixtures/`) e
  *monkeypatch* para isolar lógica pura (parser, decisão de parar a
  paginação, detecção de redirecionamento) sem depender de rede.
- `test_integracao_http_local.py`: sobe um servidor HTTP real em
  `127.0.0.1` (porta aleatória) e faz a sessão `curl_cffi` de verdade
  conversar com ele pela rede — valida que o redirecionamento é seguido e
  detectado, e que `coletar_categoria` funciona ponta a ponta, sem depender
  do site em produção nem de mocks na camada de rede.

Juntos, cobrem: detecção de redirecionamento pra fora da categoria (com e sem
recuperação via retry), parsing da tabela de ativos, parada correta da
paginação e o caso de a página 1 não trazer a tabela esperada (deve levantar
erro, nunca devolver coleta parcial como sucesso).

## 7. Dashboard
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

> **Ajuste de compatibilidade (09/2026):** depois da correção do scraper (ver
> seção 8), os dados passaram a vir com chaves internas em inglês/snake_case
> (`variation_12_months`, `net_worth`, `p_vp` etc.) em vez dos antigos rótulos
> em português (`"Variação 12M"`, `"Patrimônio Líquido"`). Dois pontos do
> gerador de dashboard dependiam do formato antigo e foram ajustados:
> - a coloração azul/vermelho das colunas de variação e a faixa de destaques
>   no topo (`ehCampoVariacao`, em `scripts.js`) reconheciam só `variação`
>   (PT) — agora também reconhecem `variation` (EN);
> - o campo de link do ativo mudou de nome (`href_relativo` →
>   `url_relativa`) e passou a aparecer como coluna visível na tabela por
>   engano — voltou a ficar oculto (`CAMPOS_OCULTOS_EXPLICITOS`).
>
> `LABELS` também ganhou traduções para as chaves mais comuns (`p_vp` →
> "P/VP", `net_worth` → "Patrimônio Líquido" etc.); chaves novas que o site
> venha a introduzir e que não estejam nesse dicionário aparecem formatadas
> automaticamente (`campo_novo` → "Campo Novo"), sem quebrar nada.

## 8. Observações
- A rota de listagem (`/{categoria}/?page=N`) é pública, mas não é uma API
  documentada — pode mudar de estrutura ou de comportamento sem aviso; se a
  extração parar de funcionar, comece pelo `diagnostico.py`.
- **Limitação conhecida:** a listagem paginada por categoria não inclui todos
  os campos que a antiga rota `all2/` trazia — por exemplo, não há "Preço
  Atual" nem os preços-teto de Bazin/Graham. Esses dados só existem na página
  de cada ativo individual (ex.: `/fiis/kncr11/`), que não é visitada por
  este coletor (isso multiplicaria o número de requisições por um fator igual
  ao total de ativos). Se esses campos forem necessários, é preciso um novo
  passo de coleta por ativo, provavelmente com um `DELAY_ENTRE_REQUESTS` maior
  e/ou paralelismo controlado.
- **Bloqueio por fingerprint (histórico, já mitigado):** depois de corrigir a
  rota, a coleta em produção continuou vindo com 0 ativos em todas as
  categorias — HTTP 200, na categoria certa, mas com a tabela sem nenhuma
  linha. A hipótese era um bloqueio baseado em fingerprint de TLS/HTTP (a lib
  `requests`/`urllib3` tem uma assinatura de handshake — JA3 — bem diferente
  de um navegador real, independente do `User-Agent` enviado). Trocamos
  `requests` por [`curl_cffi`](https://github.com/lexiforest/curl_cffi)
  (`impersonate="chrome131"`, configurável em `IMPERSONATE` no topo de
  `investidor10_scraper.py`), com API praticamente idêntica à do `requests`
  (`Session`, `.get()`, `resp.status_code/url/history/headers`) — toda a
  lógica de retry, backoff, aquecimento de sessão e detecção de
  redirecionamento continua igual, só o transporte HTTP mudou.
  - **Confirmado com HTML real de produção:** rodando `diagnostico.py` com
    `curl_cffi`, o HTML deixou de vir vazio — os tickers (ex.: `KNCR11`,
    `HGLG11`, `MXRF11`) passaram a aparecer normalmente no HTML bruto salvo
    em `diagnostico_<categoria>.html`. Ou seja, o bloqueio por fingerprint
    era real e o `curl_cffi` o contorna.
  - **Causa do "0 ativos" restante (já corrigida):** com o HTML de verdade em
    mãos, ficou claro que o problema final não era mais bloqueio, e sim o
    **parser não reconhecer a estrutura real da tabela**. Duas diferenças
    entre o que eu tinha assumido (baseado em conteúdo indexado por
    buscadores) e o HTML real do site:
    1. o link de cada ativo usa **URL absoluta**
       (`href="https://investidor10.com.br/fiis/kncr11/"`), não relativa
       (`/fiis/kncr11/`) — o regex de reconhecimento só aceitava a forma
       relativa;
    2. a tabela real tem `id="rankigns"` (assim mesmo, com esse typo) e cada
       célula de dado tem um atributo `data-name` (ex.: `net_worth`, `p_vp`,
       `dividend_yield_last_12_months`) — mais estável para mapear colunas
       do que a posição/texto do `<thead>` usada antes.
    `extrair_ativos` foi reescrito para aceitar link absoluto ou relativo e
    para montar os campos a partir do `data-name` de cada célula (a coluna do
    ticker usa `data-column="ticker"` em vez de `data-name`, por isso é
    tratada à parte). Os nomes de campo no JSON também mudaram: em vez de
    `"Patrimônio Líquido"`/`"P/VP"`/`"Dividend Yield"` (texto do cabeçalho),
    agora são as chaves internas do site (`net_worth`, `p_vp`,
    `dividend_yield_last_12_months` etc.) — menos "bonitas", porém muito mais
    estáveis a mudanças de idioma/redação do cabeçalho.
  - **Se `curl_cffi` parar de ser suficiente no futuro** (ex.: o site passar
    a exigir de fato execução de JavaScript, ou um desafio interativo tipo
    Cloudflare Turnstile), o próximo degrau é um navegador headless de
    verdade (Playwright ou Selenium). Nesse cenário, a função a substituir
    seria só `buscar_pagina` (trocar `SESSION.get(...)` por `page.goto(...)`
    + `page.content()`) — `extrair_ativos` e o resto da paginação continuariam
    valendo, pois operam sobre o HTML final, não sobre o transporte.
  - Independentemente da técnica usada, respeite o site: mantenha o
    `DELAY_ENTRE_REQUESTS`, evite paralelismo contra o mesmo alvo e não
    aumente a frequência de execuções tentando "forçar" a passagem por um
    bloqueio.
- **Limitação deste ambiente de desenvolvimento:** a correção foi feita sem
  acesso de rede direto a `investidor10.com.br` a partir do ambiente de
  execução de código (sandbox restrita a poucos domínios). A investigação e
  a validação final do parser foram feitas a partir de trechos reais de HTML
  de produção colados manualmente (via `diagnostico.py` rodado no ambiente
  do usuário) — validei o parser contra esses trechos reais e ele extraiu os
  ativos corretamente, mas **não houve uma execução completa de
  `coletar_dados.py`, ponta a ponta, direto contra o site em produção** por
  parte de quem implementou a correção. Rode `python src/diagnostico.py` (e
  depois `python src/coletar_dados.py`) no seu ambiente para confirmar as 5
  categorias.
