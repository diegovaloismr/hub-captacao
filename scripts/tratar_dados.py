# -*- coding: utf-8 -*-
"""
Tratamento e scoring de projetos da Lei de Incentivo ao Esporte.

Score de prioridade (0-1):
  40% saldo disponível para captação (normalizado)
  30% urgência temporal (dias até fim da captação)
  20% momentum de captação (% já captado)
  10% base fixa
"""
import pandas as pd
import numpy as np
from datetime import date
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')


def calcular_score_prioridade(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    max_saldo = df['saldo_disponivel'].max()
    df['_score_saldo'] = df['saldo_disponivel'] / max_saldo if max_saldo > 0 else 0.0

    hoje = date.today()
    df['data_fim_captacao'] = pd.to_datetime(df['data_fim_captacao'], errors='coerce')
    df['_dias_restantes'] = (df['data_fim_captacao'].dt.date - hoje).apply(
        lambda x: x.days if hasattr(x, 'days') else 365
    )
    df['_score_urgencia'] = df['_dias_restantes'].apply(
        lambda d: max(0.0, 1.0 - (d / 180.0)) if d >= 0 else 0.0
    )

    df['_pct_captado'] = (
        df['valor_captado'] / df['valor_aprovado'].replace(0, np.nan)
    ).fillna(0).clip(0, 1)

    df['score_prioridade'] = (
        df['_score_saldo'] * 0.40
        + df['_score_urgencia'] * 0.30
        + df['_pct_captado'] * 0.20
        + 0.10
    ).round(4)

    df = df.drop(columns=[c for c in df.columns if c.startswith('_')], errors='ignore')
    return df


def tratar_projetos() -> pd.DataFrame:
    path = os.path.join(DATA_DIR, 'projetos_reais_tratados.csv')
    df = pd.read_csv(path)
    df = calcular_score_prioridade(df)
    df.to_csv(path, index=False)
    print(f"[OK] {len(df)} projetos tratados e scores recalculados.")
    return df


if __name__ == '__main__':
    tratar_projetos()
