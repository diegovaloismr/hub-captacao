# -*- coding: utf-8 -*-
"""
Coleta emendas parlamentares de duas fontes:
  A) Transferegov API (sem autenticação) — dados de transferências especiais
  B) Portal da Transparência /emendas (fallback) — filtrado por 2024-2026

Uso: python3 scripts/importar_emendas.py
"""
import os, re, requests, pandas as pd, time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'

# Carregar .env
env_path = BASE_DIR / '.env'
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            if k.strip() and v.strip() and k.strip() not in os.environ:
                os.environ[k.strip()] = v.strip()

REGIOES = {
    'AC':'Norte','AM':'Norte','AP':'Norte','PA':'Norte','RO':'Norte','RR':'Norte','TO':'Norte',
    'AL':'Nordeste','BA':'Nordeste','CE':'Nordeste','MA':'Nordeste','PB':'Nordeste',
    'PE':'Nordeste','PI':'Nordeste','RN':'Nordeste','SE':'Nordeste',
    'DF':'Centro-Oeste','GO':'Centro-Oeste','MS':'Centro-Oeste','MT':'Centro-Oeste',
    'ES':'Sudeste','MG':'Sudeste','RJ':'Sudeste','SP':'Sudeste',
    'PR':'Sul','RS':'Sul','SC':'Sul',
}

AREAS_INTERESSE = [
    'esporte','cultura','social','educação','educacao','saúde','saude',
    'criança','crianca','juventude','idoso','inclusão','inclusao',
    'diversidade','comunidade','arte','música','musica','teatro',
    'cinema','patrimônio','patrimonio','lazer','assistência','assistencia',
]

def _to_float(val) -> float:
    """Converte valor brasileiro (1.234,56) ou americano para float."""
    if val is None:
        return 0.0
    s = str(val).strip().replace(' ', '')
    if not s or s in ('-', ''):
        return 0.0
    # Formato brasileiro: 1.234,56
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except:
        return 0.0

def _extrair_uf(texto: str) -> str:
    """Extrai UF de textos como 'AMAPÁ (UF)' ou 'Estado de São Paulo - SP'."""
    if not texto:
        return ''
    m = re.search(r'\b([A-Z]{2})\b(?:\s*\(UF\))?', str(texto).upper())
    if m and m.group(1) in REGIOES:
        return m.group(1)
    m = re.search(r'[-\s]([A-Z]{2})$', str(texto).upper().strip())
    if m and m.group(1) in REGIOES:
        return m.group(1)
    return ''

def _tem_area_interesse(texto: str) -> list:
    t = str(texto or '').lower()
    return [a for a in AREAS_INTERESSE if a in t]

# ── FONTE A: Transferegov API ─────────────────────────────────────────────────

def coletar_transferegov(anos: list = [2024, 2025, 2026]) -> list:
    """
    Coleta transferências especiais (emendas parlamentares individuais)
    via API pública do Transferegov — sem autenticação.
    """
    BASE = 'https://api.transferegov.dth.api.gov.br/transferenciasespeciais'
    emendas = []

    print('[A] Coletando emendas via Transferegov API...')

    endpoints = [
        '/emendas_especiais',
        '/parlamentar_especial',
        '/emenda',
        '/transferencia',
    ]

    endpoint_ok = None
    for ep in endpoints:
        try:
            r = requests.get(f'{BASE}{ep}', params={'limit': 1}, timeout=10)
            if r.status_code == 200:
                endpoint_ok = ep
                dados_teste = r.json()
                if dados_teste:
                    primeiro = dados_teste[0] if isinstance(dados_teste, list) else dados_teste
                    print(f'  Endpoint funcionando: {ep}')
                    print(f'  Campos: {list(primeiro.keys())[:10]}')
                break
        except Exception:
            continue

    if endpoint_ok is None:
        try:
            r = requests.get(BASE, params={'limit': 1}, timeout=10)
            if r.status_code == 200:
                dados_teste = r.json()
                if dados_teste:
                    primeiro = dados_teste[0] if isinstance(dados_teste, list) else dados_teste
                    print(f'  Endpoint raiz funcionando')
                    print(f'  Campos: {list(primeiro.keys())[:10]}')
                    endpoint_ok = ''
        except:
            pass

    if endpoint_ok is None:
        print('  [AVISO] Transferegov API indisponível — usando fallback')
        return []

    url = f'{BASE}{endpoint_ok}'

    for ano in anos:
        print(f'  Coletando {ano}...')
        offset = 0
        limite = 1000
        while True:
            try:
                r = requests.get(url, params={
                    'ano_exercicio': f'eq.{ano}',
                    'limit': limite,
                    'offset': offset,
                }, timeout=20)
                if r.status_code != 200:
                    r = requests.get(url, params={
                        'limit': limite,
                        'offset': offset,
                    }, timeout=20)
                if r.status_code != 200:
                    break

                dados = r.json()
                if not dados:
                    break

                antes = len(emendas)
                for item in dados:
                    autor     = str(item.get('nome_autor') or item.get('autor') or item.get('parlamentar') or '')
                    uf_raw    = str(item.get('uf_autor') or item.get('localidade') or item.get('uf') or '')
                    uf        = _extrair_uf(uf_raw) or uf_raw[:2].upper()
                    funcao    = str(item.get('funcao') or item.get('area') or item.get('objeto') or '')
                    valor_emp = _to_float(item.get('valor_empenhado') or item.get('valor') or 0)
                    valor_pag = _to_float(item.get('valor_pago') or 0)
                    valor_aut = _to_float(item.get('valor_autorizado') or item.get('valor_dotacao') or valor_emp)
                    saldo     = max(valor_aut - valor_pag, 0)
                    cod       = str(item.get('codigo_emenda') or item.get('nr_emenda') or item.get('id') or '')

                    if saldo < 50_000:
                        continue
                    areas = _tem_area_interesse(funcao)
                    if not areas:
                        continue

                    emendas.append({
                        'codigo_emenda':      cod,
                        'ano':                item.get('ano_exercicio', ano),
                        'parlamentar':        autor,
                        'tipo_parlamentar':   str(item.get('tipo_autor') or 'Deputado'),
                        'uf_parlamentar':     uf,
                        'regiao_parlamentar': REGIOES.get(uf, ''),
                        'funcao':             funcao[:100],
                        'objeto':             funcao[:200],
                        'valor_autorizado':   valor_aut,
                        'valor_empenhado':    valor_emp,
                        'valor_pago':         valor_pag,
                        'saldo_disponivel':   saldo,
                        'areas_interesse':    '|'.join(areas),
                        'fonte':              'Transferegov',
                        'url':                f'https://portaldatransparencia.gov.br/emendas/{cod}',
                        'is_real':            True,
                    })

                print(f'    {ano} offset {offset}: {len(dados)} itens | relevantes: {len(emendas) - antes}')
                if len(dados) < limite:
                    break
                offset += limite
                time.sleep(0.2)

            except Exception as e:
                print(f'  [ERRO] {ano} offset {offset}: {e}')
                break

    print(f'  [A] Total Transferegov: {len(emendas)} emendas')
    return emendas

# ── FONTE B: Portal da Transparência /emendas (fallback) ─────────────────────

def coletar_portal_transparencia_emendas(anos=[2024, 2025, 2026]) -> list:
    api_key = os.environ.get('PORTAL_TRANSPARENCIA_API_KEY', '')
    if not api_key:
        print('[B] Chave não configurada.')
        return []

    BASE    = 'https://api.portaldatransparencia.gov.br/api-de-dados'
    headers = {'chave-api-dados': api_key}

    # Funções orçamentárias de interesse — código SIAFI
    FUNCOES = {
        '13': 'Cultura',
        '27': 'Desporto e Lazer',
        '12': 'Educação',
        '08': 'Assistência Social',
        '10': 'Saúde',
    }

    emendas = []
    print('[B] Coletando emendas via Portal da Transparência...')

    for ano in anos:
        for cod_func, nome_func in FUNCOES.items():
            pagina = 1
            while pagina <= 50:
                try:
                    r = requests.get(
                        f'{BASE}/emendas',
                        headers=headers,
                        params={'ano': ano, 'codigoFuncao': cod_func, 'pagina': pagina},
                        timeout=15,
                    )
                    if r.status_code != 200:
                        break
                    dados = r.json()
                    if not isinstance(dados, list) or not dados:
                        break

                    for item in dados:
                        valor_emp  = _to_float(item.get('valorEmpenhado', 0))
                        valor_pago = _to_float(item.get('valorPago', 0))
                        valor_rest = _to_float(item.get('valorRestoInscrito', 0))
                        rest_pago  = _to_float(item.get('valorRestoPago', 0))
                        saldo      = max(valor_rest - rest_pago, valor_emp - valor_pago, 0)

                        if saldo < 10_000:
                            continue

                        localidade = str(item.get('localidadeDoGasto') or '')
                        uf         = _extrair_uf(localidade)
                        autor      = str(item.get('nomeAutor') or item.get('autor') or '')
                        cod        = str(item.get('codigoEmenda') or '')

                        emendas.append({
                            'codigo_emenda':      cod,
                            'ano':                ano,
                            'parlamentar':        autor,
                            'tipo_parlamentar':   str(item.get('tipoEmenda') or 'Individual')[:50],
                            'uf_parlamentar':     uf,
                            'regiao_parlamentar': REGIOES.get(uf, ''),
                            'funcao':             nome_func,
                            'objeto':             localidade[:200],
                            'valor_autorizado':   valor_emp,
                            'valor_empenhado':    valor_emp,
                            'valor_pago':         valor_pago,
                            'saldo_disponivel':   saldo,
                            'areas_interesse':    nome_func.lower(),
                            'fonte':              'Portal Transparência',
                            'url':                f'https://portaldatransparencia.gov.br/emendas/{cod}',
                            'is_real':            True,
                        })

                    print(f'  {ano} | {nome_func} | pág {pagina}: {len(dados)} | total: {len(emendas)}')
                    if len(dados) < 15:
                        break
                    pagina += 1
                    time.sleep(0.2)

                except Exception as e:
                    print(f'  [ERRO] {ano}/{nome_func}/pág{pagina}: {e}')
                    break

    # Remover duplicatas por código
    df_tmp = pd.DataFrame(emendas)
    if not df_tmp.empty and 'codigo_emenda' in df_tmp.columns:
        df_tmp = df_tmp.drop_duplicates(subset=['codigo_emenda'])
        emendas = df_tmp.to_dict('records')

    print(f'[B] Total: {len(emendas)} emendas')
    return emendas

# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    ANOS = [2024, 2025, 2026]

    print('=' * 58)
    print('  IMPORTAÇÃO — Emendas Parlamentares (2024-2026)')
    print(f'  Data: {datetime.now().strftime("%d/%m/%Y %H:%M")}')
    print('=' * 58)

    emendas = coletar_transferegov(ANOS)

    if len(emendas) < 100:
        print(f'\n[INFO] Poucos dados do Transferegov ({len(emendas)}). Tentando Portal da Transparência...')
        emendas_b = coletar_portal_transparencia_emendas(ANOS)
        emendas.extend(emendas_b)

    if not emendas:
        print('[AVISO] Nenhuma emenda coletada.')
        pd.DataFrame(columns=[
            'codigo_emenda','ano','parlamentar','tipo_parlamentar','uf_parlamentar',
            'regiao_parlamentar','funcao','objeto','valor_autorizado','valor_empenhado',
            'valor_pago','saldo_disponivel','areas_interesse','fonte','url','is_real'
        ]).to_csv(DATA_DIR / 'emendas_parlamentares.csv', index=False)
        return

    df = pd.DataFrame(emendas)
    df = df.drop_duplicates(subset=['codigo_emenda'], keep='first')

    if 'ano' in df.columns:
        df['ano'] = pd.to_numeric(df['ano'], errors='coerce')
        df = df[df['ano'].isin(ANOS)]

    df = df.sort_values('saldo_disponivel', ascending=False)

    out = DATA_DIR / 'emendas_parlamentares.csv'
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(out, index=False, encoding='utf-8')

    print(f'\n{"=" * 58}')
    print(f'  {len(df)} emendas salvas em emendas_parlamentares.csv')
    print(f'  Anos: {sorted(df["ano"].dropna().astype(int).unique().tolist())}')
    print(f'  UFs com dados: {df["uf_parlamentar"].nunique()} estados')
    print(f'  Parlamentares: {df["parlamentar"].nunique()}')
    print(f'  Saldo total disponível: R$ {df["saldo_disponivel"].sum()/1e6:.1f}M')
    print(f'  Fontes: {df["fonte"].value_counts().to_dict()}')
    print(f'{"=" * 58}')
    print('Execute em seguida:')
    print('  python3 scripts/matching_emendas.py')

if __name__ == '__main__':
    main()
