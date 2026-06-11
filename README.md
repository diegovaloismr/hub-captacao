# Hub de Captação — Terminal de Inteligência

Plataforma de inteligência para captação de recursos via **Lei de Incentivo ao Esporte** no Brasil.
Funciona como um "Bloomberg Terminal da Captação", conectando projetos incentivados e patrocinadores.

## Estrutura

```
terminal-captacao/
├── app/
│   └── dashboard.html          # Interface principal (Bloomberg Terminal)
├── data/
│   ├── projetos_reais_tratados.csv   # Base de projetos aprovados
│   ├── empresas_potenciais.csv       # Base de empresas patrocinadoras
│   └── match_inteligente.csv         # Resultados de matching
├── scripts/
│   ├── tratar_dados.py         # Scoring e tratamento de projetos
│   ├── empresas.py             # Gestão da base de empresas
│   ├── matching.py             # Motor de matching inteligente
│   ├── radar.py                # Radar de oportunidades
│   └── gerar_dashboard.py      # Gerador do dashboard HTML
└── requirements.txt
```

## Quickstart

```bash
pip install -r requirements.txt

# Recalcular scores dos projetos
python scripts/tratar_dados.py

# Atualizar scores das empresas
python scripts/empresas.py

# Rodar matching completo (projetos × empresas)
python scripts/matching.py

# Ver oportunidades no radar
python scripts/radar.py

# Gerar/atualizar o dashboard
python scripts/gerar_dashboard.py

# Abrir o dashboard
open app/dashboard.html
```

## Funcionalidades

- **Tabela de Projetos** — filtros avançados por UF, região, modalidade, ano, score e saldo
- **Ranking de Empresas** — ordenável por potencial de investimento, setor e região
- **Radar de Oportunidades** — maiores saldos, encerrando em breve, alta prioridade, momentum
- **Matching Inteligente** — score de compatibilidade empresa×projeto com justificativas
- **Ticker em tempo real** — projetos com maiores saldos rolando no topo

## Módulo de Editais

Cruza projetos com editais abertos de financiamento do terceiro setor.

### Configuração (opcional — Portal da Transparência)

```bash
export PORTAL_TRANSPARENCIA_API_KEY=sua_chave_aqui
# Obter chave gratuita em: https://portaldatransparencia.gov.br/api-de-dados
```

### Executar coleta de editais

```bash
# Atualização em um único comando (recomendado):
python scripts/atualizar_tudo.py

# Ou manualmente, passo a passo:
python scripts/coletar_editais.py       # coleta editais das fontes públicas
python scripts/matching_editais.py      # calcula score projeto × edital
python scripts/gerar_dashboard.py       # regenera o dashboard com os novos dados
```

Consulte [COMO_ATUALIZAR.md](COMO_ATUALIZAR.md) para instruções detalhadas, automação via cron e diagnóstico.

### Fontes de dados

- Observatório do 3º Setor (RSS público)
- Capta.org.br / Prosas (RSS público)
- Portal da Transparência — Convênios (API REST, chave gratuita)
- Editais curados (fallback quando fontes externas estão indisponíveis)

## Arquitetura

Atualmente opera com CSVs locais. Preparado para evoluir para PostgreSQL, APIs externas e aplicação web.
