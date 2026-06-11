# -*- coding: utf-8 -*-
"""
Gestão da base de empresas patrocinadoras.

Score de empresa (0-1):
  60% escala de faturamento anual (log10 normalizado)
  40% potencial estimado de investimento
"""
import math
import pandas as pd
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')


def calcular_score_empresa(row) -> float:
    faturamento = float(row.get('faturamento_anual') or 0)
    potencial   = float(row.get('potencial_investimento') or 0)

    score_fat = min(1.0, math.log10(max(faturamento, 1)) / 12.0)  # 10^12 ≈ 1T BRL
    score_pot = min(1.0, potencial / 50_000_000.0)

    return round(score_fat * 0.6 + score_pot * 0.4, 4)


def carregar_empresas() -> pd.DataFrame:
    return pd.read_csv(os.path.join(DATA_DIR, 'empresas_potenciais.csv'))


def atualizar_scores() -> pd.DataFrame:
    df = carregar_empresas()
    df['score_empresa'] = df.apply(calcular_score_empresa, axis=1)
    df.to_csv(os.path.join(DATA_DIR, 'empresas_potenciais.csv'), index=False)
    print(f"[OK] Scores atualizados para {len(df)} empresas.")
    return df


if __name__ == '__main__':
    atualizar_scores()
