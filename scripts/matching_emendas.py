# -*- coding: utf-8 -*-
"""
Motor de matching vetorizado entre projetos e emendas parlamentares.
Usa cross join + operações numpy para performance em vez de loop duplo.

Uso: python3 scripts/matching_emendas.py
Saída: data/match_emendas.csv
"""
import os
import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = Path(os.environ.get('DATA_DIR', BASE_DIR / 'data'))

IN_LIE     = DATA_DIR / 'projetos_reais_tratados.csv'
IN_ROUANET = DATA_DIR / 'projetos_rouanet.csv'
IN_EMENDAS = DATA_DIR / 'emendas_parlamentares.csv'
OUT_CSV    = DATA_DIR / 'match_emendas.csv'

SCORE_MIN            = 0.35
TOP_POR_PROJETO      = 10

REGIOES = {
    'AC':'Norte','AM':'Norte','AP':'Norte','PA':'Norte','RO':'Norte','RR':'Norte','TO':'Norte',
    'AL':'Nordeste','BA':'Nordeste','CE':'Nordeste','MA':'Nordeste','PB':'Nordeste',
    'PE':'Nordeste','PI':'Nordeste','RN':'Nordeste','SE':'Nordeste',
    'DF':'Centro-Oeste','GO':'Centro-Oeste','MS':'Centro-Oeste','MT':'Centro-Oeste',
    'ES':'Sudeste','MG':'Sudeste','RJ':'Sudeste','SP':'Sudeste',
    'PR':'Sul','RS':'Sul','SC':'Sul',
}

# Palavras que identificam área do projeto → termos esperados nas emendas
AREA_KEYWORDS = {
    'esporte':   ['esporte', 'desporto', 'lazer', 'atleta', 'olímpico'],
    'cultura':   ['cultura', 'arte', 'patrimônio', 'música', 'teatro', 'cinema', 'audiovisual'],
    'social':    ['social', 'assistência', 'comunidade', 'inclusão', 'vulnerável'],
    'educação':  ['educação', 'escola', 'juventude', 'criança', 'formação'],
    'saúde':     ['saúde', 'médico', 'hospital', 'deficiência'],
}

# Mapa: funcao da emenda → área
FUNCAO_AREA = {
    'desporto e lazer': 'esporte',
    'cultura':          'cultura',
    'assistência social': 'social',
    'educação':         'educação',
    'saúde':            'saúde',
    'direitos da cidadania': 'social',
    'seguridade social': 'social',
}


def _area_projeto(row: pd.Series) -> str:
    """Detecta área principal de um projeto."""
    campos = ' '.join([
        str(row.get('modalidade_esportiva', '')),
        str(row.get('segmento_cultural', '')),
        str(row.get('tipo', '')),
        str(row.get('nome_projeto', '')),
    ]).lower()
    for area, kws in AREA_KEYWORDS.items():
        if any(kw in campos for kw in kws):
            return area
    return 'social'


def _area_emenda(row: pd.Series) -> str:
    """Detecta área principal de uma emenda."""
    funcao = str(row.get('funcao', '')).lower()
    for f, a in FUNCAO_AREA.items():
        if f in funcao:
            return a
    areas_interesse = str(row.get('areas_interesse', '')).lower()
    for area in AREA_KEYWORDS:
        if area in areas_interesse:
            return area
    return ''


def calcular_matches(df_proj: pd.DataFrame, df_em: pd.DataFrame, lei: str) -> pd.DataFrame:
    """Cross join vetorizado entre projetos e emendas."""
    if df_proj.empty or df_em.empty:
        return pd.DataFrame()

    # Colunas auxiliares nos projetos
    df_proj = df_proj.copy()
    df_proj['_area']   = df_proj.apply(_area_projeto, axis=1)
    df_proj['_regiao'] = df_proj['uf'].map(REGIOES).fillna('')
    df_proj['_key']    = 1

    # Colunas auxiliares nas emendas
    df_em = df_em.copy()
    df_em['_area_em']   = df_em.apply(_area_emenda, axis=1)
    df_em['_regiao_em'] = df_em['uf_parlamentar'].map(REGIOES).fillna('')
    df_em['_key']       = 1

    # Cross join
    df = df_proj.merge(df_em, on='_key', suffixes=('_proj', '_em')).drop('_key', axis=1)

    # ── Score GEO ──────────────────────────────────────────────────────────
    uf_proj = df['uf'].fillna('')
    uf_em   = df['uf_parlamentar'].fillna('')
    reg_p   = df['_regiao'].fillna('')
    reg_e   = df['_regiao_em'].fillna('')

    df['score_geo'] = np.where(
        (uf_proj != '') & (uf_proj == uf_em), 1.0,
        np.where(
            (reg_p != '') & (reg_p == reg_e), 0.65,
            0.25
        )
    )

    # ── Score AREA ─────────────────────────────────────────────────────────
    df['score_area'] = np.where(
        df['_area'] == df['_area_em'], 0.90,
        np.where(df['_area_em'] == '', 0.40, 0.20)
    )

    # ── Score SALDO ────────────────────────────────────────────────────────
    saldo_proj = pd.to_numeric(df.get('saldo_disponivel_proj', df.get('saldo_disponivel', 0)), errors='coerce').fillna(0)
    saldo_em   = pd.to_numeric(df['saldo_disponivel_em'] if 'saldo_disponivel_em' in df.columns else df.get('saldo_disponivel', 0), errors='coerce').fillna(1).clip(lower=1)

    ratio = saldo_proj / saldo_em
    df['score_saldo'] = np.select(
        [ratio <= 0.20, ratio <= 0.50, ratio <= 1.00, ratio <= 2.00],
        [1.00,          0.85,          0.70,          0.45],
        default=0.20
    )

    # ── Score final ────────────────────────────────────────────────────────
    df['score_match'] = (
        df['score_geo']   * 0.45 +
        df['score_area']  * 0.35 +
        df['score_saldo'] * 0.20
    ).round(4)

    df['lei'] = lei

    # Filtrar por score mínimo
    df = df[df['score_match'] >= SCORE_MIN]

    # Top N por projeto
    df = (df.sort_values('score_match', ascending=False)
            .groupby('nome_projeto')
            .head(TOP_POR_PROJETO))

    # Selecionar colunas de saída
    cols_saida = {
        'nome_projeto':    'nome_projeto',
        'uf':              'uf_projeto',
        'lei':             'lei',
        'score_match':     'score_match',
        'score_geo':       'score_geo',
        'score_area':      'score_area',
        'score_saldo':     'score_saldo',
        'codigo_emenda':   'codigo_emenda',
        'parlamentar':     'parlamentar',
        'tipo_parlamentar':'tipo_parlamentar',
        'uf_parlamentar':  'uf_parlamentar',
        'funcao':          'funcao',
        'saldo_disponivel_em': 'saldo_emenda',
        'valor_empenhado': 'valor_empenhado',
        'ano':             'ano',
        'url':             'url',
    }

    presentes = {k: v for k, v in cols_saida.items() if k in df.columns}
    df_out = df[list(presentes.keys())].rename(columns=presentes)

    return df_out


def main() -> None:
    print('=' * 56)
    print('  MATCHING EMENDAS PARLAMENTARES (vetorizado)')
    print('=' * 56)

    if not IN_EMENDAS.exists():
        print(f'[ERRO] {IN_EMENDAS} não encontrado.')
        print('  Execute primeiro: python3 scripts/importar_emendas.py')
        return

    df_em = pd.read_csv(IN_EMENDAS).fillna('')
    print(f'[INFO] Emendas carregadas: {len(df_em)}')

    if df_em.empty:
        print('[AVISO] CSV de emendas vazio — nenhum match gerado.')
        pd.DataFrame().to_csv(OUT_CSV, index=False)
        return

    # Garantir coluna saldo_disponivel nas emendas
    if 'saldo_disponivel' not in df_em.columns:
        df_em['saldo_disponivel'] = pd.to_numeric(df_em.get('valor_empenhado', 0), errors='coerce').fillna(0)

    df_em = df_em[pd.to_numeric(df_em['saldo_disponivel'], errors='coerce').fillna(0) > 0].copy()
    print(f'[INFO] Emendas com saldo > 0: {len(df_em)}')

    frames = []

    for csv_path, lei in [(IN_LIE, 'LIE'), (IN_ROUANET, 'Rouanet')]:
        if not csv_path.exists():
            print(f'[SKIP] {csv_path.name} não encontrado')
            continue
        df_proj = pd.read_csv(csv_path).fillna('')
        print(f'[{lei}] {len(df_proj)} projetos × {len(df_em)} emendas...')
        resultado = calcular_matches(df_proj, df_em, lei)
        print(f'[{lei}] {len(resultado)} matches (score >= {SCORE_MIN})')
        frames.append(resultado)

    if not frames:
        print('[ERRO] Nenhum CSV de projetos encontrado.')
        return

    df_final = pd.concat(frames, ignore_index=True)
    df_final = df_final.sort_values('score_match', ascending=False).reset_index(drop=True)
    df_final.to_csv(OUT_CSV, index=False)

    print(f'\n[OK] {len(df_final)} matches salvos em {OUT_CSV}')
    print(f'     Score médio: {df_final["score_match"].mean():.3f}')
    print(f'     Score máx:   {df_final["score_match"].max():.3f}')
    if 'parlamentar' in df_final.columns:
        print(f'     Parlamentares únicos: {df_final["parlamentar"].nunique()}')
    print('\nTop 5:')
    for _, r in df_final.head(5).iterrows():
        print(f'  {r["score_match"]:.2f}  {str(r.get("nome_projeto",""))[:38]:<38}  '
              f'{str(r.get("parlamentar",""))[:25]:<25}')


if __name__ == '__main__':
    main()
