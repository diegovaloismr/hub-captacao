# -*- coding: utf-8 -*-
"""
Motor de matching inteligente entre projetos e empresas.

Score de match (0-1):
  35% afinidade geográfica  (mesma UF=1.0, mesma região=0.6, nacional=0.3)
  35% afinidade setor×modalidade
  30% capacidade financeira (potencial vs. saldo necessário)
"""
import pandas as pd
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

REGIOES: dict[str, str] = {
    'AC': 'Norte',  'AM': 'Norte',  'AP': 'Norte',  'PA': 'Norte',
    'RO': 'Norte',  'RR': 'Norte',  'TO': 'Norte',
    'AL': 'Nordeste', 'BA': 'Nordeste', 'CE': 'Nordeste', 'MA': 'Nordeste',
    'PB': 'Nordeste', 'PE': 'Nordeste', 'PI': 'Nordeste', 'RN': 'Nordeste',
    'SE': 'Nordeste',
    'DF': 'Centro-Oeste', 'GO': 'Centro-Oeste', 'MS': 'Centro-Oeste', 'MT': 'Centro-Oeste',
    'ES': 'Sudeste', 'MG': 'Sudeste', 'RJ': 'Sudeste', 'SP': 'Sudeste',
    'PR': 'Sul', 'RS': 'Sul', 'SC': 'Sul',
}

# Setores com afinidade natural por modalidade
AFINIDADE: dict[str, list[str]] = {
    'Petróleo e Gás':       ['Iatismo', 'Remo', 'Canoagem', 'Natação', 'Triathlon'],
    'Mineração':            ['Atletismo', 'Judô', 'Wrestling', 'Lutas', 'Boxe'],
    'Financeiro':           ['Futebol', 'Basquete', 'Tênis', 'Golfe', 'Vôlei'],
    'Telecomunicações':     ['eSports', 'Futebol', 'Basquete', 'Tênis', 'Atletismo'],
    'Alimentos e Bebidas':  ['Futebol', 'Vôlei', 'Atletismo', 'Natação', 'Basquete'],
    'Energia':              ['Atletismo', 'Ciclismo', 'Remo', 'Natação', 'Triathlon'],
    'Automotivo':           ['Automobilismo', 'Ciclismo', 'Atletismo', 'Triathlon'],
    'Saúde':                ['Atletismo Paralímpico', 'Natação Paralímpica',
                             'Basquete em Cadeira de Rodas', 'Judô Paralímpico', 'Natação'],
    'Tecnologia':           ['eSports', 'Tênis de Mesa', 'Futebol', 'Basquete'],
    'Varejo':               ['Futebol', 'Vôlei', 'Basquete', 'Atletismo', 'Skate'],
    'Siderurgia':           ['Atletismo', 'Judô', 'Boxe', 'Rugby', 'Futebol'],
    'Papel e Celulose':     ['Canoagem', 'Remo', 'Atletismo', 'Ciclismo'],
    'Aeronáutica':          ['Iatismo', 'Atletismo', 'Ciclismo', 'Triathlon'],
    'Cosméticos':           ['Ginástica Artística', 'Ginástica Rítmica', 'Natação', 'Surfe'],
    'Construção':           ['Futebol', 'Atletismo', 'Vôlei', 'Basquete'],
    'Seguros':              ['Futebol', 'Tênis', 'Golfe', 'Atletismo', 'Automobilismo'],
    'Saneamento':           ['Natação', 'Polo Aquático', 'Canoagem', 'Remo', 'Atletismo'],
    'Financeiro/Tecnologia': ['eSports', 'Futebol', 'Basquete', 'Tênis', 'Atletismo'],
}

ALTA_VISIBILIDADE = {'futebol', 'vôlei', 'basquete', 'atletismo', 'natação', 'tênis'}


def _score_geo(uf_proj: str, uf_emp: str, reg_emp: str) -> tuple[float, str]:
    reg_proj = REGIOES.get(uf_proj, '')
    if uf_proj == uf_emp:
        return 1.0, f"Mesma UF ({uf_proj})"
    if reg_proj and reg_proj == reg_emp:
        return 0.6, f"Mesma região ({reg_proj})"
    return 0.3, "Atuação nacional"


def _score_setor(modalidade: str, setor: str) -> tuple[float, str]:
    afins = AFINIDADE.get(setor, [])
    mod_lower = str(modalidade).lower() if modalidade and str(modalidade) != 'nan' else ''
    if any(a.lower() in mod_lower for a in afins):
        return 0.9, f"Alta afinidade: {setor} × {modalidade}"
    if any(k in mod_lower for k in ALTA_VISIBILIDADE):
        return 0.5, "Modalidade de alta visibilidade"
    return 0.3, "Afinidade geral com esporte"


def _score_fin(saldo: float, potencial: float) -> tuple[float, str]:
    if potencial <= 0:
        return 0.5, "Potencial nao informado"
    ratio = saldo / potencial
    if ratio <= 0.10:   return 1.0, "Projeto cabe folgado no budget da empresa"
    elif ratio <= 0.30: return 0.85, "Projeto bem adequado ao porte da empresa"
    elif ratio <= 0.60: return 0.70, "Projeto dentro do alcance da empresa"
    elif ratio <= 1.00: return 0.55, "Projeto no limite do potencial da empresa"
    elif ratio <= 2.00: return 0.35, "Projeto acima do potencial tipico"
    else:               return 0.15, "Projeto muito acima do porte da empresa"


def calcular_match(proj: dict, emp: dict) -> dict:
    s_geo, j_geo = _score_geo(proj['uf'], emp['uf_sede'], emp.get('regiao_sede', ''))
    s_set, j_set = _score_setor(proj['modalidade_esportiva'], emp['setor'])
    s_fin, j_fin = _score_fin(proj['saldo_disponivel'], emp['potencial_investimento'])

    score = round(s_geo * 0.35 + s_set * 0.35 + s_fin * 0.30, 4)

    return {
        'nome_projeto':    proj['nome_projeto'],
        'nome_empresa':    emp['nome_empresa'],
        'score_match':     score,
        'score_geo':       round(s_geo, 4),
        'score_setor':     round(s_set, 4),
        'score_financeiro': round(s_fin, 4),
        'justificativa':   f"{j_geo} | {j_set} | {j_fin}",
    }


def rodar_matching() -> pd.DataFrame:
    projetos  = pd.read_csv(os.path.join(DATA_DIR, 'projetos_reais_tratados.csv'))
    empresas  = pd.read_csv(os.path.join(DATA_DIR, 'empresas_potenciais.csv'))

    # Com muitos projetos, limitar ao top por score para manter o CSV gerenciavel
    SCORE_MINIMO = 0.50
    TOP_EMPRESAS_POR_PROJETO = 10  # top 10 empresas por projeto

    resultados = []
    empresas_list = [emp.to_dict() for _, emp in empresas.iterrows()]

    for idx, (_, proj) in enumerate(projetos.iterrows()):
        proj_dict = proj.to_dict()
        # Garantir que modalidade seja string
        if not isinstance(proj_dict.get('modalidade_esportiva'), str) or str(proj_dict.get('modalidade_esportiva', '')) == 'nan':
            proj_dict['modalidade_esportiva'] = ''
        if not isinstance(proj_dict.get('uf'), str) or str(proj_dict.get('uf', '')) == 'nan':
            proj_dict['uf'] = ''

        matches = [calcular_match(proj_dict, emp) for emp in empresas_list]
        matches = [m for m in matches if m['score_match'] >= SCORE_MINIMO]
        matches.sort(key=lambda x: x['score_match'], reverse=True)
        matches = matches[:TOP_EMPRESAS_POR_PROJETO]
        for rank, m in enumerate(matches, 1):
            m['ranking_projeto'] = rank
        resultados.extend(matches)

        if (idx + 1) % 500 == 0:
            print(f"  Processados {idx+1}/{len(projetos)} projetos...")

    df = pd.DataFrame(resultados)
    df.to_csv(os.path.join(DATA_DIR, 'match_inteligente.csv'), index=False)
    print(f"[OK] {len(df)} matches gerados ({len(projetos)} projetos × {len(empresas)} empresas, score >= {SCORE_MINIMO}).")
    return df


if __name__ == '__main__':
    rodar_matching()
