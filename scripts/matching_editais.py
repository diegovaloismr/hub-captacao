# -*- coding: utf-8 -*-
"""
Motor de matching entre projetos esportivos e editais de financiamento.

Score final (0-1):
  40% score_tematico  — alinhamento entre modalidade e áreas do edital
  25% score_uf        — elegibilidade geográfica
  20% score_valor     — compatibilidade financeira
  15% score_prazo     — urgência / viabilidade de prazo
"""
import os
import pandas as pd

# Carregar variáveis do arquivo .env se existir
from pathlib import Path
_env_path = Path(__file__).parent.parent / '.env'
if _env_path.exists():
    for _line in _env_path.read_text(encoding='utf-8').splitlines():
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            _k, _v = _k.strip(), _v.strip()
            if _v and _k not in os.environ:
                os.environ[_k] = _v

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

# ── Mapeamentos temáticos ────────────────────────────────────────────────────

KEYWORDS_MODALIDADE: dict[str, list[str]] = {
    # Alto rendimento olímpico
    'atletismo':        ['esporte', 'atletismo', 'alto rendimento', 'olímpico', 'jovem'],
    'natação':          ['esporte', 'natação', 'alto rendimento', 'aquático', 'olímpico'],
    'judô':             ['esporte', 'lutas', 'alto rendimento', 'olímpico', 'judô'],
    'boxe':             ['esporte', 'lutas', 'boxe', 'alto rendimento'],
    'wrestling':        ['esporte', 'lutas', 'wrestling'],
    'taekwondo':        ['esporte', 'lutas', 'taekwondo', 'olímpico'],
    'karatê':           ['esporte', 'lutas', 'karatê'],
    'vôlei':            ['esporte', 'vôlei', 'alto rendimento', 'olímpico'],
    'futebol':          ['esporte', 'futebol', 'educação', 'juventude', 'base', 'social'],
    'basquete':         ['esporte', 'basquete', 'alto rendimento', 'olímpico'],
    'handebol':         ['esporte', 'handebol', 'alto rendimento'],
    'tênis':            ['esporte', 'tênis', 'alto rendimento'],
    'golf':             ['esporte', 'golfe', 'alto rendimento'],
    'ciclismo':         ['esporte', 'ciclismo', 'alto rendimento', 'olímpico'],
    'remo':             ['esporte', 'remo', 'alto rendimento', 'aquático', 'olímpico'],
    'canoagem':         ['esporte', 'canoagem', 'alto rendimento', 'aquático', 'olímpico'],
    'iatismo':          ['esporte', 'iatismo', 'olímpico', 'aquático'],
    'surfe':            ['esporte', 'surfe', 'olímpico'],
    'skate':            ['esporte', 'skate', 'olímpico', 'juventude'],
    'breaking':         ['esporte', 'breaking', 'olímpico', 'cultura', 'dança'],
    'rugby':            ['esporte', 'rugby', 'alto rendimento', 'olímpico'],
    'hipismo':          ['esporte', 'hipismo', 'olímpico'],
    'ginástica artística': ['esporte', 'ginástica', 'olímpico', 'cultura'],
    'ginástica rítmica': ['esporte', 'ginástica', 'olímpico', 'cultura', 'dança'],
    'esgrima':          ['esporte', 'esgrima', 'olímpico'],
    'tiro':             ['esporte', 'tiro', 'olímpico'],
    'pentatlo':         ['esporte', 'pentatlo', 'olímpico'],
    'triathlon':        ['esporte', 'triathlon', 'alto rendimento', 'olímpico'],
    # Paralímpico
    'paralímpico':      ['esporte', 'paralímpico', 'inclusão', 'acessibilidade', 'saúde'],
    'cadeira de rodas': ['esporte', 'paralímpico', 'inclusão', 'acessibilidade', 'saúde'],
    # Base / social
    'base':             ['esporte', 'educação', 'juventude', 'base', 'social', 'comunidade'],
    'formação':         ['esporte', 'educação', 'juventude', 'base', 'social'],
}

SCORE_BASE_TEMATICO = 0.20  # qualquer projeto tem afinidade mínima com "esporte"


def _score_tematico(modalidade: str, areas: str, titulo: str, descricao: str) -> tuple[float, str]:
    mod_lower  = (str(modalidade) if modalidade and str(modalidade) != 'nan' else '').lower()
    texto_edit = (str(areas) + ' ' + str(titulo) + ' ' + str(descricao)).lower()

    # Verificar palavra "esporte" no edital — score base
    if 'esport' not in texto_edit and 'atleta' not in texto_edit and 'olimp' not in texto_edit:
        # Edital sem foco esportivo explícito — score mínimo
        score = SCORE_BASE_TEMATICO
        return score, 'Esporte não é foco do edital — compatibilidade base'

    best_score = 0.0
    best_reason = ''

    for kw_mod, kw_list in KEYWORDS_MODALIDADE.items():
        if kw_mod in mod_lower or any(kw_mod in mod_lower for kw_mod in kw_list):
            matches = [kw for kw in kw_list if kw in texto_edit]
            if matches:
                frac = len(matches) / len(kw_list)
                sc = min(1.0, 0.40 + frac * 0.60)
                if sc > best_score:
                    best_score = sc
                    best_reason = f'Palavras-chave: {", ".join(matches[:3])}'

    # Correspondência direta: nome da modalidade no edital
    palavras_mod = [w for w in mod_lower.split() if len(w) > 3]
    for palavra in palavras_mod:
        if palavra in texto_edit:
            if best_score < 0.80:
                best_score = max(best_score, 0.75)
                best_reason = f'Modalidade "{palavra}" mencionada no edital'

    # "Alto rendimento" explícito no edital
    if 'alto rendimento' in texto_edit:
        best_score = max(best_score, 0.55)

    if best_score == 0.0:
        best_score = SCORE_BASE_TEMATICO + 0.10  # fundo esportivo mas sem match específico
        best_reason = 'Edital esportivo sem correspondência temática direta'

    return round(best_score, 4), best_reason or 'Alinhamento temático encontrado'


def _score_uf(uf_projeto: str, uf_elegivel: str) -> tuple[float, str]:
    uf_proj = (uf_projeto or '').strip().upper()
    uf_edit = (uf_elegivel or '').strip()

    if not uf_edit:
        return 0.30, 'Elegibilidade geográfica não informada'

    uf_edit_upper = uf_edit.upper()

    if 'NACIONAL' in uf_edit_upper or 'BRASIL' in uf_edit_upper:
        return 1.0, 'Edital de abrangência nacional'

    if uf_proj in [u.strip() for u in uf_edit_upper.split('|')]:
        return 1.0, f'UF do projeto ({uf_proj}) elegível'

    return 0.0, f'UF do projeto ({uf_proj}) não elegível para este edital'


def _score_valor(saldo: float, valor_max_str: str) -> tuple[float, str]:
    if not valor_max_str or str(valor_max_str).strip() == '':
        return 0.5, 'Valor máximo do edital não informado'
    try:
        valor_max = float(str(valor_max_str).replace(',', '.'))
    except ValueError:
        return 0.5, 'Valor máximo do edital não informado'

    if valor_max <= 0:
        return 0.5, 'Valor máximo do edital não informado'

    ratio = saldo / valor_max
    if ratio <= 1.0:
        return 1.0, f'Saldo ≤ valor máximo (R$ {valor_max:,.0f})'
    if ratio <= 2.0:
        return 0.6, f'Saldo até 2× o valor máximo do edital'
    return 0.2, f'Saldo muito acima do valor máximo do edital'


def _score_prazo(dias: int) -> tuple[float, str]:
    if dias == -1:
        return 0.5, 'Prazo não informado'
    if dias <= 0:
        return 0.0, 'Edital encerrado'
    if dias <= 7:
        return 0.3, f'Prazo crítico ({dias} dias)'
    if dias <= 30:
        return 0.8, f'Prazo urgente mas viável ({dias} dias)'
    if dias <= 90:
        return 1.0, f'Prazo ideal ({dias} dias)'
    return 0.7, f'Prazo longo ({dias} dias)'


def calcular_match_edital(proj: dict, edital: dict) -> dict:
    s_tem, j_tem = _score_tematico(
        proj.get('modalidade_esportiva', ''),
        str(edital.get('areas_tematicas', '')),
        str(edital.get('titulo', '')),
        str(edital.get('descricao', '')),
    )
    s_uf,  j_uf  = _score_uf(proj.get('uf', ''), str(edital.get('uf_elegivel', '')))
    s_val, j_val = _score_valor(
        float(proj.get('saldo_disponivel', 0) or 0),
        str(edital.get('valor_max', '')),
    )
    s_pra, j_pra = _score_prazo(int(edital.get('dias_restantes', -1) or -1))

    score = round(s_tem * 0.40 + s_uf * 0.25 + s_val * 0.20 + s_pra * 0.15, 4)

    return {
        'nome_projeto':   proj.get('nome_projeto', ''),
        'id_edital':      edital.get('id', ''),
        'titulo_edital':  edital.get('titulo', ''),
        'financiador':    edital.get('financiador', ''),
        'score_match':    score,
        'score_tematico': round(s_tem, 4),
        'score_uf':       round(s_uf,  4),
        'score_valor':    round(s_val, 4),
        'score_prazo':    round(s_pra, 4),
        'dias_restantes': edital.get('dias_restantes', -1),
        'status_edital':  edital.get('status', ''),
        'url_edital':     edital.get('url_original', ''),
        'justificativa':  f'{j_tem} | {j_uf} | {j_val} | {j_pra}',
    }


def rodar_matching_editais() -> pd.DataFrame:
    proj_path   = os.path.join(DATA_DIR, 'projetos_reais_tratados.csv')
    edit_path   = os.path.join(DATA_DIR, 'editais.csv')
    out_path    = os.path.join(DATA_DIR, 'match_editais.csv')

    if not os.path.exists(edit_path):
        print(f'[ERRO] {edit_path} não encontrado. Execute coletar_editais.py primeiro.')
        return pd.DataFrame()

    projetos = pd.read_csv(proj_path)
    editais  = pd.read_csv(edit_path)
    editais['dias_restantes'] = pd.to_numeric(editais['dias_restantes'], errors='coerce').fillna(-1).astype(int)

    resultados = []
    for _, proj in projetos.iterrows():
        for _, edital in editais.iterrows():
            m = calcular_match_edital(proj.to_dict(), edital.to_dict())
            if m['score_match'] >= 0.30:
                resultados.append(m)

    df = pd.DataFrame(resultados)
    if not df.empty:
        df = df.sort_values('score_match', ascending=False).reset_index(drop=True)

    df.to_csv(out_path, index=False)
    print(f'[OK] {len(df)} matches projeto×edital salvos em {out_path}')
    print(f'     ({len(projetos)} projetos × {len(editais)} editais, corte ≥ 0.30)')
    return df


if __name__ == '__main__':
    rodar_matching_editais()
