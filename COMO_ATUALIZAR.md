# Como Atualizar os Dados do Hub de Captação

## Configuração Inicial (primeira vez)

### 1. Chaves de API

Copie o arquivo de exemplo e preencha suas chaves:

```bash
cp .env.exemplo .env
```

Edite `.env` com suas chaves:

```
PORTAL_TRANSPARENCIA_API_KEY=sua_chave_aqui
ANTHROPIC_API_KEY=sua_chave_aqui
```

- **Portal da Transparência:** https://portaldatransparencia.gov.br/api-de-dados (gratuita)
- **Anthropic (Claude):** https://console.anthropic.com (necessária para extração IA de notícias)

Você também pode configurar as chaves diretamente no dashboard pela aba **⚙ CONFIG**.

### 2. Instalar dependências

```bash
pip install requests pandas anthropic
sudo apt-get install -y python3-feedparser   # ou: pip install feedparser
```

---

## Atualização Completa (recomendado)

```bash
python scripts/atualizar_tudo.py
```

Executa em sequência:
1. Coleta editais de todas as fontes
2. Recalcula scores de compatibilidade
3. Regenera o dashboard

---

## Atualização Manual (passo a passo)

```bash
python scripts/coletar_editais.py       # ~60 segundos
python scripts/matching_editais.py      # ~10 segundos
python scripts/gerar_dashboard.py       # ~5 segundos
```

---

## Fontes de Editais

| Fonte | Descrição | Chave necessária |
|-------|-----------|-----------------|
| **A — Portal da Transparência** | Convênios e emendas parlamentares (API oficial) | `PORTAL_TRANSPARENCIA_API_KEY` |
| **B — Governo Federal RSS** | gov.br, Esporte, Cultura, MDH, Transferegov | nenhuma |
| **C — Organismos Internacionais** | COI, FIFA, PNUD, UNESCO, UE | nenhuma |
| **D — MROSC / Lei 13.019** | Termos de fomento e colaboração via Portal da Transparência | `PORTAL_TRANSPARENCIA_API_KEY` |
| **E — Portais de Notícias (IA)** | GIFE, Filantropia, Captadores, Sebrae + 14 portais; extração estruturada com Claude Haiku | `ANTHROPIC_API_KEY` |
| **Fallback** | 15 editais curados — ativado apenas quando nenhuma fonte real retorna dados | nenhuma |

### Portais RSS monitorados (Fonte E)
- GIFE, Filantropia.org, Instituto Filantropia, Observatório do 3º Setor
- Captadores.com.br, Sebrae Notícias
- gov.br/esporte, Fundo Nacional do Esporte, Fundo Nacional de Cultura
- Ministério dos Direitos Humanos, Transferegov
- Fundação Lemann, Itaú Social, Unibanco Social, Roberto Marinho, Votorantim, Gerdau

---

## Frequência Recomendada

- **Diária:** ideal para acompanhar novos editais
- **Semanal:** mínimo para projetos ativos

---

## Automatização (opcional)

```bash
crontab -e

# Adicionar (ajuste o caminho):
0 7 * * * cd /caminho/para/terminal-captacao-editais && python scripts/atualizar_tudo.py >> logs/atualizacao.log 2>&1
```

---

## Indicador de dados reais vs demonstração

O dashboard exibe um banner **⚠ DADOS DE DEMONSTRAÇÃO** quando todas as fontes
falharam e o fallback está ativo. O banner desaparece assim que pelo menos 1
edital real for coletado.
