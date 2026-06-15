# -*- coding: utf-8 -*-
"""
Motor de matching entre projetos Rouanet e empresas patrocinadoras.
Score: 35% geo + 35% setor×segmento cultural + 30% capacidade financeira
"""
import pandas as pd, os

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

REGIOES = {
    'AC':'Norte','AM':'Norte','AP':'Norte','PA':'Norte','RO':'Norte','RR':'Norte','TO':'Norte',
    'AL':'Nordeste','BA':'Nordeste','CE':'Nordeste','MA':'Nordeste','PB':'Nordeste',
    'PE':'Nordeste','PI':'Nordeste','RN':'Nordeste','SE':'Nordeste',
    'DF':'Centro-Oeste','GO':'Centro-Oeste','MS':'Centro-Oeste','MT':'Centro-Oeste',
    'ES':'Sudeste','MG':'Sudeste','RJ':'Sudeste','SP':'Sudeste',
    'PR':'Sul','RS':'Sul','SC':'Sul',
}

AFINIDADE_CULTURAL = {
    'Financeiro':            ['Música','Teatro','Artes Visuais','Patrimônio Cultural','Humanidades'],
    'Petróleo e Gás':        ['Patrimônio Cultural','Humanidades','Artes Visuais','Música'],
    'Mineração e Siderurgia':['Patrimônio Cultural','Humanidades','Artes Visuais'],
    'Telecomunicações':      ['Audiovisual','Música','Teatro','Circo','Artes Visuais'],
    'Tecnologia':            ['Audiovisual','Artes Visuais','Música','Games'],
    'Alimentos e Bebidas':   ['Música','Teatro','Circo','Festas Populares','Carnaval'],
    'Automotivo':            ['Música','Audiovisual','Artes Visuais','Teatro'],
    'Energia':               ['Patrimônio Cultural','Artes Visuais','Humanidades'],
    'Varejo':                ['Música','Teatro','Artes Visuais','Circo'],
    'Saúde':                 ['Música','Teatro','Dança','Humanidades'],
    'Papel e Celulose':      ['Literatura','Humanidades','Patrimônio Cultural'],
    'Saneamento':            ['Patrimônio Cultural','Humanidades','Artes Visuais'],
    'Logística':             ['Música','Teatro','Audiovisual'],
    'Cosméticos':            ['Dança','Música','Moda','Artes Visuais'],
    'Construção':            ['Patrimônio Cultural','Artes Visuais','Humanidades'],
    'Seguros':               ['Música','Teatro','Humanidades','Patrimônio Cultural'],
}

ALTA_VISIBILIDADE = {'música','teatro','audiovisual','cinema','dança','literatura'}


def _score_geo(uf_proj, uf_emp, reg_emp):
    reg_proj = REGIOES.get(str(uf_proj).strip().upper(), '')
    uf_emp = str(uf_emp).strip().upper()
    if uf_proj == uf_emp:
        return 1.0, f'Mesma UF ({uf_proj})'
    if reg_proj and reg_proj == reg_emp:
        return 0.6, f'Mesma região ({reg_proj})'
    return 0.3, 'Atuação nacional'


def _score_setor(segmento, setor):
    afins = AFINIDADE_CULTURAL.get(setor, [])
    seg_l = str(segmento).lower() if segmento and str(segmento) != 'nan' else ''
    if any(a.lower() in seg_l for a in afins):
        return 0.9, f'Alta afinidade: {setor} × {segmento}'
    if any(k in seg_l for k in ALTA_VISIBILIDADE):
        return 0.5, 'Segmento de alta visibilidade'
    return 0.3, 'Afinidade geral com cultura'


def _score_fin(saldo, potencial):
    if potencial <= 0:
        return 0.5, 'Potencial não informado'
    ratio = saldo / potencial
    if ratio <= 0.10:   return 1.0,  'Projeto cabe folgado no budget'
    elif ratio <= 0.30: return 0.85, 'Projeto bem adequado ao porte'
    elif ratio <= 0.60: return 0.70, 'Projeto dentro do alcance'
    elif ratio <= 1.00: return 0.55, 'Projeto no limite do potencial'
    elif ratio <= 2.00: return 0.35, 'Projeto acima do potencial típico'
    else:               return 0.15, 'Projeto muito acima do porte'


def calcular_match(proj, emp):
    uf_proj   = str(proj.get('uf', '') or '').strip().upper()
    uf_emp    = str(emp.get('uf_sede', '') or '').strip().upper()
    reg_emp   = str(emp.get('regiao_sede', '') or '')
    segmento  = str(proj.get('segmento_cultural', '') or '')
    setor     = str(emp.get('setor', '') or '')
    saldo     = float(proj.get('saldo_disponivel', 0) or 0)
    potencial = float(emp.get('potencial_investimento', 0) or 0)

    s_geo, j_geo = _score_geo(uf_proj, uf_emp, reg_emp)
    s_set, j_set = _score_setor(segmento, setor)
    s_fin, j_fin = _score_fin(saldo, potencial)

    score = round(s_geo * 0.35 + s_set * 0.35 + s_fin * 0.30, 4)
    return {
        'nome_projeto':     proj.get('nome_projeto', ''),
        'nome_empresa':     emp.get('nome_empresa', ''),
        'score_match':      score,
        'score_geo':        round(s_geo, 4),
        'score_setor':      round(s_set, 4),
        'score_financeiro': round(s_fin, 4),
        'justificativa':    f'{j_geo} | {j_set} | {j_fin}',
        'ranking_projeto':  0,
        'lei':              'Rouanet',
    }


def rodar_matching():
    projetos = pd.read_csv(os.path.join(DATA_DIR, 'projetos_rouanet.csv'))
    empresas = pd.read_csv(os.path.join(DATA_DIR, 'empresas_potenciais.csv'))

    SCORE_MINIMO     = 0.45
    TOP_EMP_POR_PROJ = 15

    empresas_list = [e.to_dict() for _, e in empresas.iterrows()]
    resultados = []

    for idx, (_, proj) in enumerate(projetos.iterrows()):
        p = proj.to_dict()
        if str(p.get('segmento_cultural', '')) == 'nan': p['segmento_cultural'] = ''
        if str(p.get('uf', '')) == 'nan':                p['uf'] = ''

        matches = [calcular_match(p, emp) for emp in empresas_list]
        matches = sorted([m for m in matches if m['score_match'] >= SCORE_MINIMO],
                         key=lambda x: x['score_match'], reverse=True)[:TOP_EMP_POR_PROJ]
        for rank, m in enumerate(matches, 1):
            m['ranking_projeto'] = rank
        resultados.extend(matches)

        if (idx + 1) % 500 == 0:
            print(f'  Processados {idx+1}/{len(projetos)}...')

    df = pd.DataFrame(resultados)
    out = os.path.join(DATA_DIR, 'match_rouanet.csv')
    df.to_csv(out, index=False)
    print(f'[OK] {len(df)} matches Rouanet ({len(projetos)} projetos × {len(empresas)} empresas, score >= {SCORE_MINIMO})')
    return df


if __name__ == '__main__':
    rodar_matching()
