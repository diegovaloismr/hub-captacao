# -*- coding: utf-8 -*-
"""
Importa emendas parlamentares via API do Portal da Transparência (CGU).
Documentação: https://api.portaldatransparencia.gov.br/swagger-ui.html

Uso:
    python3 scripts/importar_emendas.py

Requer variável de ambiente:
    TRANSPARENCIA_API_KEY  — chave obtida em
    https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email

Se a chave não estiver configurada, gera um CSV vazio com as colunas corretas
para que o restante do pipeline não quebre.
"""
import os
import time
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = Path(os.environ.get('DATA_DIR', BASE_DIR / 'data'))
OUT_CSV  = DATA_DIR / 'emendas_parlamentares.csv'

API_BASE   = 'https://api.portaldatransparencia.gov.br/api-de-dados'
API_KEY    = os.environ.get('PORTAL_TRANSPARENCIA_API_KEY', '') or os.environ.get('TRANSPARENCIA_API_KEY', '')

# Colunas que o CSV final deve ter — mantidas mesmo quando API está indisponível
COLUNAS = [
    'codigo_emenda',
    'numero_emenda',
    'tipo_emenda',
    'autor',
    'partido',
    'uf_autor',
    'area_tematica',
    'funcao',
    'subfuncao',
    'valor_empenhado',
    'valor_liquidado',
    'valor_pago',
    'ano_exercicio',
    'nome_programa',
    'nome_acao',
    'nome_beneficiario',
    'cnpj_beneficiario',
    'municipio_beneficiario',
    'uf_beneficiario',
    'link_transparencia',
    'coletado_em',
]

ANOS_BUSCA    = [datetime.now().year, datetime.now().year - 1]
TIPOS_EMENDA  = ['Individual', 'Bancada', 'Comissao']  # conforme API
MAX_PAGINAS   = 200   # 100 registros/página → até 20 000 por combinação
SLEEP_ENTRE_REQ = 0.5  # segundos — respeita rate-limit da API


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _headers() -> dict:
    return {
        'chave-api-dados': API_KEY,
        'Accept': 'application/json',
    }


def _get(endpoint: str, params: dict) -> list:
    """Faz GET paginado e retorna lista de itens."""
    itens: list = []
    for pagina in range(1, MAX_PAGINAS + 1):
        params_req = {**params, 'pagina': pagina}
        try:
            r = requests.get(
                f'{API_BASE}/{endpoint}',
                headers=_headers(),
                params=params_req,
                timeout=30,
            )
            if r.status_code == 204:          # sem conteúdo nesta página
                break
            r.raise_for_status()
            dados = r.json()
            if not dados:
                break
            itens.extend(dados if isinstance(dados, list) else [dados])
            if len(dados) < 100:              # última página
                break
            time.sleep(SLEEP_ENTRE_REQ)
        except requests.exceptions.HTTPError as exc:
            print(f'  [ERRO HTTP] {exc} — parando paginação')
            break
        except Exception as exc:
            print(f'  [ERRO] {exc}')
            break
    return itens


# ---------------------------------------------------------------------------
# Extração
# ---------------------------------------------------------------------------

def extrair_emendas(ano: int) -> list[dict]:
    """Coleta emendas de um ano pelo endpoint /emendas."""
    print(f'  Coletando emendas {ano}...')
    raw = _get('emendas', {'ano': ano})
    registros = []
    agora = datetime.now().isoformat(timespec='seconds')

    for item in raw:
        # Identificação da emenda
        codigo   = str(item.get('codigoEmenda') or item.get('codigo') or '')
        numero   = str(item.get('numeroEmenda') or item.get('numero') or '')
        tipo     = str(item.get('tipoEmenda') or '')
        autor    = str(item.get('nomeAutor') or item.get('autor') or '')
        partido  = str(item.get('siglaPartidoAutor') or item.get('partido') or '')
        uf_autor = str(item.get('siglaUfAutor') or item.get('ufAutor') or '').upper()

        # Classificação orçamentária
        area      = str(item.get('areaTematica') or '')
        funcao    = str(item.get('nomeFuncao') or item.get('funcao') or '')
        subfuncao = str(item.get('nomeSubfuncao') or item.get('subfuncao') or '')
        programa  = str(item.get('nomePrograma') or '')
        acao      = str(item.get('nomeAcao') or '')

        # Valores (API retorna formato BR: '7,00' → substituir vírgula por ponto)
        def _to_float(v):
            if not v:
                return 0.0
            return float(str(v).replace('.', '').replace(',', '.'))

        val_emp = _to_float(item.get('valorEmpenhado'))
        val_liq = _to_float(item.get('valorLiquidado'))
        val_pag = _to_float(item.get('valorPago'))

        # Beneficiário
        nome_ben  = str(item.get('nomeFavorecido') or item.get('nomeBeneficiario') or '')
        cnpj_ben  = str(item.get('cnpjCpfFavorecido') or item.get('cnpjBeneficiario') or '')
        mun_ben   = str(item.get('municipioFavorecido') or item.get('municipioBeneficiario') or '')
        uf_ben    = str(item.get('siglaUfFavorecido') or item.get('ufBeneficiario') or '').upper()

        link = (
            f'https://portaldatransparencia.gov.br/emendas/{codigo}'
            if codigo else ''
        )

        registros.append({
            'codigo_emenda':         codigo,
            'numero_emenda':         numero,
            'tipo_emenda':           tipo,
            'autor':                 autor,
            'partido':               partido,
            'uf_autor':              uf_autor,
            'area_tematica':         area,
            'funcao':                funcao,
            'subfuncao':             subfuncao,
            'valor_empenhado':       val_emp,
            'valor_liquidado':       val_liq,
            'valor_pago':            val_pag,
            'ano_exercicio':         ano,
            'nome_programa':         programa,
            'nome_acao':             acao,
            'nome_beneficiario':     nome_ben,
            'cnpj_beneficiario':     cnpj_ben,
            'municipio_beneficiario': mun_ben,
            'uf_beneficiario':       uf_ben,
            'link_transparencia':    link,
            'coletado_em':           agora,
        })

    return registros


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not API_KEY:
        print('[AVISO] PORTAL_TRANSPARENCIA_API_KEY não configurada.')
        print('  Gerando CSV vazio com colunas corretas em:', OUT_CSV)
        pd.DataFrame(columns=COLUNAS).to_csv(OUT_CSV, index=False)
        print('  Configure a chave e rode novamente para importar dados reais.')
        print('  Obtenha sua chave em: https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email')
        return

    todos: list[dict] = []
    for ano in ANOS_BUSCA:
        registros = extrair_emendas(ano)
        todos.extend(registros)
        print(f'  [{ano}] {len(registros)} emendas coletadas')

    if not todos:
        print('[AVISO] Nenhuma emenda coletada. Gerando CSV vazio.')
        pd.DataFrame(columns=COLUNAS).to_csv(OUT_CSV, index=False)
        return

    df = pd.DataFrame(todos)[COLUNAS]

    # Remove duplicatas pela chave composta (codigo + ano)
    df = df.drop_duplicates(subset=['codigo_emenda', 'ano_exercicio'])

    # Ordena por valor empenhado desc
    df = df.sort_values('valor_empenhado', ascending=False).reset_index(drop=True)

    df.to_csv(OUT_CSV, index=False)
    print(f'\n[OK] {len(df)} emendas salvas em {OUT_CSV}')
    print(f'     Anos: {sorted(df["ano_exercicio"].unique().tolist())}')
    print(f'     Valor total empenhado: R$ {df["valor_empenhado"].sum():,.2f}')


if __name__ == '__main__':
    main()
