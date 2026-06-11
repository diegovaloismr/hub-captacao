# -*- coding: utf-8 -*-
"""
Atualiza todos os dados do Hub de Captação em sequência.
Execute: python scripts/atualizar_tudo.py
"""
import subprocess
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

passos = [
    ('Atualizando projetos aprovados (Lei de Incentivo ao Esporte + SALIC)...', 'coletar_projetos.py'),
    ('Coletando oportunidades dos portais de noticias...', 'coletar_editais.py'),
    ('Calculando compatibilidade projeto x oportunidade...', 'matching_editais.py'),
    ('Regenerando dashboard...', 'gerar_dashboard.py'),
]

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
        print(f'  [ERRO] {script} falhou com código {resultado.returncode}')
        print('  Interrompendo atualização.')
        sys.exit(1)

print('\n══════════════════════════════════════════')
print('  Atualizacao concluida com sucesso!')
print('  Abra app/dashboard.html para ver os dados atualizados.')
print('══════════════════════════════════════════')

# Lembrete sobre planilha do Ministerio do Esporte
xlsx_path = os.path.join(os.path.dirname(BASE_DIR), 'data', 'projetos-ministerio-esporte.xlsx')
if not os.path.exists(os.path.join(BASE_DIR, '..', 'data', 'projetos-ministerio-esporte.xlsx')):
    print()
    print('--- ATENCAO — Dados dos projetos -----------------------------------')
    print('Para atualizar com a planilha mais recente do Ministerio do Esporte:')
    print()
    print('  python3 scripts/importar_ministerio_esporte.py /caminho/planilha.xlsx')
    print()
    print('Baixe a planilha em:')
    print('  gov.br/esporte -> Lei de Incentivo ao Esporte')
    print('  -> "Projetos aptos a captacao"')
    print('--------------------------------------------------------------------')
