# -*- coding: utf-8 -*-
"""
Importa projetos reais da planilha oficial do Ministerio do Esporte.
Uso: python3 scripts/importar_ministerio_esporte.py <caminho_para_planilha.xlsx>

Exemplo:
  python3 scripts/importar_ministerio_esporte.py ~/Downloads/projetos-aptos-a-captacao.xlsx

Se nenhum argumento for passado, o script busca automaticamente por *.xlsx
na pasta do script e em data/.
"""
import os
import sys
import shutil
import pandas as pd
from datetime import datetime, date
from pathlib import Path

# Carregar variaveis do .env
_env_path = Path(__file__).parent.parent / '.env'
if _env_path.exists():
    for _line in _env_path.read_text(encoding='utf-8').splitlines():
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            _k, _v = _k.strip(), _v.strip()
            if _v and _k not in os.environ:
                os.environ[_k] = _v

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'

REGIOES = {
    'AC': 'Norte',    'AM': 'Norte',    'AP': 'Norte',
    'PA': 'Norte',    'RO': 'Norte',    'RR': 'Norte',    'TO': 'Norte',
    'AL': 'Nordeste', 'BA': 'Nordeste', 'CE': 'Nordeste', 'MA': 'Nordeste',
    'PB': 'Nordeste', 'PE': 'Nordeste', 'PI': 'Nordeste', 'RN': 'Nordeste',
    'SE': 'Nordeste',
    'DF': 'Centro-Oeste', 'GO': 'Centro-Oeste', 'MS': 'Centro-Oeste', 'MT': 'Centro-Oeste',
    'ES': 'Sudeste',  'MG': 'Sudeste',  'RJ': 'Sudeste',  'SP': 'Sudeste',
    'PR': 'Sul',      'RS': 'Sul',      'SC': 'Sul',
}

# Schema final esperado pelo dashboard e scripts downstream
SCHEMA = [
    'processo', 'proponente', 'nome_projeto', 'sli', 'manifestacao',
    'modalidade_esportiva', 'cnpj', 'municipio', 'uf', 'regiao',
    'valor_aprovado', 'valor_captado', 'saldo_disponivel',
    'percentual_captado', 'data_publicacao', 'data_inicio_captacao',
    'data_fim_captacao', 'ano_aprovacao', 'status', 'score_prioridade',
    'is_real',
]


def _localizar_planilha(caminho_arg=None):
    """Localiza a planilha XLSX: argumento, pasta data/ ou pasta scripts/."""
    if caminho_arg:
        p = Path(caminho_arg)
        if p.exists():
            return p
        # Tentar relativo ao BASE_DIR
        p2 = BASE_DIR / caminho_arg
        if p2.exists():
            return p2
        print('[ERRO] Arquivo nao encontrado: ' + str(caminho_arg))
        return None

    # Busca automatica
    candidatos = list(DATA_DIR.glob('*.xlsx')) + list(Path(__file__).parent.glob('*.xlsx'))
    candidatos = [c for c in candidatos if 'ministerio' in c.name.lower()
                  or 'projetos' in c.name.lower()
                  or 'captacao' in c.name.lower()
                  or 'aptos' in c.name.lower()]
    if candidatos:
        print('[AUTO] Planilha encontrada: ' + str(candidatos[0]))
        return candidatos[0]

    print('[ERRO] Nenhuma planilha XLSX encontrada.')
    print('       Use: python3 scripts/importar_ministerio_esporte.py /caminho/planilha.xlsx')
    print('       Baixe em: https://www.gov.br/esporte/pt-br/acoes-e-programas/lei-de-incentivo-ao-esporte')
    return None


def calcular_score(row):
    """Score de prioridade 0.0-1.0 baseado em prazo, valor e manifestacao."""
    score = 0.0
    hoje = datetime.now()

    # Fator 1 — Prazo de captacao (40%)
    try:
        dt = row['data_fim_captacao']
        dias = (dt - hoje).days if pd.notna(dt) else -1
    except Exception:
        dias = -1

    if dias < 0:
        prazo = 0.0
    elif dias <= 30:
        prazo = 1.0
    elif dias <= 90:
        prazo = 0.85
    elif dias <= 180:
        prazo = 0.70
    elif dias <= 365:
        prazo = 0.55
    else:
        prazo = 0.40
    score += prazo * 0.40

    # Fator 2 — Valor do saldo (30%) — valores menores = mais faceis de captar
    valor = row.get('valor_aprovado', 0)
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        valor = 0.0

    if pd.notna(valor) and valor > 0:
        if valor <= 500_000:
            v_score = 1.0
        elif valor <= 1_000_000:
            v_score = 0.8
        elif valor <= 3_000_000:
            v_score = 0.6
        else:
            v_score = 0.4
    else:
        v_score = 0.5
    score += v_score * 0.30

    # Fator 3 — Manifestacao (30%)
    manif = str(row.get('manifestacao', '')).strip().lower()
    if 'rendimento' in manif:
        m_score = 1.0
    elif 'participacao' in manif or 'participação' in manif:
        m_score = 0.85
    elif 'educacional' in manif:
        m_score = 0.75
    else:
        m_score = 0.60
    score += m_score * 0.30

    return round(score, 4)


def importar(xlsx_path: Path) -> pd.DataFrame:
    print('  Lendo planilha: ' + str(xlsx_path))
    df_raw = pd.read_excel(xlsx_path, header=1)
    total_raw = len(df_raw)
    print('  Registros lidos: ' + str(total_raw))

    # Renomear coluna sem header (municipio — posicao 9, indice 9)
    cols = list(df_raw.columns)
    # A coluna nan entre CNPJ e UF e o municipio
    for i, c in enumerate(cols):
        if str(c) == 'nan' or (hasattr(c, '__class__') and c.__class__.__name__ == 'float'):
            cols[i] = 'municipio'
            break
    df_raw.columns = cols

    # Strip em strings
    for col in df_raw.select_dtypes(include='object').columns:
        df_raw[col] = df_raw[col].astype(str).str.strip()

    # Mapeamento de colunas
    col_map = {
        'Processo':                    'processo',
        'Proponente':                  'proponente',
        'Projeto':                     'nome_projeto',
        'SLI':                         'sli',
        'Manifestação Desportiva':     'manifestacao',
        'Modalidade':                  'modalidade_esportiva',
        'CNPJ':                        'cnpj',
        'municipio':                   'municipio',
        'UF':                          'uf',
        'Valor Autorizado para Captação': 'valor_aprovado',
        'Data da Publicação':          'data_publicacao',
        'Período de Captação até':     'data_fim_captacao',
    }
    df = df_raw.rename(columns=col_map)

    # Garantir que colunas existam
    for novo_nome in col_map.values():
        if novo_nome not in df.columns:
            df[novo_nome] = ''

    # Converter datas
    df['data_publicacao']  = pd.to_datetime(df['data_publicacao'],  errors='coerce')
    df['data_fim_captacao'] = pd.to_datetime(df['data_fim_captacao'], errors='coerce')

    # Limpar UF (pode ter espacos ou nan)
    df['uf'] = df['uf'].astype(str).str.strip().str.upper()
    df['uf'] = df['uf'].replace({'NAN': '', 'NONE': ''})

    # Limpar CNPJ (pode ter \xa0 e outros)
    df['cnpj'] = df['cnpj'].astype(str).str.replace('\xa0', '', regex=False).str.strip()

    # Converter valor
    df['valor_aprovado'] = pd.to_numeric(df['valor_aprovado'], errors='coerce').fillna(0.0)

    # Campos derivados
    df['valor_captado']       = 0.0
    df['saldo_disponivel']    = df['valor_aprovado']
    df['percentual_captado']  = 0.0
    df['data_inicio_captacao'] = df['data_publicacao']
    df['ano_aprovacao']       = df['data_publicacao'].dt.year.fillna(0).astype(int)
    df['regiao']              = df['uf'].map(REGIOES).fillna('Nao informado')
    df['is_real']             = True

    hoje = date.today()
    def _status(row):
        try:
            dt = row['data_fim_captacao']
            if pd.isna(dt):
                return 'Encerrado'
            return 'Captando' if dt.date() >= hoje else 'Encerrado'
        except Exception:
            return 'Encerrado'
    df['status'] = df.apply(_status, axis=1)

    # Filtrar: apenas Captando + valor > 0
    df = df[(df['status'] == 'Captando') & (df['valor_aprovado'] > 0)].copy()
    print('  Projetos ativos com valor > 0: ' + str(len(df)))

    # Score de prioridade
    df['score_prioridade'] = df.apply(calcular_score, axis=1)

    # Calcular dias_restantes para o filtro
    hoje_dt = datetime.now()
    df['dias_restantes'] = df['data_fim_captacao'].apply(
        lambda d: (d - hoje_dt).days if pd.notna(d) else -1
    )

    # Filtro de qualidade — apenas projetos com real potencial de captacao
    df_filtrado = df[
        (df['status'] == 'Captando') &
        (df['score_prioridade'] >= 0.45) &
        (df['saldo_disponivel'] >= 50_000) &
        (df['dias_restantes'] >= 15)
    ].copy()
    print('  Apos filtro de qualidade: ' + str(len(df_filtrado)) + ' projetos')
    print('  (removidos ' + str(len(df) - len(df_filtrado)) + ' projetos de baixa prioridade)')
    df = df_filtrado

    # Ordenar por score desc
    df = df.sort_values('score_prioridade', ascending=False).reset_index(drop=True)

    # Garantir schema completo
    for col in SCHEMA:
        if col not in df.columns:
            df[col] = ''
    df = df[SCHEMA]

    return df


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    xlsx_path = _localizar_planilha(arg)

    if xlsx_path is None:
        sys.exit(1)

    print()
    print('=========================================================')
    print('  IMPORTACAO — Lei de Incentivo ao Esporte')
    print('=========================================================')

    df = importar(xlsx_path)

    # Copiar planilha para data/
    dest_xlsx = DATA_DIR / 'projetos-ministerio-esporte.xlsx'
    try:
        shutil.copy2(xlsx_path, dest_xlsx)
        print('  Planilha copiada para: ' + str(dest_xlsx))
    except Exception as e:
        print('  [AVISO] Nao foi possivel copiar planilha: ' + str(e))

    # Salvar CSV
    out_csv = DATA_DIR / 'projetos_reais_tratados.csv'
    df.to_csv(out_csv, index=False, encoding='utf-8')

    # Resumo
    total_ufs      = df['uf'].nunique()
    total_mods     = df['modalidade_esportiva'].nunique()
    valor_total    = df['valor_aprovado'].sum()
    ano_min        = int(df['ano_aprovacao'].min()) if len(df) else 0
    ano_max        = int(df['ano_aprovacao'].max()) if len(df) else 0

    print()
    print('  Projetos apos filtro de qualidade: ' + str(len(df)))
    print('    -> score >= 0.45, saldo >= R$ 50.000, prazo >= 15 dias')
    print('  UFs representadas:       ' + str(total_ufs))
    print('  Modalidades unicas:      ' + str(total_mods))
    print('  Ano mais antigo:         ' + str(ano_min))
    print('  Ano mais recente:        ' + str(ano_max))
    print('  Valor total em captacao: R$ {:,.2f}'.format(valor_total))
    print()
    print('  Arquivo salvo: ' + str(out_csv))
    print('=========================================================')


if __name__ == '__main__':
    main()
