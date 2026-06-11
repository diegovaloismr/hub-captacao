# -*- coding: utf-8 -*-
"""
Coleta projetos aprovados via Lei de Incentivo ao Esporte (Lei 11.438/2006)
e Lei Rouanet (Lei Cultura) do Portal da Transparencia / SALIC.

Mescla com a base existente (projetos_reais_tratados.csv), marcando
projetos coletados automaticamente como is_real=True e atualizando
status/saldo para o ano corrente.

Execute: python scripts/coletar_projetos.py
"""
import os
import re
import json
import hashlib
import unicodedata
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

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

DATA_DIR  = os.path.join(os.path.dirname(__file__), '..', 'data')
ANO_ATUAL = date.today().year

# Schema minimo esperado no CSV de projetos
SCHEMA_PROJETOS = [
    'nome_projeto', 'proponente', 'modalidade_esportiva', 'uf', 'regiao',
    'ano_aprovacao', 'valor_aprovado', 'valor_captado', 'saldo_disponivel',
    'percentual_captado', 'score_prioridade', 'is_real',
]

MAPA_REGIAO = {
    'AC':'Norte','AP':'Norte','AM':'Norte','PA':'Norte','RO':'Norte','RR':'Norte','TO':'Norte',
    'AL':'Nordeste','BA':'Nordeste','CE':'Nordeste','MA':'Nordeste','PB':'Nordeste',
    'PE':'Nordeste','PI':'Nordeste','RN':'Nordeste','SE':'Nordeste',
    'DF':'Centro-Oeste','GO':'Centro-Oeste','MT':'Centro-Oeste','MS':'Centro-Oeste',
    'ES':'Sudeste','MG':'Sudeste','RJ':'Sudeste','SP':'Sudeste',
    'PR':'Sul','RS':'Sul','SC':'Sul',
}

MAPA_MODALIDADE = {
    'atletismo':'Atletismo', 'natacao':'Natacao', 'natação':'Natacao',
    'judo':'Judo', 'judô':'Judo', 'boxe':'Boxe', 'wrestling':'Wrestling',
    'taekwondo':'Taekwondo', 'karate':'Karate', 'karatê':'Karate',
    'volei':'Volei', 'vôlei':'Volei', 'futebol':'Futebol',
    'basquete':'Basquete', 'basquetebol':'Basquete',
    'handebol':'Handebol', 'tenis':'Tenis', 'tênis':'Tenis',
    'golfe':'Golfe', 'ciclismo':'Ciclismo', 'remo':'Remo',
    'canoagem':'Canoagem', 'iatismo':'Iatismo', 'surfe':'Surfe',
    'skate':'Skate', 'breaking':'Breaking', 'rugby':'Rugby',
    'hipismo':'Hipismo', 'esgrima':'Esgrima', 'tiro':'Tiro',
    'pentatlo':'Pentatlo moderno', 'triathlon':'Triathlon',
    'ginastica artistica':'Ginastica Artistica', 'ginástica artística':'Ginastica Artistica',
    'ginastica ritmica':'Ginastica Ritmica', 'ginástica rítmica':'Ginastica Ritmica',
    'paralimpico':'Paralimpico', 'paralímpico':'Paralimpico',
    'natacao paralimpica':'Natacao Paralimpica',
    'esportes aquaticos':'Esportes Aquaticos',
}


def _clean(text) -> str:
    if not text:
        return ''
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', str(text))).strip()[:300]

def _uf_para_regiao(uf: str) -> str:
    return MAPA_REGIAO.get(str(uf).strip().upper(), 'Nao informado')

def _detectar_modalidade(texto: str) -> str:
    texto_lower = unicodedata.normalize('NFKD', texto.lower())
    texto_lower = ''.join(c for c in texto_lower if not unicodedata.combining(c))
    for chave, valor in MAPA_MODALIDADE.items():
        chave_norm = unicodedata.normalize('NFKD', chave)
        chave_norm = ''.join(c for c in chave_norm if not unicodedata.combining(c))
        if chave_norm in texto_lower:
            return valor
    return 'Esporte'

def _score_prioridade(valor_aprovado: float, valor_captado: float, ano: int) -> float:
    """Score de prioridade baseado em saldo disponivel e recencia."""
    saldo = max(0.0, valor_aprovado - valor_captado)
    sc_saldo = min(1.0, saldo / 1_000_000) * 0.6
    sc_ano   = 1.0 if ano >= ANO_ATUAL else max(0.0, 1.0 - (ANO_ATUAL - ano) * 0.1)
    sc_ano  *= 0.4
    return round(sc_saldo + sc_ano, 4)


# ── Fonte 1: API Beneficios/Incentivos — Lei de Incentivo ao Esporte ──────────

def coletar_lei_incentivo_esporte(api_key: str) -> list:
    """
    Tenta coletar projetos aprovados via Lei de Incentivo ao Esporte
    pelo endpoint de incentivos/beneficios do Portal da Transparencia.
    """
    print('[LIE] Coletando projetos Lei de Incentivo ao Esporte...')
    base    = 'https://api.portaldatransparencia.gov.br/api-de-dados'
    headers = {'chave-api-dados': api_key, 'Accept': 'application/json'}

    # Tentar endpoint de incentivos fiscais esportivos
    endpoints_tentativas = [
        (f'{base}/incentivos', {'codigoAcao': '2109', 'ano': ANO_ATUAL, 'pagina': 1}),
        (f'{base}/beneficios/lei-rouanet', {'ano': ANO_ATUAL, 'pagina': 1}),
        (f'{base}/acoes-orcamentarias', {'codigoAcao': '2109', 'exercicio': ANO_ATUAL, 'pagina': 1}),
    ]

    for url, params in endpoints_tentativas:
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code in (404, 400):
                continue
            resp.raise_for_status()
            dados = resp.json()
            if not isinstance(dados, list):
                dados = dados.get('data', dados.get('content', []))
            if not dados:
                continue

            items = []
            for item in dados:
                nome    = _clean(item.get('nome') or item.get('descricao') or item.get('objeto') or '')
                valor   = float(item.get('valor') or item.get('valorAprovado') or 0)
                captado = float(item.get('valorCaptado') or item.get('valorExecutado') or 0)
                uf      = str(item.get('uf') or item.get('estado') or '').strip().upper()[:2]
                prop    = _clean(item.get('proponente') or item.get('beneficiario') or item.get('nome') or '')
                ano     = int(item.get('ano') or item.get('exercicio') or ANO_ATUAL)

                if not nome:
                    continue

                modalidade = _detectar_modalidade(nome)
                saldo      = max(0.0, valor - captado)
                perc       = round((captado / valor * 100), 1) if valor > 0 else 0.0
                score      = _score_prioridade(valor, captado, ano)

                items.append({
                    'nome_projeto':        nome[:150],
                    'proponente':          prop[:100] or nome[:60],
                    'modalidade_esportiva': modalidade,
                    'uf':                  uf or 'BR',
                    'regiao':              _uf_para_regiao(uf),
                    'ano_aprovacao':       ano,
                    'valor_aprovado':      round(valor, 2),
                    'valor_captado':       round(captado, 2),
                    'saldo_disponivel':    round(saldo, 2),
                    'percentual_captado':  perc,
                    'score_prioridade':    score,
                    'is_real':             True,
                })

            print('    -> ' + str(len(items)) + ' projetos via ' + url.split('/')[-1])
            return items

        except Exception as e:
            print('    [AVISO] ' + url + ': ' + str(e))

    return []


# ── Fonte 2: SALIC API (Lei Rouanet — cultura/esporte) ───────────────────────

def coletar_salic(ano: int = None) -> list:
    """
    Coleta projetos aprovados via SALIC (Lei Rouanet) com foco em
    esporte, cultura corporal e modalidades olimpicas.
    API publica, sem autenticacao.
    """
    if ano is None:
        ano = ANO_ATUAL
    print('[SALIC] Coletando projetos Lei Rouanet (' + str(ano) + ')...')

    base = 'http://api.salic.cultura.gov.br/v1'
    # Segmentos relacionados a esporte/cultura corporal
    segmentos_esporte = ['10', '11', '12', '52', '53']

    items = []
    for segmento in segmentos_esporte:
        try:
            resp = requests.get(
                f'{base}/projetos/',
                params={
                    'ano_projeto': ano,
                    'segmento': segmento,
                    'situacao': 'aprovado',
                    'limit': 50,
                    'offset': 0,
                    'format': 'json',
                },
                timeout=15,
            )
            if resp.status_code in (404, 400, 500):
                continue
            resp.raise_for_status()
            dados = resp.json()
            projetos = dados.get('_embedded', {}).get('projetos', [])

            for p in projetos:
                nome    = _clean(p.get('nome') or p.get('titulo') or '')
                prop    = _clean(p.get('proponente', {}).get('nome') or '')
                valor   = float(p.get('valor_solicitado') or p.get('valor_aprovado') or 0)
                captado = float(p.get('valor_captado') or 0)
                uf      = str(p.get('UF') or p.get('uf') or '').strip().upper()[:2]
                ano_p   = int(p.get('ano_projeto') or ano)

                if not nome:
                    continue

                modalidade = _detectar_modalidade(nome)
                saldo      = max(0.0, valor - captado)
                perc       = round((captado / valor * 100), 1) if valor > 0 else 0.0
                score      = _score_prioridade(valor, captado, ano_p)

                items.append({
                    'nome_projeto':        nome[:150],
                    'proponente':          prop[:100] or nome[:60],
                    'modalidade_esportiva': modalidade,
                    'uf':                  uf or 'BR',
                    'regiao':              _uf_para_regiao(uf),
                    'ano_aprovacao':       ano_p,
                    'valor_aprovado':      round(valor, 2),
                    'valor_captado':       round(captado, 2),
                    'saldo_disponivel':    round(saldo, 2),
                    'percentual_captado':  perc,
                    'score_prioridade':    score,
                    'is_real':             True,
                })

        except Exception as e:
            print('    [AVISO] SALIC segmento ' + segmento + ': ' + str(e))

    if items:
        print('[SALIC] -> ' + str(len(items)) + ' projetos coletados')
    else:
        print('[SALIC] -> 0 projetos (API indisponivel ou sem dados para ' + str(ano) + ')')
    return items


# ── Fonte 3: Transferegov — projetos vigentes ────────────────────────────────

def coletar_transferegov(api_key: str) -> list:
    """Busca propostas vigentes no Transferegov com foco em esporte."""
    print('[TGV] Coletando propostas Transferegov...')
    base    = 'https://api.portaldatransparencia.gov.br/api-de-dados'
    headers = {'chave-api-dados': api_key, 'Accept': 'application/json'}
    try:
        resp = requests.get(
            f'{base}/transferencias-especiais',
            headers=headers,
            params={'pagina': 1, 'situacao': 'vigente'},
            timeout=15,
        )
        if resp.status_code in (404, 400):
            return []
        resp.raise_for_status()
        dados = resp.json()
        if not isinstance(dados, list):
            dados = dados.get('data', [])

        items = []
        palavras_esporte = ['esporte', 'atleta', 'olimp', 'sport', 'futebol',
                            'natacao', 'ginastica', 'lutas', 'modalidade']
        for item in dados:
            descricao = str(item.get('objeto') or item.get('descricao') or '').lower()
            desc_norm = unicodedata.normalize('NFKD', descricao)
            desc_norm = ''.join(c for c in desc_norm if not unicodedata.combining(c))
            if not any(p in desc_norm for p in palavras_esporte):
                continue

            nome    = _clean(item.get('objeto') or item.get('descricao') or '')[:150]
            valor   = float(item.get('valor') or 0)
            uf      = str(item.get('uf') or '').strip().upper()[:2]
            prop    = _clean(item.get('favorecido') or item.get('beneficiario') or '')

            items.append({
                'nome_projeto':        nome,
                'proponente':          prop[:100] or nome[:60],
                'modalidade_esportiva': _detectar_modalidade(nome),
                'uf':                  uf or 'BR',
                'regiao':              _uf_para_regiao(uf),
                'ano_aprovacao':       ANO_ATUAL,
                'valor_aprovado':      round(valor, 2),
                'valor_captado':       0.0,
                'saldo_disponivel':    round(valor, 2),
                'percentual_captado':  0.0,
                'score_prioridade':    _score_prioridade(valor, 0, ANO_ATUAL),
                'is_real':             True,
            })

        print('[TGV] -> ' + str(len(items)) + ' projetos esportivos encontrados')
        return items
    except Exception as e:
        print('[AVISO] Transferegov: ' + str(e))
        return []


# ── Merge com base existente ──────────────────────────────────────────────────

def atualizar_projetos() -> pd.DataFrame:
    agora = datetime.now()
    print('=========================================')
    print('  HUB DE CAPTACAO — Atualizacao de Projetos')
    print('  Data: ' + agora.strftime('%d/%m/%Y') + '  Hora: ' + agora.strftime('%H:%M'))
    print('=========================================')

    api_key = os.environ.get('PORTAL_TRANSPARENCIA_API_KEY', '')

    # Carregar base existente
    proj_path = os.path.join(DATA_DIR, 'projetos_reais_tratados.csv')
    df_existente = pd.DataFrame(columns=SCHEMA_PROJETOS)
    if os.path.exists(proj_path):
        try:
            df_existente = pd.read_csv(proj_path)
            print('[BASE] ' + str(len(df_existente)) + ' projetos na base existente')
        except Exception as e:
            print('[AVISO] Nao foi possivel ler base existente: ' + str(e))

    novos: list = []

    # Fonte 1: Lei de Incentivo ao Esporte (requer chave)
    if api_key:
        lie = coletar_lei_incentivo_esporte(api_key)
        novos.extend(lie)
    else:
        print('[LIE] PORTAL_TRANSPARENCIA_API_KEY nao configurada — pulado')

    # Fonte 2: SALIC (publico)
    salic_atual = coletar_salic(ANO_ATUAL)
    novos.extend(salic_atual)
    # Tambem busca ano anterior como complemento
    salic_ant = coletar_salic(ANO_ATUAL - 1)
    novos.extend(salic_ant)

    # Fonte 3: Transferegov (requer chave)
    if api_key:
        tgv = coletar_transferegov(api_key)
        novos.extend(tgv)

    if novos:
        df_novos = pd.DataFrame(novos)

        # Garantir colunas
        for col in SCHEMA_PROJETOS:
            if col not in df_novos.columns:
                df_novos[col] = ''

        # Mesclar com existente — novos substituem por nome_projeto normalizado
        def _norm(t):
            t = unicodedata.normalize('NFKD', str(t).lower())
            return ''.join(c for c in t if not unicodedata.combining(c)).strip()[:80]

        df_existente['_norm'] = df_existente['nome_projeto'].apply(_norm)
        df_novos['_norm']     = df_novos['nome_projeto'].apply(_norm)

        # Remover existentes que serao substituidos
        nomes_novos = set(df_novos['_norm'])
        df_mantidos = df_existente[~df_existente['_norm'].isin(nomes_novos)].copy()

        df_final = pd.concat([df_novos, df_mantidos], ignore_index=True)
        df_final = df_final.drop(columns=['_norm'], errors='ignore')

        # Garantir schema
        for col in SCHEMA_PROJETOS:
            if col not in df_final.columns:
                df_final[col] = ''
        df_final = df_final[SCHEMA_PROJETOS]

        # Ordenar por score
        df_final['score_prioridade'] = pd.to_numeric(df_final['score_prioridade'], errors='coerce').fillna(0)
        df_final = df_final.sort_values('score_prioridade', ascending=False).reset_index(drop=True)

        df_final.to_csv(proj_path, index=False)
        total_reais = int(df_final['is_real'].astype(str).str.lower().eq('true').sum())
        print()
        print('[OK] ' + str(len(df_final)) + ' projetos salvos (' + str(total_reais) + ' reais + ' + str(len(df_final) - total_reais) + ' base fixa)')
        print('     Arquivo: ' + proj_path)
        return df_final
    else:
        print()
        print('[AVISO] Nenhuma fonte retornou projetos novos. Base existente mantida sem alteracoes.')
        print('[DICA] Configure PORTAL_TRANSPARENCIA_API_KEY no arquivo .env para ativar fontes governamentais.')
        return df_existente


if __name__ == '__main__':
    atualizar_projetos()
