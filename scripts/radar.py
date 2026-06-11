# -*- coding: utf-8 -*-
"""
Radar de Oportunidades.

Identifica automaticamente projetos prioritários para prospecção imediata
em quatro categorias: grandes saldos, encerrando em breve, alta prioridade
e momentum positivo.
"""
import pandas as pd
import numpy as np
from datetime import date
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')


def identificar_oportunidades() -> dict:
    df = pd.read_csv(os.path.join(DATA_DIR, 'projetos_reais_tratados.csv'))
    df['data_fim_captacao'] = pd.to_datetime(df['data_fim_captacao'], errors='coerce')
    hoje = pd.Timestamp(date.today())
    df['dias_restantes'] = (df['data_fim_captacao'] - hoje).dt.days
    df['pct_captado'] = (
        df['valor_captado'] / df['valor_aprovado'].replace(0, np.nan)
    ).fillna(0).clip(0, 1)

    cols_base = ['nome_projeto', 'uf', 'modalidade_esportiva', 'saldo_disponivel', 'score_prioridade']

    return {
        'grandes_saldos': df.nlargest(10, 'saldo_disponivel')[cols_base].to_dict('records'),

        'encerrando_breve': (
            df[df['dias_restantes'].between(0, 60)]
            .sort_values('dias_restantes')
            [cols_base + ['dias_restantes']]
            .head(10).to_dict('records')
        ),

        'alta_prioridade': (
            df[df['score_prioridade'] >= 0.70]
            .sort_values('score_prioridade', ascending=False)
            [cols_base]
            .head(10).to_dict('records')
        ),

        'momentum_positivo': (
            df[(df['pct_captado'] > 0.3) & (df['saldo_disponivel'] > 200_000)]
            .sort_values('saldo_disponivel', ascending=False)
            [['nome_projeto', 'uf', 'modalidade_esportiva', 'saldo_disponivel', 'valor_captado', 'pct_captado']]
            .head(10).to_dict('records')
        ),
    }


if __name__ == '__main__':
    oportunidades = identificar_oportunidades()
    for categoria, projetos in oportunidades.items():
        print(f"\n{'─'*60}")
        print(f"  {categoria.upper().replace('_', ' ')}")
        print(f"{'─'*60}")
        for p in projetos:
            saldo = p.get('saldo_disponivel', 0)
            print(f"  {p['nome_projeto'][:45]:<45} | {p['uf']} | R$ {saldo:>12,.0f}")
