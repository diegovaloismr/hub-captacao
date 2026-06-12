# -*- coding: utf-8 -*-
"""
Calcula matching entre projetos Rouanet e empresas patrocinadoras.
Prioriza empresas com histórico de doação na Rouanet (total_rouanet > 0).
"""
import pandas as pd, re
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'

def score_match(proj: dict, emp: dict) -> float:
    rouanet = float(emp.get('total_rouanet', 0) or 0)
    if rouanet >= 10_000_000: cult = 1.0
    elif rouanet >= 1_000_000: cult = 0.85
    elif rouanet > 0:          cult = 0.70
    else:                      cult = 0.30

    uf_proj = str(proj.get('uf', '')).strip().upper()
    uf_emp  = str(emp.get('uf_sede', '')).strip().upper()
    geo = 1.0 if (not uf_emp or uf_emp in ('N/D', '') or uf_emp == uf_proj) else 0.5

    saldo = float(proj.get('saldo_disponivel', 0) or 0)
    pot   = float(emp.get('potencial_investimento', 0) or 0)
    if pot <= 0: fin = 0.5
    elif saldo / max(pot, 1) <= 0.3: fin = 1.0
    elif saldo / max(pot, 1) <= 0.6: fin = 0.75
    else: fin = 0.40

    prazo = float(proj.get('score_prioridade', 0.5) or 0.5)

    return round(cult * 0.40 + geo * 0.25 + fin * 0.20 + prazo * 0.15, 4)

def extrair_rouanet(desc):
    m = re.search(r'Rouanet:\s*R\$([0-9,.]+)([MBK]?)', str(desc))
    if not m: return 0.0
    val = float(m.group(1).replace(',', '.'))
    mult = {'M': 1e6, 'B': 1e9, 'K': 1e3}.get(m.group(2), 1)
    return val * mult

def main():
    rouanet_path = DATA_DIR / 'projetos_rouanet.csv'
    if not rouanet_path.exists():
        print('[ERRO] projetos_rouanet.csv não encontrado. Execute importar_rouanet.py primeiro.')
        return

    df_proj = pd.read_csv(rouanet_path).fillna('')
    df_emp  = pd.read_csv(DATA_DIR / 'empresas_potenciais.csv').fillna('')

    if 'total_rouanet' not in df_emp.columns:
        df_emp['total_rouanet'] = df_emp['descricao'].apply(extrair_rouanet)

    print(f'  Calculando {len(df_proj)} projetos × {len(df_emp)} empresas...')

    rows = []
    for _, proj in df_proj.iterrows():
        scores = []
        for _, emp in df_emp.iterrows():
            s = score_match(proj.to_dict(), emp.to_dict())
            if s >= 0.30:
                scores.append({
                    'nome_projeto':      proj['nome_projeto'],
                    'nome_empresa':      emp['nome_empresa'],
                    'score_match':       s,
                    'score_geo':         0,
                    'score_setor':       0,
                    'score_financeiro':  0,
                    'justificativa':     f"Rouanet histórico: R${emp.get('total_rouanet', 0)/1e6:.1f}M",
                    'ranking_projeto':   0,
                    'lei':               'Rouanet',
                })
        scores.sort(key=lambda x: x['score_match'], reverse=True)
        rows.extend(scores[:20])

    df_out = pd.DataFrame(rows)
    df_out.to_csv(DATA_DIR / 'match_rouanet.csv', index=False, encoding='utf-8')
    print(f'[OK] {len(df_out)} matches salvos em match_rouanet.csv')

if __name__ == '__main__':
    main()
