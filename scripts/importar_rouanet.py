# -*- coding: utf-8 -*-
"""
Importa projetos da Lei Rouanet via API SALIC.
Uso: python3 scripts/importar_rouanet.py
"""
import requests, pandas as pd, time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'
API_BASE = 'https://api.salic.cultura.gov.br/api/v1'

REGIOES = {
    'AC':'Norte','AM':'Norte','AP':'Norte','PA':'Norte','RO':'Norte','RR':'Norte','TO':'Norte',
    'AL':'Nordeste','BA':'Nordeste','CE':'Nordeste','MA':'Nordeste','PB':'Nordeste',
    'PE':'Nordeste','PI':'Nordeste','RN':'Nordeste','SE':'Nordeste',
    'DF':'Centro-Oeste','GO':'Centro-Oeste','MS':'Centro-Oeste','MT':'Centro-Oeste',
    'ES':'Sudeste','MG':'Sudeste','RJ':'Sudeste','SP':'Sudeste',
    'PR':'Sul','RS':'Sul','SC':'Sul',
}

def coletar_projetos_salic(max_paginas: int = 200) -> list:
    projetos = []
    hoje = datetime.now()

    for pagina in range(max_paginas):
        offset = pagina * 100
        try:
            r = requests.get(f'{API_BASE}/projetos', params={
                'situacao': 'aprovado',
                'limit': 100,
                'offset': offset,
                'format': 'json',
            }, timeout=20)
            r.raise_for_status()
            data = r.json()
            items = data.get('_embedded', {}).get('projetos', [])
            if not items:
                break

            for item in items:
                val_aprovado = float(item.get('valor_aprovado') or 0)
                val_captado  = float(item.get('valor_captado') or 0)
                saldo = val_aprovado - val_captado
                if saldo <= 0:
                    continue

                dt_fim_str = (item.get('data_termino') or '')[:10]
                try:
                    dt_fim = datetime.strptime(dt_fim_str, '%Y-%m-%d') if dt_fim_str else None
                    if dt_fim and dt_fim < hoje:
                        continue
                    dias_rest = (dt_fim - hoje).days if dt_fim else 365
                except Exception:
                    dias_rest = 365
                    dt_fim_str = ''

                uf = (item.get('UF') or '').strip().upper()
                ano_raw = str(item.get('ano_projeto') or '')
                ano = int('20' + ano_raw) if len(ano_raw) == 2 else (int(ano_raw) if ano_raw.isdigit() else 2024)

                if dias_rest <= 30:    prazo_s = 1.0
                elif dias_rest <= 90:  prazo_s = 0.85
                elif dias_rest <= 180: prazo_s = 0.70
                else:                  prazo_s = 0.55

                if val_aprovado <= 500_000:     val_s = 1.0
                elif val_aprovado <= 1_000_000: val_s = 0.8
                elif val_aprovado <= 3_000_000: val_s = 0.6
                else:                           val_s = 0.4

                score = round(prazo_s * 0.50 + val_s * 0.50, 4)

                projetos.append({
                    'processo':             str(item.get('PRONAC') or ''),
                    'proponente':           str(item.get('proponente') or ''),
                    'nome_projeto':         str(item.get('nome') or '')[:200],
                    'sli':                  '',
                    'segmento_cultural':    str(item.get('segmento') or ''),
                    'cnpj':                 str(item.get('cgccpf') or ''),
                    'municipio':            str(item.get('municipio') or ''),
                    'uf':                   uf,
                    'regiao':               REGIOES.get(uf, 'Nacional'),
                    'valor_aprovado':       val_aprovado,
                    'valor_captado':        val_captado,
                    'saldo_disponivel':     saldo,
                    'percentual_captado':   round(val_captado / val_aprovado * 100, 1) if val_aprovado else 0,
                    'data_publicacao':      str(item.get('data_inicio') or ''),
                    'data_inicio_captacao': str(item.get('data_inicio') or ''),
                    'data_fim_captacao':    dt_fim_str,
                    'ano_aprovacao':        ano,
                    'status':               'Captando',
                    'score_prioridade':     score,
                    'lei':                  'Rouanet',
                    'area':                 'Cultura',
                    'is_real':              True,
                })

            total = data.get('total', 0)
            print(f'  Página {pagina+1}: {len(items)} itens | coletados: {len(projetos)} | total API: {total}')
            if offset + 100 >= total:
                break
            time.sleep(0.3)

        except Exception as e:
            print(f'  [ERRO] Página {pagina+1}: {e}')
            time.sleep(2)
            continue

    return projetos

def main():
    print('=' * 54)
    print('  IMPORTAÇÃO — Lei Rouanet (API SALIC)')
    print(f'  Data: {datetime.now().strftime("%d/%m/%Y %H:%M")}')
    print('=' * 54)

    projetos = coletar_projetos_salic()

    if not projetos:
        print('[ERRO] Nenhum projeto coletado.')
        return

    df = pd.DataFrame(projetos)
    df = df[df['score_prioridade'] >= 0.45]
    df = df[df['saldo_disponivel'] >= 50_000]
    df = df.sort_values('score_prioridade', ascending=False)

    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / 'projetos_rouanet.csv'
    df.to_csv(out, index=False, encoding='utf-8')

    print(f'\n{"=" * 54}')
    print(f'  {len(df)} projetos salvos em projetos_rouanet.csv')
    print(f'  UFs: {df["uf"].nunique()} | Segmentos: {df["segmento_cultural"].nunique()}')
    print(f'  Valor total em captação: R$ {df["saldo_disponivel"].sum()/1e9:.2f}B')
    print(f'{"=" * 54}')
    print('Execute em seguida:')
    print('  python3 scripts/matching_rouanet.py')

if __name__ == '__main__':
    main()
