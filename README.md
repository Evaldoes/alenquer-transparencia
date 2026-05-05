# Alenquer Transparência

Monitor de fiscalização pública para o município de Alenquer/PA. Cruza dados do Portal da Transparência Federal com fontes abertas (PNCP, CNPJ, CEIS/CNEP, TSE, CNJ, IBGE) e exibe um dashboard web local.

## Funcionalidades

- **Benefícios sociais** — Bolsa Família, BPC e Seguro Defeso (12 meses)
- **Convênios federais** — execução por ministério, situação e ano
- **Monitor de risco** — score de irregularidade por contrato (CNPJ, sanções, sobrepreço)
- **Copy-paste e semântico** — detecta contratos com texto idêntico ou paráfrases entre empresas
- **PNCP** — contratações públicas mais recentes sem precisar de token
- **TSE** — cruza doadores de campanha com empresas contratadas
- **CNJ** — empresas contratadas com processos de improbidade no Datajud
- **Saúde (SIOPS)** — convênios SUS, BPC e histórico dos últimos 4 anos
- **Benchmark** — compara Alenquer com municípios paraenses de porte similar
- **Emprego** — dados de mercado de trabalho (CAGED/IBGE)
- **Notícias** — feed de notícias sobre Alenquer e transparência no Pará
- **Boletim PDF** — relatório mensal exportável
- **API pública** — endpoints em `/v1/` para jornalistas e ONGs
- **Agendamento** — cron job para rodar o monitor automaticamente

## Pré-requisitos

- Python 3.10+
- Token gratuito do Portal da Transparência: [portaldatransparencia.gov.br/api-de-dados](https://portaldatransparencia.gov.br/api-de-dados)

## Instalação

```bash
git clone https://github.com/seu-usuario/alenquer-transparencia.git
cd alenquer-transparencia

# Copiar e preencher as variáveis de ambiente
cp .env.example .env
# Edite .env e adicione seu PORTAL_TOKEN

# Instalar dependências e subir o dashboard
chmod +x alenquer.sh
./alenquer.sh
```

O menu interativo cuida da criação do virtualenv e instalação das dependências automaticamente.

## Uso rápido

```bash
./alenquer.sh          # menu principal
```

| Opção | Ação |
|-------|------|
| 1 | Configurar token e e-mail |
| 2 | Rodar monitor de risco |
| 3 | Abrir dashboard web (http://localhost:5000) |
| 4 | Atualizar notícias e Diário Oficial |
| 5 | Gerar boletim PDF |
| 6 | Exportar planilha Excel |
| 7 | Comparar municípios vizinhos |

## Estrutura

```
alenquer-transparencia/
├── app.py                  # API FastAPI + servidor do dashboard
├── monitor.py              # Score de risco dos contratos
├── alenquer.sh             # Menu interativo (instalação e operação)
├── requirements.txt
├── .env.example
├── templates/
│   └── index.html          # Dashboard web (single-page)
├── modules/
│   ├── banco.py            # SQLite (histórico, notícias, denúncias)
│   ├── benchmark.py        # Comparação com municípios similares
│   ├── caged.py            # Dados de emprego formal
│   ├── cnj.py              # Processos judiciais (Datajud)
│   ├── copypaste.py        # Detecção de copy-paste entre contratos
│   ├── embeddings.py       # Similaridade semântica (TF-IDF)
│   ├── exportar.py         # CSV e Excel
│   ├── grafo.py            # Rede de vínculos entre empresas
│   ├── municipios.py       # Comparação de municípios
│   ├── noticias.py         # Feed de notícias
│   ├── pdf_report.py       # Geração de boletim PDF
│   ├── pncp.py             # Portal Nacional de Contratações Públicas
│   ├── score_empresa.py    # Histórico de score por empresa
│   ├── siops.py            # Execução orçamentária de saúde
│   ├── tse.py              # Cruzamento TSE × contratos
│   └── api_publica.py      # API pública /v1/
└── dados/                  # Gerado em runtime (banco, PDFs)
```

## API pública

O servidor expõe endpoints abertos em `/v1/`:

| Endpoint | Descrição |
|----------|-----------|
| `GET /v1/` | Documentação |
| `GET /v1/status` | Status da última análise |
| `GET /v1/contratos` | Lista de contratos analisados |
| `GET /v1/contratos/risco` | Contratos de alto/médio risco |
| `GET /v1/empresa/{cnpj}` | Histórico de uma empresa |
| `GET /v1/estatisticas` | Estatísticas gerais |

Rate limit: 60 req/min por IP.

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `PORTAL_TOKEN` | Sim | Token do Portal da Transparência |
| `ANTHROPIC_KEY` | Não | Análise de contratos com IA (Claude) |
| `EMAIL_DESTINO` | Não | E-mail para receber alertas |
| `EMAIL_REMETENTE` | Não | E-mail remetente (Gmail) |
| `EMAIL_SENHA` | Não | Senha de app do Gmail |

## Fontes de dados

- [Portal da Transparência Federal](https://portaldatransparencia.gov.br/)
- [PNCP — Portal Nacional de Contratações Públicas](https://pncp.gov.br/)
- [CEIS/CNEP — Cadastros de sanções](https://portaldatransparencia.gov.br/sancoes)
- [Receita Federal — CNPJ](https://www.gov.br/receitafederal/)
- [TSE — Dados eleitorais](https://dadosabertos.tse.jus.br/)
- [CNJ — Datajud](https://www.cnj.jus.br/sistemas/datajud/)
- [IBGE — Indicadores municipais](https://servicodados.ibge.gov.br/)

## Licença

MIT
