# Investidor10 - Extração de Dados e Dashboard

## 1. Project Overview
Este projeto foi criado para coletar dados de ativos do site Investidor10, organizar essas informações localmente em arquivos JSON e gerar um dashboard interativo em HTML.

O fluxo principal permite extrair informações de diferentes categorias de investimentos, armazenar os resultados em uma pasta dedicada e visualizar os dados em uma interface simples com filtros e ordenação.

## 2. Folder Structure
A estrutura do projeto foi organizada para separar responsabilidades:

- `src/`: contém os scripts Python responsáveis por coleta, diagnóstico e geração do dashboard.
- `templates/`: armazena o arquivo `dashboard.html` gerado para exibição.
- `static/css/`: contém os estilos CSS do dashboard.
- `static/js/`: contém o JavaScript responsável por filtros, ordenação e interação na tabela.
- `data/`: guarda os arquivos JSON produzidos pela coleta; esses arquivos são gerados localmente e não devem ser enviados ao GitHub.
- `.gitignore`: define quais arquivos e pastas devem permanecer fora do controle de versão, como dados gerados, caches Python e arquivos temporários.

## 3. Data Collection Instructions
Siga os passos abaixo para coletar os dados do Investidor10:

1. Acesse a pasta do projeto:
   ```bash
   cd investidor10
   ```
2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
3. Execute o script de coleta:
   ```bash
   python src/coletar_dados.py
   ```
4. Os dados serão salvos em `data/` em arquivos JSON, como `acoes.json`, `fiis.json` e outros.
5. Gere o dashboard a partir dos dados locais:
   ```bash
   python src/gerar_dashboard.py
   ```

Você também pode usar o script de diagnóstico para revisar o processo:
```bash
python src/diagnostico.py
```

## 4. Dashboard Usage
Depois de gerar o dashboard, abra o arquivo `templates/dashboard.html` em um navegador.

O painel foi projetado para:
- exibir colunas com filtros e ordenação;
- permitir busca por ticker, nome ou segmento;
- manter a estrutura separada entre HTML, CSS e JavaScript.

Os arquivos de estilo e lógica estão organizados em `static/css/` e `static/js/`, respectivamente.

## 5. Running the Notebook
Para explorar os dados em análise visual, execute o notebook:

```bash
jupyter notebook src/Valuation.ipynb
```

Se o Jupyter ainda não estiver instalado, use:
```bash
pip install jupyter
```

## 6. Requirements
- Python 3.9 ou superior
- Bibliotecas principais:
  - `requests`
  - `beautifulsoup4`
  - `lxml`

Instalação:
```bash
pip install -r requirements.txt
```

## 7. Best Practices
- Mantenha o dashboard independente dos arquivos temporários de coleta.
- Remova arquivos desnecessários após testes ou experimentos.
- Use um `.gitignore` para evitar versionar dados temporários, caches e arquivos sensíveis.
- Preserve a separação entre HTML, CSS e JavaScript para facilitar manutenção.
