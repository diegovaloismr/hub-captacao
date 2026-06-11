# -*- coding: utf-8 -*-
"""
Importa empresas reais dos Paineis LIE + Rouanet (Prosas, 2022-2025).
Uso: python3 scripts/importar_empresas.py
"""
import os, sys, time, re, math, requests, pandas as pd
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
    'AC':'Norte','AM':'Norte','AP':'Norte','PA':'Norte','RO':'Norte','RR':'Norte','TO':'Norte',
    'AL':'Nordeste','BA':'Nordeste','CE':'Nordeste','MA':'Nordeste','PB':'Nordeste',
    'PE':'Nordeste','PI':'Nordeste','RN':'Nordeste','SE':'Nordeste',
    'DF':'Centro-Oeste','GO':'Centro-Oeste','MS':'Centro-Oeste','MT':'Centro-Oeste',
    'ES':'Sudeste','MG':'Sudeste','RJ':'Sudeste','SP':'Sudeste',
    'PR':'Sul','RS':'Sul','SC':'Sul',
}

CNPJ_MAP = {
    'VALE':'33592510000154','ITAU':'60872504000123','PETROBRAS':'33000167000101',
    'NUBANK':'18236120000158','SHELL':'04882798000177','BRADESCO':'60746948000112',
    'SANTANDER':'90400888000142','BANCO DO BRASIL':'00000000000191',
    'BNDES':'33657248000189','B3':'09346601000125','AMBEV':'07526557000100',
    'VIVO':'02558157000162','WEG':'84429695000111','ARCELORMITTAL':'60887852000123',
    'VOLVO':'00197614000500','TOYOTA':'59275792000140','JOHN DEERE':'91687871000194',
    'MERCADO LIVRE':'03887049000154','CEMIG':'17155730000101','CPFL':'02429144000193',
    'SABESP':'43776517000180','PORTO SEGURO':'61198164000160',
    'BTG PACTUAL':'30306294000145','ENGIE':'03461879000106','EDP':'03983431000103',
    'RAIZEN':'08000610000189','EQUATORIAL':'01417004000174',
    'BANCO DO NORDESTE':'07237373000120','SUL AMERICA':'29978814000187',
    'KINROSS':'15451994000175','COMGAS':'61856691000183','SANEPAR':'76484013000145',
    'RUMO LOGISTICA':'02178351000110','ECORODOVIAS':'03523847000135',
    'MRS LOGISTICA':'01417004000164','CBMM':'60869501000101',
    'SAFRA':'03017677000120','ULTRA':'61460336000162',
}


def inferir_setor(nome: str) -> str:
    n = nome.upper()
    if any(x in n for x in ['BANCO','FINANC','BTG','SEGURO','BRADESC','ITAU','SANTANDER',
                              'BB ','CAIXA','BNDES','SAFRA','DAYCOVAL','SICOOB','SICREDI',
                              'NUBANK','BRASILPREV','B3','UNIBANCO','CREDIT']):
        return 'Financeiro'
    if any(x in n for x in ['ENERGIA','CEMIG','CPFL','ENERGISA','ENGIE','EDP','EQUATORIAL',
                              'NEOENERGI','ENEL','COELBA','CELPE','LIGHT','ELETRO']):
        return 'Energia'
    if any(x in n for x in ['PETRO','SHELL','REPSOL','RAIZEN','VIBRA','PRIO','ULTRA',
                              'COMGAS','IPIRANGA','DISTRIBU']):
        return 'Petróleo e Gás'
    if any(x in n for x in ['VALE','MINER','KINROSS','CBMM','ARCELORMITTAL','VICUNHA',
                              'CSN','NOVELIS','GERDAU','USIMINAS','VOTORANTIM']):
        return 'Mineração e Siderurgia'
    if any(x in n for x in ['TELECOM','VIVO','TIM','CLARO','OI ','TELEFON','ALGAR']):
        return 'Telecomunicações'
    if any(x in n for x in ['AMBEV','HEINEKEN','COCA','PEPSI','NESTL','UNILEVER','JBS',
                              'MARFRIG','BRF','SADIA','PERDIGAO','VIGOR','LATICIN']):
        return 'Alimentos e Bebidas'
    if any(x in n for x in ['TOYOTA','VOLVO','HONDA','FIAT','GM ','FORD','VOLKSWAGEN',
                              'STELLANTIS','JOHN DEERE','CNH','RANDON','MERCEDES','BMW']):
        return 'Automotivo'
    if any(x in n for x in ['SABESP','SANEPAR','COPASA','AEGEA','CEDAE','CAERN','CAGECE']):
        return 'Saneamento'
    if any(x in n for x in ['LOGISTIC','RUMO','MRS','ECORODOVIAS','CCR','ARTERIS','TAG',
                              'NOVA TRANS','CORREIO','LATAM','GOL ','AZUL']):
        return 'Logística'
    if any(x in n for x in ['GOOGLE','MICROSOFT','AMAZON','ORACLE','SAP','TOTVS',
                              'MERCADO LIVRE','IFOOD','UBER','RAPPI']):
        return 'Tecnologia'
    if any(x in n for x in ['SUZANO','PAPEL','CELULOSE','KLABIN','FIBRIA']):
        return 'Papel e Celulose'
    if any(x in n for x in ['WEG','EMBRAER','TUPY','MAHLE','BOSCH','SIEMENS','ABB']):
        return 'Indústria'
    if any(x in n for x in ['MAGAZINE','AMERICANAS','CASAS BAHIA','RIACHUELO','RENNER',
                              'GRUPO PÃO','CARREFOUR','ATACADAO']):
        return 'Varejo'
    if any(x in n for x in ['SAUDE','HAPVIDA','NOTREDAME','UNIMED','AMIL','FLEURY','DASA']):
        return 'Saúde'
    return 'Outros'


def calcular_score(total_lie, total_rouanet, total_incentivos) -> float:
    multiplas = 0.15 if (total_lie > 0 and total_rouanet > 0) else 0.0
    vol = min(math.log10(max(total_incentivos, 1)) / 9, 1.0) * 0.55
    lie = min(math.log10(max(total_lie, 1)) / 8.5, 1.0) * 0.30
    return round(min(multiplas + vol + lie, 1.0), 4)


def buscar_brasilapi(cnpj: str) -> dict:
    cnpj_limpo = re.sub(r'\D', '', cnpj)
    try:
        r = requests.get(f'https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}', timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def main():
    print('=' * 54)
    print('  IMPORTACAO — Empresas Patrocinadoras Reais')
    print('  Fonte: Paineis LIE + Rouanet (Prosas 2022-2025)')
    print('=' * 54)

    # Procurar o CSV base
    base_path = DATA_DIR / 'empresas_patrocinadores_base.csv'
    if not base_path.exists():
        base_path = BASE_DIR / 'empresas_patrocinadores_base.csv'
    if not base_path.exists():
        print('[ERRO] empresas_patrocinadores_base.csv nao encontrado.')
        print('       Coloque o arquivo em data/ ou na raiz do projeto.')
        sys.exit(1)

    df = pd.read_csv(base_path)
    print(f'[OK] Base: {len(df)} grupos empresariais')

    # Filtrar relevantes (>= R$100k historico)
    df = df[pd.to_numeric(df['total_incentivos'], errors='coerce').fillna(0) >= 100_000].copy()
    print(f'[OK] Apos filtro relevancia (>=R$100k): {len(df)}')

    # Enriquecer com BrasilAPI (graciosamente — se falhar, continua sem dados)
    print('\n[INFO] Enriquecendo com BrasilAPI...')
    dados_cnpj = {}
    nomes_na_base = set(df['nome_grupo'].astype(str).str.strip().str.upper())
    para_buscar = [(n, c) for n, c in CNPJ_MAP.items()
                   if n.upper() in nomes_na_base]
    for i, (nome, cnpj) in enumerate(para_buscar, 1):
        print(f'  [{i}/{len(para_buscar)}] {nome}...', end=' ', flush=True)
        d = buscar_brasilapi(cnpj)
        if d:
            dados_cnpj[nome.upper()] = d
            print('OK')
        else:
            print('sem dados')
        time.sleep(0.25)

    # Montar output
    rows = []
    for _, row in df.iterrows():
        nome = str(row['nome_grupo']).strip()
        nome_upper = nome.upper()
        cd = dados_cnpj.get(nome_upper, {})
        uf    = str(cd.get('uf', '') or '').strip()
        razao = str(cd.get('razao_social', '') or '').strip()
        nome_final = razao.title() if razao and len(razao) < 80 else nome.title()
        setor  = inferir_setor(nome)
        regiao = REGIOES.get(uf, 'Nacional' if not uf else 'Outro')

        total_lie = float(row.get('total_lie', 0) or 0)
        total_rou = float(row.get('total_rouanet', 0) or 0)
        total_inc = float(row.get('total_incentivos', 0) or 0)
        potencial = float(row.get('potencial_anual_estimado', 0) or 0)

        faturamento_est = total_inc * 80
        lucro_est       = faturamento_est * 0.10
        score = calcular_score(total_lie, total_rou, total_inc)
        descricao = (
            f"LIE: R${total_lie/1e6:.1f}M | "
            f"Rouanet: R${total_rou/1e6:.1f}M | "
            f"Total historico 2022-2025: R${total_inc/1e6:.1f}M"
        )
        rows.append({
            'nome_empresa':           nome_final,
            'setor':                  setor,
            'uf_sede':                uf or 'N/D',
            'regiao_sede':            regiao,
            'faturamento_anual':      round(faturamento_est),
            'lucro_liquido':          round(lucro_est),
            'potencial_investimento': round(potencial),
            'score_empresa':          score,
            'site':                   '',
            'descricao':              descricao,
        })

    out = pd.DataFrame(rows).sort_values('score_empresa', ascending=False).reset_index(drop=True)
    out.to_csv(DATA_DIR / 'empresas_potenciais.csv', index=False, encoding='utf-8')

    # Copiar base para data/ se ainda nao estiver la
    dest_base = DATA_DIR / 'empresas_patrocinadores_base.csv'
    if not dest_base.exists():
        import shutil
        shutil.copy2(base_path, dest_base)

    print(f'\n{"=" * 54}')
    print(f'  {len(out)} empresas salvas em empresas_potenciais.csv')
    grandes = len(out[out['potencial_investimento'] >= 50_000_000])
    medias  = len(out[(out['potencial_investimento'] >= 5_000_000) &
                      (out['potencial_investimento'] < 50_000_000)])
    print(f'  Grandes (>=R$50M):  {grandes}')
    print(f'  Medias  (>=R$5M):   {medias}')
    print(f'{"=" * 54}')
    print('Execute em seguida:')
    print('  python3 scripts/matching.py')
    print('  python3 scripts/matching_editais.py')
    print('  python3 scripts/gerar_dashboard.py')


if __name__ == '__main__':
    main()
