# -*- coding: utf-8 -*-
"""
Matching entre projetos Rouanet e editais de financiamento.
Score: 40% temático + 25% UF + 20% valor + 15% prazo
"""
import os, pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

KEYWORDS_SEGMENTO: dict = {
    'música':          ['música', 'musica', 'cultura', 'arte', 'festival', 'show', 'concerto'],
    'teatro':          ['teatro', 'cultura', 'arte', 'cênico', 'dramaturg', 'peça'],
    'audiovisual':     ['audiovisual', 'cinema', 'filme', 'vídeo', 'video', 'cultura', 'tv'],
    'dança':           ['dança', 'danca', 'cultura', 'arte', 'cênico', 'ballet'],
    'literatura':      ['literatura', 'livro', 'leitura', 'cultura', 'educação', 'arte'],
    'artes visuais':   ['arte', 'cultura', 'visual', 'exposição', 'museu', 'patrimônio'],
    'patrimônio':      ['patrimônio', 'cultura', 'história', 'memória', 'identidade'],
    'circo':           ['circo', 'cultura', 'arte', 'cênico', 'espetáculo'],
    'humanidades':     ['cultura', 'educação', 'social', 'humanidades', 'diversidade'],
    'default':         ['cultura', 'arte', 'social', 'educação', 'comunidade'],
}

SCORE_BASE = 0.20


def _score_tematico(segmento: str, areas: str, titulo: str) -> tuple:
    seg  = str(segmento or '').lower()
    text = (str(areas or '') + ' ' + str(titulo or '')).lower()

    kws = None
    for k, v in KEYWORDS_SEGMENTO.items():
        if k in seg:
            kws = v
            break
    if kws is None:
        kws = KEYWORDS_SEGMENTO['default']

    matches = [k for k in kws if k in text]

    if len(matches) >= 3:
        return 1.0, f'Alta compatibilidade: {", ".join(matches[:3])}'
    elif len(matches) >= 2:
        return 0.75, f'Boa compatibilidade: {", ".join(matches[:2])}'
    elif len(matches) == 1:
        return 0.50, f'Compatibilidade parcial: {matches[0]}'
    elif any(k in text for k in ['cultura', 'arte', 'social']):
        return 0.35, 'Edital com foco cultural/social'
    return SCORE_BASE, 'Compatibilidade base'


def _score_uf(uf_proj: str, uf_edit: str) -> tuple:
    uf_proj = str(uf_proj or '').strip().upper()
    uf_edit = str(uf_edit or '').strip().upper()
    if not uf_edit or uf_edit in ('NACIONAL', ''):
        return 1.0, 'Edital nacional'
    if uf_proj == uf_edit:
        return 1.0, f'Mesma UF ({uf_proj})'
    return 0.3, 'UF diferente'


def _score_valor(saldo: float, valor_max: str) -> tuple:
    try:
        vmax = float(str(valor_max).replace(',', '.')) if valor_max else 0
    except Exception:
        vmax = 0
    if not vmax:
        return 0.5, 'Valor máximo não informado'
    if saldo <= vmax:
        return 1.0, f'Saldo dentro do limite (R$ {vmax:,.0f})'
    elif saldo <= vmax * 2:
        return 0.6, 'Saldo ligeiramente acima do limite'
    return 0.2, 'Saldo muito acima do limite'


def _score_prazo(dias: int) -> tuple:
    if dias < 0:   return 0.0, 'Edital encerrado'
    if dias <= 7:  return 0.3, f'Prazo crítico ({dias}d)'
    if dias <= 30: return 0.8, f'Prazo curto ({dias}d)'
    if dias <= 90: return 1.0, f'Prazo ideal ({dias}d)'
    return 0.7, f'Prazo longo ({dias}d)'


def rodar_matching():
    proj_path = os.path.join(DATA_DIR, 'projetos_rouanet.csv')
    edit_path = os.path.join(DATA_DIR, 'editais.csv')

    if not os.path.exists(proj_path):
        print('[ERRO] projetos_rouanet.csv não encontrado.')
        return
    if not os.path.exists(edit_path):
        print('[ERRO] editais.csv não encontrado.')
        return

    projetos = pd.read_csv(proj_path).fillna('')
    editais  = pd.read_csv(edit_path).fillna('')
    editais_ativos = editais[editais['status'] == 'ativo']

    print(f'[INFO] {len(projetos)} projetos Rouanet × {len(editais_ativos)} editais ativos')

    resultados = []
    for _, proj in projetos.iterrows():
        for _, ed in editais_ativos.iterrows():
            s_tem, j_tem = _score_tematico(
                proj.get('segmento_cultural', ''),
                ed.get('areas_tematicas', ''),
                ed.get('titulo', ''),
            )
            s_uf,  j_uf  = _score_uf(proj.get('uf', ''), ed.get('uf_elegivel', ''))
            s_val, j_val = _score_valor(
                float(proj.get('saldo_disponivel', 0) or 0),
                ed.get('valor_max', ''),
            )
            s_pra, j_pra = _score_prazo(int(ed.get('dias_restantes', -1) or -1))

            score = round(s_tem*0.40 + s_uf*0.25 + s_val*0.20 + s_pra*0.15, 4)
            if score < 0.30:
                continue

            resultados.append({
                'nome_projeto':   proj['nome_projeto'],
                'id_edital':      ed['id'],
                'titulo_edital':  ed['titulo'],
                'financiador':    ed['financiador'],
                'score_match':    score,
                'score_tematico': round(s_tem, 4),
                'score_uf':       round(s_uf,  4),
                'score_valor':    round(s_val,  4),
                'score_prazo':    round(s_pra,  4),
                'dias_restantes': int(ed.get('dias_restantes', -1) or -1),
                'status_edital':  ed.get('status', ''),
                'url_edital':     ed.get('url_original', ''),
                'justificativa':  f'{j_tem} | {j_uf} | {j_val} | {j_pra}',
                'lei':            'Rouanet',
            })

    df = pd.DataFrame(resultados)
    if not df.empty:
        df = df.sort_values('score_match', ascending=False)

    out = os.path.join(DATA_DIR, 'match_editais_rouanet.csv')
    df.to_csv(out, index=False)
    print(f'[OK] {len(df)} matches Rouanet×editais salvos em match_editais_rouanet.csv')


if __name__ == '__main__':
    rodar_matching()
