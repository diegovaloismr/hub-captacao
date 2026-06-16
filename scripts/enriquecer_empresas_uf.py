# -*- coding: utf-8 -*-
"""
Enriquece data/empresas_potenciais.csv com UF e dados reais via BrasilAPI.
Usa o CNPJ_MAP para as principais empresas e atualiza o CSV.
Uso: python3 scripts/enriquecer_empresas_uf.py
"""
import requests, pandas as pd, time, re
from pathlib import Path

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
    'Vale':                    '33592510000154',
    'Itau':                    '60872504000123',
    'Petrobras':               '33000167000101',
    'Nubank':                  '18236120000158',
    'Shell':                   '04882798000177',
    'Bradesco':                '60746948000112',
    'Santander':               '90400888000142',
    'Banco Do Brasil':         '00000000000191',
    'Bndes':                   '33657248000189',
    'B3':                      '09346601000125',
    'Ambev':                   '07526557000100',
    'Vivo':                    '02558157000162',
    'Weg':                     '84429695000111',
    'Arcelormittal':           '60887852000123',
    'Volvo':                   '00197614000500',
    'Toyota':                  '59275792000140',
    'John Deere':              '91687871000194',
    'Mercado Livre':           '03887049000154',
    'Cemig':                   '17155730000101',
    'Cpfl':                    '02429144000193',
    'Sabesp':                  '43776517000180',
    'Porto Seguro':            '61198164000160',
    'Btg Pactual':             '30306294000145',
    'Engie':                   '03461879000106',
    'Edp':                     '03983431000103',
    'Raizen':                  '08000610000189',
    'Equatorial':              '01417004000174',
    'Banco Do Nordeste':       '07237373000120',
    'Sul America':             '29978814000187',
    'Kinross':                 '15451994000175',
    'Comgas':                  '61856691000183',
    'Sanepar':                 '76484013000145',
    'Rumo Logistica':          '02178351000110',
    'Ecorodovias':             '03523847000135',
    'Cbmm':                    '60869501000101',
    'Safra':                   '03017677000120',
    'Suzano':                  '16404287000155',
    'Klabin':                  '89637490000197',
    'Embraer':                 '07715698000118',
    'Gerdau':                  '33611500000119',
    'Caixa Seguros':           '34020354000100',
    'Mapfre':                  '61074175000138',
    'Tokio Marine':            '33164021000104',
    'Energisa':                '07206816000115',
    'Aegea':                   '09027490000190',
    'Ccr':                     '02846056000197',
    'Tim Brasil':              '04206050000180',
    'Google':                  '06990590000123',
    'Microsoft':               '60316817000100',
    'Amazon':                  '15313741000100',
    'Localfrio':               '61088894000155',
    'Brasilprev':              '27251303000187',
    'Prio':                    '22281182000101',
    'Vibra Energia':           '08100474000100',
    'Ultra':                   '61460336000162',
    'Itausa':                  '61532644000115',
    'Multiplan':               '07816890000126',
    'Cyrela':                  '73178600000118',
    'Natura':                  '71673990000177',
    'Raia Drogasil':           '61585865000151',
    'Hapvida':                 '63554067000198',
    'Fleury':                  '60840055000131',
}

def _cnae_para_setor(cnae: str) -> str:
    cnae_u = (cnae or '').upper()
    if any(x in cnae_u for x in ['BANCO','FINANC','SEGURO','CRÉDITO','CREDITO','FUNDO','INVEST']):
        return 'Financeiro'
    if any(x in cnae_u for x in ['ELÉTRIC','ELETRIC','ENERGIA','GÁS','GAS','PETRÓLE','PETROLE','COMBUS']):
        return 'Energia e Petróleo'
    if any(x in cnae_u for x in ['TELECOM','TELEFON','COMUNICAÇ','COMUNICAC']):
        return 'Telecomunicações'
    if any(x in cnae_u for x in ['ALIMENT','BEBIDA','FRIGORIF','LATICIN']):
        return 'Alimentos e Bebidas'
    if any(x in cnae_u for x in ['VEÍCULO','VEICULO','AUTOMOTIV','MÁQUINA','MAQUINA','AERONAVE']):
        return 'Automotivo e Industrial'
    if any(x in cnae_u for x in ['INFORMÁTIC','INFORMATIC','SOFTWAR','TECNOLOG','DADO','INTERNET']):
        return 'Tecnologia'
    if any(x in cnae_u for x in ['SANEAM','ÁGUA','AGUA','ESGOTO']):
        return 'Saneamento'
    if any(x in cnae_u for x in ['LOGÍSTIC','LOGISTIC','TRANSPORT','FERROVIA','RODOVIA','ARMAZENA']):
        return 'Logística'
    if any(x in cnae_u for x in ['MINERAÇ','MINERAC','EXTRAT','SIDERUR','METALUR','MINERIO']):
        return 'Mineração e Siderurgia'
    if any(x in cnae_u for x in ['PAPEL','CELULOSE','MADEIRA','FLORESTA']):
        return 'Papel e Celulose'
    if any(x in cnae_u for x in ['COMÉRCIO','COMERCIO','VAREJO','ATACADO','MAGAZINE','FARMÁCIA']):
        return 'Varejo'
    if any(x in cnae_u for x in ['SAÚDE','SAUDE','HOSPITAL','MÉDIC','MEDIC','FARMAC','DIAGNÓS']):
        return 'Saúde'
    if any(x in cnae_u for x in ['IMÓVEL','IMOVEL','CONSTRU','INCORPOR','LOTEAMEN']):
        return 'Construção e Imóveis'
    if any(x in cnae_u for x in ['COSMÉTIC','COSMETIC','HIGIENE','BELEZA','PERFUM']):
        return 'Cosméticos'
    return None

def buscar_cnpj(cnpj: str, tentativa: int = 1) -> dict:
    cnpj_limpo = re.sub(r'\D', '', cnpj)
    try:
        r = requests.get(
            f'https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}',
            timeout=10,
            headers={'User-Agent': 'HubCaptacao/2.0'}
        )
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 429 and tentativa <= 3:
            sleep = 5 * tentativa
            print(f'    [RATE LIMIT] Aguardando {sleep}s...')
            time.sleep(sleep)
            return buscar_cnpj(cnpj, tentativa + 1)
    except Exception as e:
        print(f'    [ERRO] {e}')
    return {}

def main():
    print('=' * 54)
    print('  ENRIQUECIMENTO — UF e dados reais via BrasilAPI')
    print('=' * 54)

    csv_path = DATA_DIR / 'empresas_potenciais.csv'
    if not csv_path.exists():
        print('[ERRO] empresas_potenciais.csv não encontrado.')
        return

    df = pd.read_csv(csv_path)
    print(f'[OK] {len(df)} empresas carregadas')
    print(f'[INFO] {len(df[df["uf_sede"] == "N/D"])} com UF pendente')

    atualizadas = 0
    for nome_csv, cnpj in CNPJ_MAP.items():
        mask = df['nome_empresa'].str.upper().str.contains(
            nome_csv.upper()[:8], na=False
        )
        if not mask.any():
            continue

        print(f'  [{atualizadas+1}/{len(CNPJ_MAP)}] {nome_csv}...', end=' ', flush=True)
        dados = buscar_cnpj(cnpj)
        if not dados:
            print('sem dados')
            continue

        uf       = dados.get('uf', '')
        cnae     = dados.get('cnae_fiscal_descricao', '')
        situacao = dados.get('descricao_situacao_cadastral', '')
        porte    = dados.get('porte', '')

        if situacao and 'ATIVA' not in situacao.upper():
            print(f'inativa ({situacao})')
            continue

        setor_novo = _cnae_para_setor(cnae)
        if uf:
            df.loc[mask, 'uf_sede']     = uf
            df.loc[mask, 'regiao_sede'] = REGIOES.get(uf, 'Nacional')
        if setor_novo:
            df.loc[mask, 'setor'] = setor_novo

        print(f'OK — UF:{uf} | {setor_novo or "setor mantido"} | {porte}')
        atualizadas += 1
        time.sleep(0.4)

    df.to_csv(csv_path, index=False, encoding='utf-8')

    com_uf = len(df[df['uf_sede'] != 'N/D'])
    print(f'\n{"=" * 54}')
    print(f'  {atualizadas} empresas enriquecidas com BrasilAPI')
    print(f'  {com_uf}/{len(df)} empresas com UF real ({com_uf/len(df)*100:.1f}%)')
    print(f'  CSV atualizado: empresas_potenciais.csv')
    print(f'{"=" * 54}')
    print('Execute em seguida:')
    print('  python3 scripts/matching.py')
    print('  python3 scripts/matching_rouanet.py')

if __name__ == '__main__':
    main()
