# -*- coding: utf-8 -*-
"""
Atualiza todos os dados do Hub de Captação em sequência.
Execute: python3 scripts/atualizar_tudo.py

AUTOMÁTICO (roda aqui sem dependências externas):
  - importar_rouanet.py    → coleta da API SALIC (Rouanet)
  - importar_empresas.py   → lê CSV base do repositório
  - coletar_editais.py     → coleta RSS + portais
  - matching_rouanet.py    → matches Rouanet × empresas
  - matching_editais.py    → matches projetos × editais

MANUAL (Diego roda na sua máquina com a planilha do Ministério):
  python3 scripts/importar_ministerio_esporte.py data/projetos-ministerio-esporte.xlsx
  python3 scripts/matching.py
  git add data/projetos_reais_tratados.csv data/match_inteligente.csv
  git commit -m "data: projetos esporte atualizados"
  git push origin main
  curl -X POST https://hub-captacao.onrender.com/api/reload
"""
import subprocess, sys, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

passos_automaticos = [
    ('Importando projetos Lei Rouanet (API SALIC)...',  'importar_rouanet.py'),
    ('Importando empresas patrocinadoras...',            'importar_empresas.py'),
    ('Coletando editais e oportunidades...',             'coletar_editais.py'),
    ('Calculando matching Rouanet...',                   'matching_rouanet.py'),
    ('Calculando matching Editais...',                   'matching_editais.py'),
]

passos = passos_automaticos

print('══════════════════════════════════════════')
print('  HUB DE CAPTAÇÃO — Atualização Completa')
print('══════════════════════════════════════════')

for descricao, script in passos:
    print(f'\n▶ {descricao}')
    resultado = subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, script)],
        capture_output=False
    )
    if resultado.returncode != 0:
        print(f'  [AVISO] {script} finalizou com código {resultado.returncode} — continuando...')

print('\n══════════════════════════════════════════')
print('  Atualização concluída!')
print('  Chame POST /api/reload para recarregar o banco.')
print('══════════════════════════════════════════')

if not os.path.exists(os.path.join(BASE_DIR, '..', 'data', 'projetos-ministerio-esporte.xlsx')):
    print()
    print('--- ATENÇÃO — Dados do Esporte ---------------------------------')
    print('Para atualizar projetos LIE (Esporte), rode na sua máquina:')
    print()
    print('  python3 scripts/importar_ministerio_esporte.py /caminho/planilha.xlsx')
    print('  python3 scripts/matching.py')
    print('  git add data/projetos_reais_tratados.csv data/match_inteligente.csv')
    print('  git commit -m "data: projetos esporte atualizados"')
    print('  git push origin main')
    print('  curl -X POST https://hub-captacao.onrender.com/api/reload')
    print('----------------------------------------------------------------')
