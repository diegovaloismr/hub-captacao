# -*- coding: utf-8 -*-
"""
Coleta oportunidades de captacao varrendo portais de noticias (RSS) em tempo real.

Fontes (ordem de execucao):
  N  — Varredura RSS de 18 portais de captacao (sempre ativa, sem chave)
  IA — Extracao estruturada com Claude Haiku (opcional, requer ANTHROPIC_API_KEY)
  PT — Portal da Transparencia: convenios e termos MROSC (requer PORTAL_TRANSPARENCIA_API_KEY)

Sem nenhuma chave configurada, o sistema ainda coleta noticias reais dos RSS
e aplica extracao por regex/palavras-chave para estruturar os dados.
"""
import os
import re
import json
import hashlib
import unicodedata
from datetime import date, datetime, timedelta
from typing import Optional

import feedparser
import pandas as pd
import requests

# Carregar variaveis do arquivo .env se existir
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

LIMITE_NOTICIAS_POR_PORTAL = 50

# Palavras-chave que indicam que uma noticia pode conter uma oportunidade de captacao
PALAVRAS_OPORTUNIDADE = [
    'edital', 'chamada', 'chamada publica', 'premio', 'premios',
    'fundo', 'financiamento', 'captacao', 'captacao de recursos',
    'recurso', 'apoio', 'incentivo', 'selecao', 'inscricao',
    'inscricoes abertas', 'oportunidade', 'patrocinio', 'bolsa',
    'grant', 'convocatoria', 'programa de apoio', 'fomento',
    'beneficio', 'subvencao', 'lei de incentivo', 'salic', 'transferegov',
    'aberto', 'abertas', 'inscreva', 'participe', 'submeta',
    'projeto', 'proposta', 'investimento social', 'apoio financeiro',
    'parceria', 'convenio', 'termo de fomento', 'mrosc',
    'contemplados', 'aprovados', 'selecionados',
]

PALAVRAS_ALTA_CONFIANCA = [
    'edital', 'chamada publica', 'inscricoes abertas', 'inscreva-se',
    'premio', 'fundo', 'patrocinio', 'bolsa', 'financiamento',
    'apoio a projetos', 'selecao de projetos', 'captacao',
    'programa de apoio', 'fomento', 'convocatoria',
]

PORTAIS_NOTICIAS = [
    # Terceiro setor e captacao
    {'nome': 'GIFE',                      'rss': 'https://gife.org.br/feed/',                                                             'area_default': 'Investimento Social|Filantropia'},
    {'nome': 'Filantropia.org.br',        'rss': 'https://filantropia.org.br/feed/',                                                      'area_default': 'Terceiro Setor|Filantropia'},
    {'nome': 'Instituto Filantropia',     'rss': 'https://www.institutofilantropia.org.br/feed/',                                         'area_default': 'Terceiro Setor|Editais'},
    {'nome': 'Observatorio 3o Setor',     'rss': 'https://observatorio3setor.org.br/category/noticias/editais/feed/',                     'area_default': 'Terceiro Setor|OSC'},
    {'nome': 'Captadores.com.br',         'rss': 'https://captadores.com.br/feed/',                                                       'area_default': 'Captacao de Recursos|Editais'},
    {'nome': 'Agencia Sebrae',            'rss': 'https://agenciasebrae.com.br/feed/',                                                    'area_default': 'Empreendedorismo|PME|Editais'},
    # Governo federal - esporte e cultura
    {'nome': 'Gov.br Esporte',            'rss': 'https://www.gov.br/esporte/pt-br/assuntos/noticias/RSS',                                'area_default': 'Esporte|Governo Federal'},
    {'nome': 'Gov.br Cultura',            'rss': 'https://www.gov.br/cultura/pt-br/assuntos/noticias/RSS',                                'area_default': 'Cultura|Governo Federal'},
    {'nome': 'Fundo Nacional do Esporte', 'rss': 'https://www.gov.br/esporte/pt-br/acoes-e-programas/fundo-nacional-do-esporte/RSS',      'area_default': 'Esporte|Fundo Nacional|Governo Federal'},
    {'nome': 'Fundo Nacional de Cultura', 'rss': 'https://www.gov.br/cultura/pt-br/assuntos/noticias/RSS',                                'area_default': 'Cultura|Fundo Nacional|Governo Federal'},
    {'nome': 'MDH',                       'rss': 'https://www.gov.br/mdh/pt-br/assuntos/noticias/RSS',                                    'area_default': 'Crianca|Adolescente|Direitos|Governo Federal'},
    {'nome': 'Transferegov',              'rss': 'https://www.gov.br/transferegov/pt-br/noticias/RSS',                                    'area_default': 'OSC|Chamada Publica|Parceria|Governo Federal'},
    # Fundacoes empresariais
    {'nome': 'Fundacao Lemann',           'rss': 'https://fundacaolemann.org.br/feed',                                                    'area_default': 'Educacao|Lideranca|Instituto Empresarial'},
    {'nome': 'Itau Social',              'rss': 'https://www.itausocial.org.br/feed/',                                                   'area_default': 'Educacao|Social|Instituto Empresarial'},
    {'nome': 'Instituto Unibanco',        'rss': 'https://www.institutounibanco.org.br/feed/',                                            'area_default': 'Educacao|Juventude|Instituto Empresarial'},
    {'nome': 'Fundacao Roberto Marinho',  'rss': 'https://frm.org.br/feed/',                                                              'area_default': 'Educacao|Cultura|Instituto Empresarial'},
    {'nome': 'Instituto Votorantim',      'rss': 'https://www.institutovotorantim.org.br/feed/',                                          'area_default': 'Desenvolvimento Local|Social|Instituto Empresarial'},
    {'nome': 'Instituto Gerdau',          'rss': 'https://www.institutogerdau.org.br/feed/',                                              'area_default': 'Educacao|Empreendedorismo|Instituto Empresarial'},
]

SCHEMA = [
    'id', 'fonte', 'titulo', 'descricao', 'financiador',
    'valor_max', 'data_encerramento', 'dias_restantes', 'status',
    'areas_tematicas', 'uf_elegivel', 'url_original', 'is_real',
]


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]

def _dias_restantes(data_enc: str) -> int:
    if not data_enc:
        return -1
    try:
        dt = datetime.strptime(str(data_enc)[:10], '%Y-%m-%d').date()
        return (dt - date.today()).days
    except ValueError:
        return -1

def _status(dias: int) -> str:
    return 'ativo' if dias > 0 or dias == -1 else 'encerrado'

def _clean(text: str) -> str:
    if not text:
        return ''
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', str(text))).strip()[:500]

def _normalizar_titulo(texto: str) -> str:
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r'[^a-z0-9 ]', '', texto)
    return re.sub(r'\s+', ' ', texto).strip()[:80]

_STOPWORDS = {
    'a','o','as','os','e','de','da','do','das','dos','em','no','na','nos','nas',
    'para','por','com','sem','ao','aos','um','uma','que','se','ou',
    'abre','lanca','publica','divulga','anuncia','oferece','seleciona',
    'novo','nova','mais','ja','esta','sera','sao','foi','selecionados',
}

def _fingerprint(titulo: str) -> str:
    norm = _normalizar_titulo(titulo)
    palavras = [p for p in norm.split() if p not in _STOPWORDS and len(p) > 3]
    palavras.sort()
    return ' '.join(palavras[:6])

def _extrair_valor(texto: str) -> str:
    """Extrai valor monetario do texto via regex."""
    m = re.search(r'R\$\s*([\d.,]+(?:\s*milh[oa]o|mil)?)', texto, re.IGNORECASE)
    if not m:
        return ''
    raw = m.group(1).strip().lower()
    try:
        if 'milh' in raw:
            num = float(re.sub(r'[^\d,.]', '', raw).replace(',', '.'))
            return str(int(num * 1_000_000))
        elif 'mil' in raw:
            num = float(re.sub(r'[^\d,.]', '', raw).replace(',', '.'))
            return str(int(num * 1_000))
        else:
            num = float(raw.replace('.', '').replace(',', '.'))
            return str(int(num))
    except (ValueError, AttributeError):
        return ''

def _extrair_data_encerramento(texto: str) -> str:
    """Tenta extrair data de encerramento do texto."""
    # Padrao dd/mm/yyyy
    for m in re.finditer(r'(\d{2}/\d{2}/\d{4})', texto):
        try:
            dt = datetime.strptime(m.group(1), '%d/%m/%Y').date()
            if dt >= date.today():
                return dt.isoformat()
        except ValueError:
            continue
    # Padrao yyyy-mm-dd
    for m in re.finditer(r'(\d{4}-\d{2}-\d{2})', texto):
        try:
            dt = datetime.strptime(m.group(1), '%Y-%m-%d').date()
            if dt >= date.today():
                return dt.isoformat()
        except ValueError:
            continue
    return ''

def _extrair_uf(texto: str) -> str:
    """Detecta UF mencionada no texto."""
    ufs = ['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS',
           'MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC',
           'SP','SE','TO']
    encontradas = [uf for uf in ufs if re.search(r'\b' + uf + r'\b', texto)]
    if not encontradas:
        return 'Nacional'
    if len(encontradas) > 3:
        return 'Nacional'
    return '|'.join(encontradas)


# ── Varredura RSS sem IA ──────────────────────────────────────────────────────

def coletar_noticias_portais(limite_por_portal: int = LIMITE_NOTICIAS_POR_PORTAL) -> list:
    """Varre todos os RSS e retorna noticias brutas filtradas por palavras-chave."""
    noticias = []
    for portal in PORTAIS_NOTICIAS:
        print('[N] Varrendo ' + portal['nome'] + '...')
        try:
            feed = feedparser.parse(portal['rss'])
            count = 0
            for entry in feed.entries[:limite_por_portal]:
                link = entry.get('link', '')
                if not link:
                    continue
                titulo = _clean(entry.get('title', ''))
                resumo = _clean(entry.get('summary', ''))
                texto_lower = (titulo + ' ' + resumo).lower()
                texto_lower_sem_acento = unicodedata.normalize('NFKD', texto_lower)
                texto_lower_sem_acento = ''.join(
                    c for c in texto_lower_sem_acento if not unicodedata.combining(c)
                )
                if not any(p in texto_lower_sem_acento for p in PALAVRAS_OPORTUNIDADE):
                    continue
                noticias.append({
                    'portal':       portal['nome'],
                    'area_default': portal['area_default'],
                    'titulo':       titulo,
                    'resumo':       resumo,
                    'link':         link,
                    'publicado':    entry.get('published', ''),
                })
                count += 1
            if count:
                print('    -> ' + str(count) + ' noticias relevantes')
        except Exception as e:
            print('    [AVISO] ' + portal['nome'] + ' indisponivel: ' + str(e))
    print('[N] Total bruto: ' + str(len(noticias)) + ' noticias para processar')
    return noticias


def extrair_edital_por_regex(noticia: dict) -> dict:
    """
    Extrai dados estruturados de uma noticia usando regex e heuristicas.
    Nao requer chave de API.
    """
    texto = noticia['titulo'] + ' ' + noticia['resumo']

    valor_max     = _extrair_valor(texto)
    data_enc      = _extrair_data_encerramento(texto)
    uf_elegivel   = _extrair_uf(texto)
    dias          = _dias_restantes(data_enc)

    # Tentar extrair financiador do titulo
    financiador = noticia['portal']
    padroes_financ = [
        r'(?:pela?|do|da|pelo|pela)\s+([A-Z][a-zA-ZÀ-ÿ\s]{4,40}?)(?:\s+abre|\s+lanca|\s+publica|\s+seleciona|\.|,)',
        r'^([A-Z][a-zA-ZÀ-ÿ\s]{3,35}?)(?:\s+abre|\s+lanca|\s+oferece|\s+seleciona)',
    ]
    for padrao in padroes_financ:
        m = re.search(padrao, noticia['titulo'])
        if m:
            candidato = m.group(1).strip()
            if 3 < len(candidato) < 50:
                financiador = candidato
                break

    return {
        'id':               _make_id(noticia['link']),
        'fonte':            noticia['portal'],
        'titulo':           noticia['titulo'][:200],
        'descricao':        noticia['resumo'][:500],
        'financiador':      financiador,
        'valor_max':        valor_max,
        'data_encerramento': data_enc,
        'dias_restantes':   dias,
        'status':           _status(dias),
        'areas_tematicas':  noticia['area_default'],
        'uf_elegivel':      uf_elegivel,
        'url_original':     noticia['link'],
        'is_real':          True,
    }


def extrair_edital_com_ia(noticia: dict, api_key: str) -> Optional[dict]:
    """Usa Claude Haiku para extrair dados estruturados. Retorna None se nao for edital."""
    prompt = (
        'Voce e um assistente especializado em captacao de recursos.\n\n'
        'Analise a noticia e extraia informacoes sobre editais, chamadas, premios '
        'ou oportunidades de financiamento.\n\n'
        'NOTICIA:\nTitulo: ' + noticia['titulo'] + '\n'
        'Resumo: ' + noticia['resumo'] + '\n'
        'Fonte: ' + noticia['portal'] + '\n\n'
        'Responda APENAS com JSON (sem markdown):\n'
        '{"contem_edital": true/false, '
        '"titulo_edital": "...", '
        '"financiador": "...", '
        '"valor_max": "apenas numeros ou vazio", '
        '"data_encerramento": "YYYY-MM-DD ou vazio", '
        '"areas_tematicas": "area1|area2", '
        '"uf_elegivel": "UF ou Nacional", '
        '"url_edital": "URL"}\n\n'
        'Se nao contiver edital: {"contem_edital": false}'
    )
    try:
        resp = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            json={
                'model': 'claude-haiku-4-5-20251001',
                'max_tokens': 400,
                'messages': [{'role': 'user', 'content': prompt}],
            },
            timeout=20,
        )
        resp.raise_for_status()
        texto = resp.json()['content'][0]['text'].strip()
        texto = texto.replace('```json', '').replace('```', '').strip()
        dados = json.loads(texto)

        if not dados.get('contem_edital'):
            return None

        dias = _dias_restantes(dados.get('data_encerramento', ''))
        return {
            'id':                _make_id(dados.get('url_edital', noticia['link'])),
            'fonte':             noticia['portal'],
            'titulo':            dados.get('titulo_edital', noticia['titulo'])[:200],
            'descricao':         noticia['resumo'][:500],
            'financiador':       dados.get('financiador', noticia['portal']),
            'valor_max':         str(dados.get('valor_max', '')),
            'data_encerramento': dados.get('data_encerramento', ''),
            'dias_restantes':    dias,
            'status':            _status(dias),
            'areas_tematicas':   dados.get('areas_tematicas', noticia['area_default']),
            'uf_elegivel':       dados.get('uf_elegivel', 'Nacional'),
            'url_original':      dados.get('url_edital', noticia['link']),
            'is_real':           True,
        }
    except Exception:
        return None


# ── Portal da Transparencia: convenios ───────────────────────────────────────

def coletar_portal_transparencia() -> list:
    api_key = os.environ.get('PORTAL_TRANSPARENCIA_API_KEY', '')
    if not api_key:
        print('[PT] PORTAL_TRANSPARENCIA_API_KEY nao configurada — pulado.')
        return []

    print('[PT] Coletando convenios do Portal da Transparencia...')
    base    = 'https://api.portaldatransparencia.gov.br/api-de-dados'
    headers = {'chave-api-dados': api_key, 'Accept': 'application/json'}
    try:
        resp = requests.get(
            f'{base}/convenios',
            headers=headers,
            params={'pagina': 1},
            timeout=15,
        )
        resp.raise_for_status()
        dados = resp.json()
        if not isinstance(dados, list):
            dados = dados.get('data', dados.get('convenios', []))

        items = []
        for c in dados:
            numero  = str(c.get('numero', ''))
            objeto  = _clean(str(c.get('objeto', '')))
            valor   = c.get('valor') or c.get('valorTotal') or ''
            dt_fim  = str(c.get('dataVigenciaFim') or c.get('dataFim') or '')[:10]
            conced  = c.get('concedente') or {}
            conv    = c.get('convenente') or {}
            financ  = str(conced.get('nome') or 'Governo Federal')
            uf      = str(conv.get('uf') or '')
            dias    = _dias_restantes(dt_fim)
            items.append({
                'id':                f'ptransp-{numero}',
                'fonte':             'Portal da Transparencia',
                'titulo':            f'Convenio {numero}',
                'descricao':         objeto,
                'financiador':       financ,
                'valor_max':         str(valor) if valor else '',
                'data_encerramento': dt_fim,
                'dias_restantes':    dias,
                'status':            _status(dias),
                'areas_tematicas':   'Convenios|Governo Federal',
                'uf_elegivel':       uf or 'Nacional',
                'url_original':      f'https://portaldatransparencia.gov.br/convenios/{numero}',
                'is_real':           True,
            })
        print('    -> ' + str(len(items)) + ' convenios coletados')
        return items
    except Exception as e:
        print('[AVISO] Portal da Transparencia indisponivel: ' + str(e))
        return []


def coletar_termos_fomento() -> list:
    """Coleta Termos de Fomento MROSC (Lei 13.019/2014)."""
    api_key = os.environ.get('PORTAL_TRANSPARENCIA_API_KEY', '')
    if not api_key:
        print('[PT] PORTAL_TRANSPARENCIA_API_KEY nao configurada — MROSC pulado.')
        return []

    print('[PT] Coletando Termos de Fomento MROSC...')
    base    = 'https://api.portaldatransparencia.gov.br/api-de-dados'
    headers = {'chave-api-dados': api_key, 'Accept': 'application/json'}

    try:
        resp = requests.get(f'{base}/transferencias-voluntarias', headers=headers,
                            params={'pagina': 1}, timeout=15)
        if resp.status_code == 404:
            print('[PT] Endpoint transferencias-voluntarias nao encontrado.')
            return []
        resp.raise_for_status()
        dados = resp.json()
        if not isinstance(dados, list):
            dados = dados.get('data', [])
        items = []
        for c in dados:
            numero = str(c.get('numero', c.get('id', '')))
            objeto = _clean(str(c.get('objeto', c.get('descricao', ''))))
            valor  = c.get('valor') or c.get('valorTotal') or ''
            dt_fim = str(c.get('dataVigenciaFim') or c.get('dataFim') or '')[:10]
            conced = c.get('concedente') or {}
            conv   = c.get('convenente') or {}
            financ = str(conced.get('nome') or 'Governo Federal')
            uf     = str(conv.get('uf') or '')
            dias   = _dias_restantes(dt_fim)
            items.append({
                'id':                f'tv-{numero}',
                'fonte':             'Portal da Transparencia',
                'titulo':            f'Transferencia Voluntaria {numero}',
                'descricao':         objeto,
                'financiador':       financ,
                'valor_max':         str(valor) if valor else '',
                'data_encerramento': dt_fim,
                'dias_restantes':    dias,
                'status':            _status(dias),
                'areas_tematicas':   'Transferencia Voluntaria|Governo Federal',
                'uf_elegivel':       uf or 'Nacional',
                'url_original':      f'https://portaldatransparencia.gov.br/transferencias/{numero}',
                'is_real':           True,
            })
        if items:
            print('    -> ' + str(len(items)) + ' transferencias coletadas')
        return items
    except Exception as e:
        print('[AVISO] transferencias-voluntarias indisponivel: ' + str(e))
    return []


# ── Fonte F: Prosas API ───────────────────────────────────────────────────────

def coletar_prosas_api() -> list:
    """Coleta editais com inscricoes abertas via API oficial da Prosas."""
    CLIENT_ID = 'lsf6jeu7-Wk04P2iSYMdcMhPZUNZqabK8CG6mAfRQ6M'
    TOKEN_URL = 'https://prosas.com.br/auth/oauth2/token'
    API_URL   = 'https://prosas.com.br/selecao/api/v2/third_party/oportunidades/inscricoes_abertas'

    print('[P] Coletando editais via API Prosas...')
    try:
        r = requests.post(TOKEN_URL, json={
            'grant_type': 'client_credentials',
            'client_id':  CLIENT_ID,
            'scope':      'public',
        }, timeout=15)
        r.raise_for_status()
        token = r.json().get('access_token', '')
        if not token:
            print('    [AVISO] Token nao obtido.')
            return []
    except Exception as e:
        print(f'    [AVISO] Falha autenticacao Prosas: {e}')
        return []

    headers = {'Authorization': f'Bearer {token}'}
    editais, page = [], 1
    while True:
        try:
            r = requests.get(API_URL, headers=headers, params={
                'include':    'area_interesses,incentivador',
                'page[page]': page,
                'page[size]': 100,
                'sort':       '',
            }, timeout=15)
            r.raise_for_status()
            items = r.json().get('data', [])
            if not items:
                break
            for item in items:
                a = item.get('attributes', {})
                encerramento = (a.get('encerramento_das_inscricoes') or '')[:10]
                dias = _dias_restantes(encerramento)
                editais.append({
                    'id':                f'prosas-{item["id"]}',
                    'fonte':             'Prosas',
                    'titulo':            (a.get('nome') or '')[:200],
                    'descricao':         (a.get('nome') or '')[:500],
                    'financiador':       a.get('nome_empresa') or 'Prosas',
                    'valor_max':         '',
                    'data_encerramento': encerramento,
                    'dias_restantes':    dias,
                    'status':            _status(dias),
                    'areas_tematicas':   'Terceiro Setor|Prosas',
                    'uf_elegivel':       'Nacional',
                    'url_original':      f'https://prosas.com.br/oportunidades/{item["id"]}',
                    'is_real':           True,
                })
            print(f'    -> Pagina {page}: {len(items)} editais')
            if len(items) < 100:
                break
            page += 1
            time.sleep(0.3)
        except Exception as e:
            print(f'    [AVISO] Erro pagina {page}: {e}')
            break

    print(f'    -> Total Prosas: {len(editais)} editais')
    return editais


# ── Main ──────────────────────────────────────────────────────────────────────

def coletar_todos() -> pd.DataFrame:
    agora = datetime.now()
    print('=========================================')
    print('  HUB DE CAPTACAO — Coleta de Oportunidades')
    print('  Data: ' + agora.strftime('%d/%m/%Y') + '  Hora: ' + agora.strftime('%H:%M'))
    print('=========================================')

    anthropic_key  = os.environ.get('ANTHROPIC_API_KEY', '')
    portal_key     = os.environ.get('PORTAL_TRANSPARENCIA_API_KEY', '')

    print('[CONFIG] ANTHROPIC_API_KEY: ' + ('configurada' if anthropic_key else 'nao configurada (extracao por regex)'))
    print('[CONFIG] PORTAL_TRANSPARENCIA_API_KEY: ' + ('configurada' if portal_key else 'nao configurada'))
    print('[CONFIG] PROSAS: sempre ativa (client_id hardcoded)')
    print()

    todos: list[dict] = []

    # ── ETAPA 1: Varredura RSS (sempre ativa) ────────────────────────────────
    print('=== ETAPA 1: Varredura de Portais de Noticias ===')
    noticias = coletar_noticias_portais()

    if noticias:
        if anthropic_key:
            # Modo IA: extracao estruturada com Claude Haiku
            print()
            print('[IA] Extraindo estrutura com Claude Haiku (' + str(len(noticias)) + ' noticias)...')
            extraidos_ia = 0
            extraidos_regex = 0
            for i, noticia in enumerate(noticias, 1):
                print('    [' + str(i) + '/' + str(len(noticias)) + '] ' + noticia['titulo'][:70] + '...')
                edital = extrair_edital_com_ia(noticia, anthropic_key)
                if edital:
                    todos.append(edital)
                    extraidos_ia += 1
                else:
                    # IA disse que nao e edital — nao incluir
                    pass
            print('[IA] ' + str(extraidos_ia) + ' oportunidades extraidas com IA')
            print('[IA] ' + str(len(noticias) - extraidos_ia) + ' noticias descartadas (nao eram editais)')
        else:
            # Modo regex: extracao heuristica sem API
            print()
            print('[RE] Modo regex — extraindo estrutura sem IA (' + str(len(noticias)) + ' noticias)...')
            for noticia in noticias:
                texto_check = unicodedata.normalize('NFKD', (noticia['titulo'] + ' ' + noticia['resumo']).lower())
                texto_check = ''.join(c for c in texto_check if not unicodedata.combining(c))
                if not any(p in texto_check for p in PALAVRAS_ALTA_CONFIANCA):
                    continue
                edital = extrair_edital_por_regex(noticia)
                todos.append(edital)
            print('[RE] ' + str(len(todos)) + ' oportunidades extraidas por regex')
    else:
        print('[AVISO] Nenhum portal RSS retornou noticias relevantes.')

    # ── ETAPA 2: Portal da Transparencia (opcional) ──────────────────────────
    print()
    print('=== ETAPA 2: Portal da Transparencia ===')
    items_pt = coletar_portal_transparencia()
    todos.extend(items_pt)

    items_mrosc = coletar_termos_fomento()
    todos.extend(items_mrosc)

    # ── ETAPA 3: Prosas API — Fonte F (opcional, requer PROSAS_CLIENT_SECRET) ─
    print()
    print('=== ETAPA 3: Prosas API (Fonte F) ===')
    items_prosas = coletar_prosas_api()
    todos.extend(items_prosas)

    # ── Resultado ────────────────────────────────────────────────────────────
    print()
    if not todos:
        print('[AVISO] Nenhuma oportunidade coletada. Verifique conexao com a internet.')
        return pd.DataFrame(columns=SCHEMA)

    df = pd.DataFrame(todos)

    for col in SCHEMA:
        if col not in df.columns:
            df[col] = ''

    df = df[SCHEMA]

    # Deduplicar por URL
    df = df.drop_duplicates(subset=['url_original']).reset_index(drop=True)

    # Deduplicar por titulo normalizado — prefere is_real=True
    df['_titulo_norm'] = df['titulo'].apply(_normalizar_titulo)
    df = df.sort_values('is_real', ascending=False)
    df = df.drop_duplicates(subset=['_titulo_norm']).reset_index(drop=True)
    df = df.drop(columns=['_titulo_norm'])

    df['_fp'] = df['titulo'].apply(_fingerprint)
    df = df.sort_values('is_real', ascending=False)
    df = df.drop_duplicates(subset=['_fp']).reset_index(drop=True)
    df = df.drop(columns=['_fp'])

    # Forcar tipos
    df['dias_restantes'] = pd.to_numeric(df['dias_restantes'], errors='coerce').fillna(-1).astype(int)

    # Remover encerrados ha mais de 30 dias
    df = df[(df['dias_restantes'] >= -1) | (df['dias_restantes'] == -1)].reset_index(drop=True)

    out = os.path.join(DATA_DIR, 'editais.csv')
    df.to_csv(out, index=False)

    total_reais = int(df['is_real'].astype(str).str.lower().eq('true').sum())
    print('[OK] ' + str(len(df)) + ' oportunidades salvas (' + str(total_reais) + ' de fontes reais)')
    print('     Arquivo: ' + out)
    return df


if __name__ == '__main__':
    coletar_todos()
