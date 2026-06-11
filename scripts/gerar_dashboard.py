# -*- coding: utf-8 -*-
"""
Gerador do Dashboard Hub de Captação.
Lê os CSVs em data/ e produz app/dashboard.html com todos os dados embutidos.
"""
import pandas as pd
import os
from datetime import date, datetime

# Carregar variáveis do arquivo .env se existir
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
APP_DIR  = os.path.join(os.path.dirname(__file__), '..', 'app')


def _load():
    proj_raw = pd.read_csv(os.path.join(DATA_DIR, 'projetos_reais_tratados.csv')).fillna('')
    # Manter apenas colunas usadas pela interface para reduzir tamanho do JSON
    _proj_cols = ['nome_projeto','proponente','modalidade_esportiva','uf','regiao',
                  'manifestacao','municipio','ano_aprovacao','valor_aprovado',
                  'valor_captado','saldo_disponivel','percentual_captado',
                  'data_fim_captacao','status','score_prioridade','is_real']
    proj = proj_raw[[c for c in _proj_cols if c in proj_raw.columns]]
    emp   = pd.read_csv(os.path.join(DATA_DIR, 'empresas_potenciais.csv')).fillna('')
    match_raw = pd.read_csv(os.path.join(DATA_DIR, 'match_inteligente.csv')).fillna('')
    # Top 10 empresas por projeto, score >= 0.50 — mantém JSON gerenciavel
    # Dropamos ranking_projeto e justificativa (pesado, reconstruido no JS se necessario)
    if not match_raw.empty and 'nome_projeto' in match_raw.columns:
        match_raw['score_match'] = pd.to_numeric(match_raw['score_match'], errors='coerce').fillna(0)
        match = (match_raw[match_raw['score_match'] >= 0.50]
                 .sort_values('score_match', ascending=False)
                 .groupby('nome_projeto', sort=False)
                 .head(10)
                 .reset_index(drop=True))
        _keep_match = [c for c in ['nome_projeto','nome_empresa','score_match',
                                    'score_geo','score_setor','score_financeiro']
                       if c in match.columns]
        match = match[_keep_match]
    else:
        match = match_raw

    edit_path  = os.path.join(DATA_DIR, 'editais.csv')
    medit_path = os.path.join(DATA_DIR, 'match_editais.csv')
    editais       = pd.read_csv(edit_path).fillna('')  if os.path.exists(edit_path)  else pd.DataFrame()

    # Limitar match_editais ao top 3 por projeto, apenas colunas necessarias
    match_editais = pd.DataFrame()
    if os.path.exists(medit_path):
        me_raw = pd.read_csv(medit_path).fillna('')
        if not me_raw.empty and 'nome_projeto' in me_raw.columns:
            me_raw['score_match'] = pd.to_numeric(me_raw['score_match'], errors='coerce').fillna(0)
            me_top = (
                me_raw.sort_values('score_match', ascending=False)
                      .groupby('nome_projeto', sort=False)
                      .head(10)
                      .reset_index(drop=True)
            )
            _keep_edit = [c for c in ['nome_projeto','id_edital','titulo_edital','financiador',
                                       'score_match','dias_restantes','status_edital','url_edital']
                          if c in me_top.columns]
            match_editais = me_top[_keep_edit]
        else:
            match_editais = me_raw

    return proj, emp, match, editais, match_editais


def gerar_dashboard():
    import json as _json
    proj, emp, match, editais, match_editais = _load()

    proj_json        = proj.to_json(orient='records', force_ascii=False)
    emp_json         = emp.to_json(orient='records', force_ascii=False)
    match_json       = match.to_json(orient='records', force_ascii=False)
    editais_json     = editais.to_json(orient='records', force_ascii=False)     if not editais.empty      else '[]'
    match_edit_json  = match_editais.to_json(orient='records', force_ascii=False) if not match_editais.empty else '[]'

    agora      = datetime.now()
    hoje       = date.today().strftime('%d/%m/%Y')
    agora_fmt  = agora.strftime('%d/%m/%Y %H:%M')
    n_proj     = len(proj)
    n_emp      = len(emp)
    n_editais  = len(editais)
    saldo_fmt  = f"R$ {proj['saldo_disponivel'].sum()/1_000_000:.1f}M"

    # Verificar se todos os editais são dados de demonstração (fallback)
    todos_demo = 'true'
    if not editais.empty and 'is_real' in editais.columns:
        if editais['is_real'].astype(str).str.lower().isin(['true', '1']).any():
            todos_demo = 'false'

    # ── META: Projetos ────────────────────────────────────────────────────────
    meta_projetos = {
        'ultima_importacao':  agora_fmt,
        'total_projetos':     n_proj,
        'planilha_base':      'projetos-ministerio-esporte.xlsx',
        'ano_min':            int(proj['ano_aprovacao'].min()) if n_proj and 'ano_aprovacao' in proj.columns else 0,
        'ano_max':            int(proj['ano_aprovacao'].max()) if n_proj and 'ano_aprovacao' in proj.columns else 0,
        'total_ufs':          int(proj['uf'].nunique())                   if n_proj and 'uf' in proj.columns else 0,
        'total_modalidades':  int(proj['modalidade_esportiva'].nunique()) if n_proj and 'modalidade_esportiva' in proj.columns else 0,
        'valor_total':        float(proj['valor_aprovado'].sum())         if n_proj and 'valor_aprovado' in proj.columns else 0.0,
    }

    # ── META: Editais ─────────────────────────────────────────────────────────
    n_edit_ativos    = int((editais['status'] == 'ativo').sum())    if not editais.empty and 'status' in editais.columns else 0
    n_edit_encerr    = int((editais['status'] != 'ativo').sum())    if not editais.empty and 'status' in editais.columns else 0
    tem_dados_reais  = bool(editais['is_real'].astype(str).str.lower().isin(['true','1']).any()) if not editais.empty and 'is_real' in editais.columns else False
    meta_editais = {
        'ultima_coleta':      agora_fmt,
        'total_ativos':       n_edit_ativos,
        'total_encerrados':   n_edit_encerr,
        'tem_dados_reais':    tem_dados_reais,
        'tem_portal_key':     bool(os.environ.get('PORTAL_TRANSPARENCIA_API_KEY')),
        'tem_anthropic_key':  bool(os.environ.get('ANTHROPIC_API_KEY')),
    }

    # ── META: Empresas ────────────────────────────────────────────────────────
    n_grandes  = int((emp['potencial_investimento'] >= 50_000_000).sum()) if n_emp and 'potencial_investimento' in emp.columns else 0
    n_medias   = int(((emp['potencial_investimento'] >= 5_000_000) & (emp['potencial_investimento'] < 50_000_000)).sum()) if n_emp and 'potencial_investimento' in emp.columns else 0
    n_pequenas = int(((emp['potencial_investimento'] >= 500_000) & (emp['potencial_investimento'] < 5_000_000)).sum()) if n_emp and 'potencial_investimento' in emp.columns else 0
    n_setores  = int(emp['setor'].nunique()) if n_emp and 'setor' in emp.columns else 0
    pot_total  = float(emp['potencial_investimento'].sum()) if n_emp and 'potencial_investimento' in emp.columns else 0.0
    meta_empresas = {
        'ultima_importacao': agora_fmt,
        'total_empresas':    n_emp,
        'fonte':             'LIE + Rouanet (Prosas, 2022-2025)',
        'filtro':            'total_incentivos >= R$ 100.000',
        'n_grandes':         n_grandes,
        'n_medias':          n_medias,
        'n_pequenas':        n_pequenas,
        'n_setores':         n_setores,
        'potencial_total':   pot_total,
    }

    # ── META: Sistema ─────────────────────────────────────────────────────────
    meta_sistema = {
        'dashboard_gerado':   agora_fmt,
        'versao':             'v8',
        'n_projetos':         n_proj,
        'n_empresas':         n_emp,
        'n_match_proj_emp':   len(match),
        'n_editais':          n_editais,
        'n_match_editais':    len(match_editais),
    }

    html = _HTML_TEMPLATE
    html = html.replace('__PROJ_JSON__',          proj_json)
    html = html.replace('__EMP_JSON__',           emp_json)
    html = html.replace('__MATCH_JSON__',         match_json)
    html = html.replace('__EDITAIS_JSON__',       editais_json)
    html = html.replace('__MATCH_EDITAIS_JSON__', match_edit_json)
    html = html.replace('__TODOS_DEMO__',         todos_demo)
    html = html.replace('__HOJE__',               hoje)
    html = html.replace('__N_PROJ__',             str(n_proj))
    html = html.replace('__N_EMP__',              str(n_emp))
    html = html.replace('__N_EDITAIS__',          str(n_editais))
    html = html.replace('__SALDO_FMT__',          saldo_fmt)
    html = html.replace('__META_PROJETOS_JSON__', _json.dumps(meta_projetos, ensure_ascii=False))
    html = html.replace('__META_EDITAIS_JSON__',  _json.dumps(meta_editais,  ensure_ascii=False))
    html = html.replace('__META_EMPRESAS_JSON__', _json.dumps(meta_empresas, ensure_ascii=False))
    html = html.replace('__META_SISTEMA_JSON__',  _json.dumps(meta_sistema,  ensure_ascii=False))

    os.makedirs(APP_DIR, exist_ok=True)
    out = os.path.join(APP_DIR, 'dashboard.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[OK] Dashboard gerado em {out}  ({n_proj} projetos | {n_emp} empresas | {n_editais} editais)")


# ─────────────────────────────────────────────────────────────────────────────
# HTML TEMPLATE  (use __PLACEHOLDER__ for Python injections, ${...} for JS)
# ─────────────────────────────────────────────────────────────────────────────
_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HUB DE CAPTAÇÃO | Terminal de Inteligência</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --green:      #00FF41;
  --green2:     #00CC33;
  --green3:     #009922;
  --green-dim:  #006614;
  --green-dark: #001a00;
  --amber:      #FFB300;
  --red:        #FF4444;
  --bg:         #000000;
  --bg2:        #050f05;
  --bg3:        #0a1a0a;
  --border:     #003300;
  --font:       'Menlo','Monaco','Consolas','Courier New',monospace;
}
html, body { height: 100%; background: var(--bg); color: var(--green); font-family: var(--font); font-size: 13px; overflow: hidden; }
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--green-dim); border-radius: 3px; }

/* layout */
#root { display: flex; flex-direction: column; height: 100vh; }
#header { flex-shrink: 0; border-bottom: 1px solid var(--border); padding: 6px 12px; background: var(--bg2); }
#ticker { flex-shrink: 0; border-bottom: 1px solid var(--border); height: 26px; overflow: hidden; background: var(--green-dark); }
#main { flex: 1; display: flex; min-height: 0; }
#sidebar { flex-shrink: 0; width: 160px; border-right: 1px solid var(--border); background: var(--bg2); padding: 8px 0; overflow-y: auto; }
#content { flex: 1; display: flex; flex-direction: column; min-width: 0; }
#statusbar { flex-shrink: 0; border-top: 1px solid var(--border); padding: 3px 12px; background: var(--bg2); font-size: 11px; color: var(--green3); }

/* header */
.hdr-top { display: flex; justify-content: space-between; align-items: center; }
.hdr-title { font-size: 15px; font-weight: bold; letter-spacing: 2px; color: var(--green); text-shadow: 0 0 8px var(--green); }
.hdr-stats { display: flex; gap: 18px; font-size: 11px; color: var(--green3); }
.hdr-stat span { color: var(--green); font-weight: bold; }

/* ticker */
#ticker-inner { display: inline-block; white-space: nowrap; animation: scroll-left 80s linear infinite; padding: 4px 0; font-size: 11px; color: var(--green3); }
@keyframes scroll-left { from { transform: translateX(100vw); } to { transform: translateX(-100%); } }
.tick-item { display: inline-block; margin-right: 40px; }
.tick-item .tick-name { color: var(--green); }
.tick-item .tick-val  { color: var(--amber); }

/* sidebar */
.nav-section { padding: 6px 12px 2px; font-size: 10px; color: var(--green-dim); letter-spacing: 1px; }
.nav-item { display: block; width: 100%; text-align: left; background: none; border: none; color: var(--green3); font-family: var(--font); font-size: 12px; padding: 6px 16px; cursor: pointer; transition: all .15s; }
.nav-item:hover, .nav-item.active { background: var(--bg3); color: var(--green); border-left: 2px solid var(--green); padding-left: 14px; }
.nav-divider { border: none; border-top: 1px solid var(--border); margin: 6px 12px; }

/* panel */
.panel-header { flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; padding: 4px 12px; background: var(--bg3); border-bottom: 1px solid var(--border); font-size: 11px; color: var(--green3); }
.panel-title { font-weight: bold; color: var(--green); letter-spacing: 1px; font-size: 12px; }

/* filters */
.filters { flex-shrink: 0; display: flex; gap: 8px; flex-wrap: wrap; padding: 6px 12px; background: var(--bg2); border-bottom: 1px solid var(--border); }
.filter-label { font-size: 10px; color: var(--green-dim); white-space: nowrap; }
.filter-group { display: flex; align-items: center; gap: 4px; }
select, input[type=text], input[type=number] {
  background: var(--bg3); border: 1px solid var(--green-dim); color: var(--green);
  font-family: var(--font); font-size: 11px; padding: 2px 6px; border-radius: 2px; outline: none;
}
select:focus, input:focus { border-color: var(--green); }
.btn { background: var(--green-dark); border: 1px solid var(--green-dim); color: var(--green3); font-family: var(--font); font-size: 11px; padding: 2px 10px; cursor: pointer; border-radius: 2px; }
.btn:hover { background: var(--bg3); color: var(--green); border-color: var(--green); }

/* tables */
.table-wrap { flex: 1; overflow: auto; min-height: 0; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { position: sticky; top: 0; background: var(--bg3); color: var(--green3); padding: 5px 10px; text-align: left; font-weight: normal; border-bottom: 1px solid var(--green-dim); cursor: pointer; white-space: nowrap; user-select: none; font-size: 11px; letter-spacing: .5px; z-index: 1; }
th:hover { color: var(--green); }
th .si { font-size: 9px; margin-left: 4px; opacity: .5; }
th.sorted .si { opacity: 1; color: var(--amber); }
td { padding: 4px 10px; border-bottom: 1px solid #001100; white-space: nowrap; }
tr:hover td { background: var(--green-dark); cursor: pointer; }
tr.selected td { background: #001f00; border-left: 2px solid var(--green); }
.score-high { color: var(--green);  font-weight: bold; }
.score-mid  { color: var(--amber); }
.score-low  { color: var(--red); }
.badge { display: inline-block; padding: 1px 6px; border-radius: 2px; font-size: 10px; border: 1px solid var(--green-dim); color: var(--green); }

/* radar */
#radar-grid { display: grid; grid-template-columns: 1fr 1fr; height: 100%; overflow: hidden; }
.radar-card { border-right: 1px solid var(--border); overflow-y: auto; display: flex; flex-direction: column; }
.radar-card:nth-child(2n) { border-right: none; }
.radar-card-header { padding: 5px 10px; background: var(--bg3); border-bottom: 1px solid var(--border); font-size: 11px; color: var(--green3); font-weight: bold; flex-shrink: 0; }
.radar-card-header em { color: var(--amber); font-style: normal; }
.radar-row { display: flex; justify-content: space-between; padding: 3px 10px; border-bottom: 1px solid #001100; font-size: 11px; }
.radar-row:hover { background: var(--green-dark); }
.radar-name { color: var(--green3); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.radar-val  { color: var(--amber); flex-shrink: 0; margin-left: 8px; }
.radar-uf   { color: var(--green-dim); width: 28px; flex-shrink: 0; text-align: right; margin-right: 8px; }

/* views */
.view { display: none; flex-direction: column; flex: 1; min-height: 0; }
.view.active { display: flex; }

/* ─── PROJETOS SPLIT ─────────────────────────────────────────────────── */
#proj-split { flex: 1; display: flex; flex-direction: column; min-height: 0; }
#proj-top   { flex: 1 1 55%; display: flex; flex-direction: column; min-height: 0; border-bottom: 2px solid var(--green-dim); }
#proj-bot   { flex: 0 0 45%; display: flex; flex-direction: column; min-height: 0; }

/* tabs inside proj-bot */
.tab-bar { flex-shrink: 0; display: flex; background: var(--bg2); border-bottom: 1px solid var(--border); }
.tab-btn { background: none; border: none; border-right: 1px solid var(--border); color: var(--green3); font-family: var(--font); font-size: 11px; padding: 5px 14px; cursor: pointer; transition: all .15s; }
.tab-btn:hover { color: var(--green); background: var(--bg3); }
.tab-btn.active { color: var(--green); background: var(--bg3); border-bottom: 2px solid var(--green); font-weight: bold; }
.tab-proj-info { flex-shrink: 0; padding: 4px 12px; background: var(--bg2); border-bottom: 1px solid var(--border); font-size: 11px; }
.tab-pane { display: none; flex: 1; flex-direction: column; min-height: 0; }
.tab-pane.active { display: flex; }

/* ─── MATCHING SPLIT ─────────────────────────────────────────────────── */
#match-split { flex: 1; display: flex; min-height: 0; }
#match-left  { flex: 0 0 320px; display: flex; flex-direction: column; border-right: 2px solid var(--green-dim); }
#match-right { flex: 1; display: flex; flex-direction: column; min-height: 0; }
/* sub-tabs in match-right */
#match-detail-tabs { flex: 1; display: flex; flex-direction: column; min-height: 0; }

/* ─── EDITAIS VIEW ───────────────────────────────────────────────────── */
.editais-stats { flex-shrink: 0; display: flex; border-bottom: 1px solid var(--border); background: var(--bg2); }
.editais-stat  { flex: 1; padding: 6px 12px; border-right: 1px solid var(--border); font-size: 11px; color: var(--green3); }
.editais-stat:last-child { border-right: none; }
.editais-stat .es-val { font-size: 18px; font-weight: bold; color: var(--green); display: block; line-height: 1.2; }
.editais-stat .es-lbl { font-size: 10px; color: var(--green-dim); }

/* prazo colors */
.prazo-ok     { color: var(--green); }
.prazo-warn   { color: var(--amber); }
.prazo-urgent { color: var(--red); animation: pulse 1.2s ease-in-out infinite; }
.prazo-none   { color: var(--green-dim); }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

/* status badge */
.st-ativo     { color: var(--green);  border-color: var(--green-dim); }
.st-encerrado { color: var(--red);    border-color: #440000; }

/* empty state */
.empty-state { flex: 1; display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 10px; color: var(--green-dim); font-size: 12px; }
.empty-state code { color: var(--green); background: var(--bg3); padding: 6px 14px; border: 1px solid var(--border); font-family: var(--font); font-size: 11px; }

/* sem dados banner */
#demo-banner { display:none; flex-shrink:0; padding:6px 16px; background:var(--bg3); border-bottom:1px solid var(--border); color:var(--green3); font-size:11px; font-family:var(--font); letter-spacing:.3px; }

/* ── ATUALIZAR VIEW ────────────────────────────────────────────────── */
.update-panel { border:1px solid var(--border); padding:16px; margin-bottom:20px; background:var(--bg2); }
.update-panel h3 { color:var(--green); font-size:11px; letter-spacing:2px; margin:0 0 12px 0; border-bottom:1px solid var(--border); padding-bottom:8px; }
.status-box { background:var(--bg3); border:1px solid var(--border); padding:10px 14px; margin-bottom:14px; font-size:12px; line-height:1.8; }
.status-row { display:flex; justify-content:space-between; margin-bottom:2px; }
.status-label { color:var(--green3); }
.status-value { color:var(--green); font-weight:bold; }
.btn-copy { background:transparent; border:1px solid var(--green3); color:var(--green3); font-family:var(--font); font-size:11px; padding:4px 10px; cursor:pointer; transition:all .15s; margin-right:8px; margin-bottom:6px; }
.btn-copy:hover { border-color:var(--green); color:var(--green); }
.btn-copy.copied { border-color:var(--amber); color:var(--amber); }
.btn-external { background:transparent; border:1px solid var(--green); color:var(--green); font-family:var(--font); font-size:11px; padding:5px 12px; cursor:pointer; transition:all .15s; text-decoration:none; display:inline-block; margin-bottom:10px; }
.btn-external:hover { background:var(--green); color:var(--bg); }
.fonte-row { display:flex; align-items:center; gap:10px; font-size:11px; margin-bottom:3px; color:var(--green3); }
.filter-area-btn { background:transparent; border:1px solid var(--border); color:var(--green3); font-family:var(--font); font-size:11px; padding:4px 12px; cursor:pointer; transition:all .15s; }
.filter-area-btn:hover, .filter-area-btn.active { border-color:var(--green); color:var(--green); background:var(--bg3); }
.area-badge { display:inline-block; font-size:9px; padding:1px 5px; border-radius:2px; font-weight:bold; letter-spacing:.5px; }
.fonte-status-ok  { color:var(--green); }
.fonte-status-off { color:var(--amber); }
.demo-badge { color:var(--amber); animation:pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

/* modal overlay */
#modal-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,.75); z-index:9999; align-items:center; justify-content:center; }
#modal-overlay.open { display:flex; }
#modal-box { background:var(--bg2); border:1px solid var(--green); width:540px; max-width:95vw; font-family:var(--font); font-size:12px; }
#modal-box .modal-title { padding:10px 16px; background:var(--bg3); border-bottom:1px solid var(--border); color:var(--green); font-weight:bold; font-size:13px; letter-spacing:1px; display:flex; justify-content:space-between; align-items:center; }
#modal-box .modal-body  { padding:16px; color:var(--green3); line-height:1.7; }
#modal-box .modal-cmd   { background:var(--bg3); border:1px solid var(--border); padding:10px 14px; margin:10px 0; color:var(--green); font-size:11px; }
#modal-box .modal-cmd div { color:var(--green3); }
#modal-box .modal-cmd code { color:var(--green); }
#modal-box .modal-footer { padding:10px 16px; border-top:1px solid var(--border); display:flex; justify-content:flex-end; gap:8px; }
</style>
</head>
<body>
<div id="root">

  <!-- HEADER -->
  <div id="header">
    <div class="hdr-top">
      <div class="hdr-title">▶ HUB DE CAPTAÇÃO &nbsp;|&nbsp; TERMINAL DE INTELIGÊNCIA v2.0</div>
      <div class="hdr-stats">
        <div class="hdr-stat">PROJETOS <span>__N_PROJ__</span></div>
        <div class="hdr-stat">SALDO <span>__SALDO_FMT__</span></div>
        <div class="hdr-stat">EMPRESAS <span>__N_EMP__</span></div>
        <div class="hdr-stat">OPORTUNIDADES <span>__N_EDITAIS__</span></div>
        <div class="hdr-stat">DATA <span>__HOJE__</span></div>
      </div>
    </div>
  </div>

  <!-- TICKER -->
  <div id="ticker"><div id="ticker-inner"></div></div>

  <!-- MAIN -->
  <div id="main">

    <!-- SIDEBAR -->
    <div id="sidebar">
      <div class="nav-section">NAVEGAÇÃO</div>
      <button class="nav-item active" id="nav-projetos" onclick="showView('projetos')">◈ PROJETOS</button>
      <button class="nav-item"        id="nav-empresas" onclick="showView('empresas')">◈ EMPRESAS</button>
      <button class="nav-item"        id="nav-radar"    onclick="showView('radar')">◈ RADAR</button>
      <button class="nav-item"        id="nav-matching" onclick="showView('matching')">◈ MATCHING</button>
      <button class="nav-item"        id="nav-editais"  onclick="showView('editais')">◈ OPORTUNIDADES</button>
      <hr class="nav-divider">
      <div style="padding:4px 8px 2px;">
        <input type="text" id="sidebar-search" placeholder="🔍 busca por tema..." style="width:100%;font-size:11px;padding:4px 6px;" oninput="buscaUniversal(this.value)" onkeydown="if(event.key==='Enter')buscaUniversal(this.value)">
      </div>
      <button class="nav-item"        id="nav-busca"    onclick="showView('busca')" style="display:none;">◈ BUSCA</button>
      <button class="nav-item"        id="nav-atualizar" onclick="showView('atualizar')">&#x27F3; ATUALIZAR</button>
      <hr class="nav-divider">
      <button class="nav-item"        id="nav-config"   onclick="showView('config');initConfigView();">⚙ CONFIG</button>
      <hr class="nav-divider">
      <div class="nav-section">REGIÕES</div>
      <button class="nav-item" onclick="qfRegiao('Sudeste')">  Sudeste</button>
      <button class="nav-item" onclick="qfRegiao('Nordeste')">  Nordeste</button>
      <button class="nav-item" onclick="qfRegiao('Sul')">  Sul</button>
      <button class="nav-item" onclick="qfRegiao('Norte')">  Norte</button>
      <button class="nav-item" onclick="qfRegiao('Centro-Oeste')">  C-Oeste</button>
      <button class="nav-item" onclick="qfRegiao('Internacional')">  Internac.</button>
      <hr class="nav-divider">
      <button class="nav-item" onclick="clearFilters()">✕ LIMPAR FILTROS</button>
    </div>

    <!-- CONTENT -->
    <div id="content">

      <!-- ══════════════════════════ VIEW: PROJETOS ══════════════════════════ -->
      <div id="view-projetos" class="view active">
        <div id="proj-split">

          <!-- TOP: tabela de projetos -->
          <div id="proj-top">
            <div class="panel-header">
              <span class="panel-title">◈ PROJETOS — LEI DE INCENTIVO AO ESPORTE</span>
              <span id="proj-count" style="color:var(--green-dim);font-size:11px"></span>
            </div>
            <div class="filters">
              <div class="filter-group"><span class="filter-label">BUSCA:</span>
                <input type="text" id="f-busca" placeholder="nome / proponente..." style="width:160px" oninput="applyFilters()">
              </div>
              <div class="filter-group"><span class="filter-label">UF:</span>
                <select id="f-uf" onchange="applyFilters()"><option value="">TODAS</option></select>
              </div>
              <div class="filter-group"><span class="filter-label">REGIÃO:</span>
                <select id="f-regiao" onchange="applyFilters()"><option value="">TODAS</option></select>
              </div>
              <div class="filter-group"><span class="filter-label">MODALIDADE:</span>
                <select id="f-modalidade" onchange="applyFilters()"><option value="">TODAS</option></select>
              </div>
              <div class="filter-group"><span class="filter-label">ANO:</span>
                <select id="f-ano" onchange="applyFilters()"><option value="">TODOS</option></select>
              </div>
              <div class="filter-group"><span class="filter-label">SCORE≥:</span>
                <input type="number" id="f-score" min="0" max="1" step="0.05" placeholder="0.0" style="width:50px" oninput="applyFilters()">
              </div>
              <div class="filter-group"><span class="filter-label">SALDO MIN:</span>
                <input type="number" id="f-saldo" min="0" step="50000" placeholder="0" style="width:80px" oninput="applyFilters()">
              </div>
              <button class="btn" onclick="clearFilters()">LIMPAR</button>
            </div>
            <div class="table-wrap">
              <table id="proj-table">
                <thead><tr>
                  <th onclick="sortT('proj','nome_projeto')">PROJETO <span class="si">⇅</span></th>
                  <th onclick="sortT('proj','proponente')">PROPONENTE <span class="si">⇅</span></th>
                  <th onclick="sortT('proj','uf')">UF <span class="si">⇅</span></th>
                  <th onclick="sortT('proj','modalidade_esportiva')">MODALIDADE <span class="si">⇅</span></th>
                  <th onclick="sortT('proj','ano_aprovacao')">ANO <span class="si">⇅</span></th>
                  <th onclick="sortT('proj','valor_aprovado')">VL. APROVADO <span class="si">⇅</span></th>
                  <th onclick="sortT('proj','valor_captado')">CAPTADO <span class="si">⇅</span></th>
                  <th onclick="sortT('proj','saldo_disponivel')">SALDO DISP. <span class="si">⇅</span></th>
                  <th onclick="sortT('proj','score_prioridade')">SCORE <span class="si">⇅</span></th>
                </tr></thead>
                <tbody id="proj-body"></tbody>
              </table>
            </div>
            <div id="proj-pag-ctrl" style="display:flex;align-items:center;gap:8px;padding:6px 12px;border-top:1px solid var(--border);background:var(--bg2);flex-shrink:0;"></div>
          </div><!-- /proj-top -->

          <!-- BOTTOM: painel com abas Empresas / Editais -->
          <div id="proj-bot">
            <div class="tab-bar">
              <button class="tab-btn active" id="tb-emp"   onclick="switchTab('emp')">◈ EMPRESAS COMPATÍVEIS <span id="tc-emp"  style="color:var(--green-dim)"></span></button>
              <button class="tab-btn"        id="tb-edit"  onclick="switchTab('edit')">◈ OPORTUNIDADES COMPATÍVEIS <span id="tc-edit" style="color:var(--green-dim)"></span></button>
            </div>
            <div class="tab-proj-info">
              <span id="match-proj-name" style="color:var(--green)">Clique em um projeto acima para ver empresas e editais compatíveis</span>
            </div>

            <!-- Aba: Empresas -->
            <div class="tab-pane active" id="pane-emp">
              <div class="table-wrap">
                <table>
                  <thead><tr>
                    <th>#</th><th>EMPRESA</th><th>SETOR</th><th>UF</th>
                    <th>POTENCIAL</th><th>GEO</th><th>SET.</th><th>FIN.</th>
                    <th>MATCH</th><th>JUSTIFICATIVA</th>
                  </tr></thead>
                  <tbody id="match-body"></tbody>
                </table>
              </div>
            </div>

            <!-- Aba: Editais -->
            <div class="tab-pane" id="pane-edit">
              <div class="table-wrap">
                <table>
                  <thead><tr>
                    <th>SCORE</th><th>EDITAL</th><th>FINANCIADOR</th>
                    <th>PRAZO</th><th>ÁREA</th><th>GEO</th><th>TEMA</th><th>LINK</th>
                  </tr></thead>
                  <tbody id="match-edit-body">
                    <tr><td colspan="8" style="color:var(--green-dim);text-align:center;padding:10px;">Selecione um projeto acima</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div><!-- /proj-bot -->

        </div><!-- /proj-split -->
      </div><!-- /view-projetos -->

      <!-- ══════════════════════════ VIEW: EMPRESAS ══════════════════════════ -->
      <div id="view-empresas" class="view">
        <div class="panel-header">
          <span class="panel-title">◈ RANKING DE EMPRESAS — POTENCIAL DE INVESTIMENTO</span>
          <span id="emp-count" style="color:var(--green-dim);font-size:11px"></span>
        </div>
        <div class="filters">
          <div class="filter-group"><span class="filter-label">BUSCA:</span>
            <input type="text" id="f-emp-busca" placeholder="empresa / setor..." style="width:170px" oninput="renderEmpresas()">
          </div>
          <div class="filter-group"><span class="filter-label">SETOR:</span>
            <select id="f-emp-setor" onchange="renderEmpresas()"><option value="">TODOS</option></select>
          </div>
          <div class="filter-group"><span class="filter-label">REGIÃO:</span>
            <select id="f-emp-regiao" onchange="renderEmpresas()"><option value="">TODAS</option></select>
          </div>
          <button class="btn" onclick="clearEmpFilters()">LIMPAR</button>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr>
              <th onclick="sortT('emp','score_empresa')">SCORE <span class="si">⇅</span></th>
              <th onclick="sortT('emp','nome_empresa')">EMPRESA <span class="si">⇅</span></th>
              <th onclick="sortT('emp','setor')">SETOR <span class="si">⇅</span></th>
              <th onclick="sortT('emp','uf_sede')">UF <span class="si">⇅</span></th>
              <th onclick="sortT('emp','regiao_sede')">REGIÃO <span class="si">⇅</span></th>
              <th onclick="sortT('emp','faturamento_anual')">FATURAMENTO <span class="si">⇅</span></th>
              <th onclick="sortT('emp','potencial_investimento')">POTENCIAL INV. <span class="si">⇅</span></th>
              <th>SITE</th>
            </tr></thead>
            <tbody id="emp-body"></tbody>
          </table>
        </div>
      </div><!-- /view-empresas -->

      <!-- ══════════════════════════ VIEW: RADAR ══════════════════════════ -->
      <div id="view-radar" class="view">
        <div class="panel-header">
          <span class="panel-title">◈ RADAR DE OPORTUNIDADES — PROSPECÇÃO IMEDIATA</span>
        </div>
        <div id="radar-grid" style="flex:1;overflow:hidden;">
          <div class="radar-card">
            <div class="radar-card-header">💰 MAIORES SALDOS DISPONÍVEIS <em id="r1-c"></em></div>
            <div id="r-saldos"></div>
          </div>
          <div class="radar-card">
            <div class="radar-card-header">⏳ ENCERRANDO EM BREVE <em id="r2-c"></em></div>
            <div id="r-encerrando"></div>
          </div>
          <div class="radar-card" style="border-top:1px solid var(--border)">
            <div class="radar-card-header">⭐ ALTA PRIORIDADE (SCORE ≥ 0.70) <em id="r3-c"></em></div>
            <div id="r-prioridade"></div>
          </div>
          <div class="radar-card" style="border-top:1px solid var(--border)">
            <div class="radar-card-header">📈 MOMENTUM POSITIVO <em id="r4-c"></em></div>
            <div id="r-momentum"></div>
          </div>
        </div>
      </div><!-- /view-radar -->

      <!-- ══════════════════════════ VIEW: MATCHING ══════════════════════════ -->
      <div id="view-matching" class="view">
        <div class="panel-header" style="flex-shrink:0;">
          <span class="panel-title">◈ MATCHING INTELIGENTE — PROJETO × EMPRESA × EDITAL</span>
          <span id="matching-proj-count" style="color:var(--green-dim);font-size:11px"></span>
        </div>
        <div id="match-split">

          <!-- LEFT: lista de projetos -->
          <div id="match-left">
            <div style="flex-shrink:0;padding:4px 8px;background:var(--bg3);border-bottom:1px solid var(--border);font-size:10px;color:var(--green-dim);letter-spacing:.5px;">
              PROJETOS — clique para ver matching
            </div>
            <div style="flex-shrink:0;padding:4px 8px;background:var(--bg2);border-bottom:1px solid var(--border);">
              <input type="text" id="f-match-busca" placeholder="buscar projeto..." style="width:100%;font-size:11px;" oninput="renderMatchLeft()">
            </div>
            <div class="table-wrap">
              <table id="match-left-table" style="font-size:11px;">
                <thead><tr>
                  <th style="font-size:10px;">PROJETO</th>
                  <th style="font-size:10px;">UF</th>
                  <th style="font-size:10px;">SALDO</th>
                </tr></thead>
                <tbody id="match-left-body"></tbody>
              </table>
            </div>
          </div><!-- /match-left -->

          <!-- RIGHT: detalhe do projeto selecionado -->
          <div id="match-right">
            <div id="match-right-empty" class="empty-state">
              <div style="color:var(--green3);font-size:13px;">◈ Selecione um projeto à esquerda</div>
              <div>para ver empresas e editais compatíveis</div>
            </div>
            <div id="match-right-detail" style="display:none;flex:1;flex-direction:column;min-height:0;">
              <div style="flex-shrink:0;padding:5px 12px;background:var(--bg3);border-bottom:1px solid var(--border);">
                <span id="mr-proj-name" style="color:var(--green);font-weight:bold;font-size:12px;"></span>
                <span id="mr-proj-meta" style="color:var(--green3);font-size:11px;margin-left:12px;"></span>
              </div>
              <!-- matching sub-tabs -->
              <div class="tab-bar" style="flex-shrink:0;">
                <button class="tab-btn active" id="mrt-emp"  onclick="switchMatchTab('emp')">◈ EMPRESAS <span id="mrc-emp" style="color:var(--green-dim)"></span></button>
                <button class="tab-btn"        id="mrt-edit" onclick="switchMatchTab('edit')">◈ OPORTUNIDADES <span id="mrc-edit" style="color:var(--green-dim)"></span></button>
              </div>
              <!-- emp pane -->
              <div class="tab-pane active" id="mrp-emp" style="flex:1;min-height:0;">
                <div class="table-wrap">
                  <table>
                    <thead><tr>
                      <th>#</th><th>EMPRESA</th><th>SETOR</th><th>PAÍS/UF</th>
                      <th>POTENCIAL</th><th>GEO</th><th>SET.</th><th>FIN.</th>
                      <th>MATCH</th><th>JUSTIFICATIVA</th>
                    </tr></thead>
                    <tbody id="mr-emp-body"></tbody>
                  </table>
                </div>
              </div>
              <!-- edit pane -->
              <div class="tab-pane" id="mrp-edit" style="flex:1;min-height:0;">
                <div class="table-wrap">
                  <table>
                    <thead><tr>
                      <th>SCORE</th><th>EDITAL</th><th>FINANCIADOR</th>
                      <th>PRAZO</th><th>ÁREA</th><th>GEO</th><th>TEMA</th><th>LINK</th>
                    </tr></thead>
                    <tbody id="mr-edit-body"></tbody>
                  </table>
                </div>
              </div>
            </div>
          </div><!-- /match-right -->

        </div><!-- /match-split -->
      </div><!-- /view-matching -->

      <!-- ══════════════════════════ VIEW: EDITAIS ══════════════════════════ -->
      <div id="view-editais" class="view">
        <div class="panel-header">
          <span class="panel-title">◈ OPORTUNIDADES — NOTICIAS E FONTES DE FINANCIAMENTO</span>
          <span id="editais-count" style="color:var(--green-dim);font-size:11px"></span>
        </div>

        <!-- banner: sem dados ainda -->
        <div id="demo-banner">
          ○ &nbsp;Nenhuma oportunidade carregada ainda. Execute <code style="background:rgba(0,0,0,.2);padding:1px 6px;">python scripts/coletar_editais.py</code> para varrer os portais de noticias.
          &nbsp;&nbsp;<button onclick="openModal()" style="background:rgba(0,0,0,.25);border:1px solid #000;padding:2px 10px;font-family:var(--font);font-size:10px;cursor:pointer;font-weight:bold;">↺ COMO ATUALIZAR</button>
        </div>

        <!-- stats bar -->
        <div class="editais-stats">
          <div class="editais-stat">
            <span class="es-val" id="es-ativos">—</span>
            <span class="es-lbl">OPORTUNIDADES ATIVAS</span>
          </div>
          <div class="editais-stat">
            <span class="es-val" id="es-30d" style="color:var(--amber)">—</span>
            <span class="es-lbl">ENCERRAM EM 30 DIAS</span>
          </div>
          <div class="editais-stat">
            <span class="es-val" id="es-7d" style="color:var(--red)">—</span>
            <span class="es-lbl">ENCERRAM EM 7 DIAS</span>
          </div>
          <div class="editais-stat" style="flex:0 0 auto;padding:6px 12px;display:flex;align-items:center;">
            <button onclick="openModal()" id="btn-atualizar"
              style="background:transparent;border:1px solid var(--green);color:var(--green);font-family:var(--font);font-size:11px;padding:4px 12px;cursor:pointer;letter-spacing:.5px;transition:all .15s;"
              onmouseover="this.style.background='var(--green-dark)'"
              onmouseout="this.style.background='transparent'">
              ↺ ATUALIZAR OPORTUNIDADES
            </button>
          </div>
          <div class="editais-stat">
            <span class="es-val" id="es-updated" style="font-size:13px">—</span>
            <span class="es-lbl">ATUALIZADO</span>
          </div>
        </div>

        <!-- filtros rapidos de area -->
        <div style="display:flex;gap:8px;margin:8px 12px 4px;flex-wrap:wrap;">
          <button class="filter-area-btn active" onclick="filtrarAreaEditais('todos')" id="fab-todos">&#x25C8; TODOS</button>
          <button class="filter-area-btn" onclick="filtrarAreaEditais('esporte')" id="fab-esporte">&#x1F3C5; ESPORTE</button>
          <button class="filter-area-btn" onclick="filtrarAreaEditais('cultura')" id="fab-cultura">&#x1F3AD; CULTURA</button>
          <button class="filter-area-btn" onclick="filtrarAreaEditais('educacao')" id="fab-educacao">&#x1F4DA; EDUCA&#xC7;&#xC3;O</button>
          <button class="filter-area-btn" onclick="filtrarAreaEditais('social')" id="fab-social">&#x1F91D; SOCIAL</button>
          <button class="filter-area-btn" onclick="filtrarAreaEditais('outros')" id="fab-outros">+ OUTROS</button>
        </div>

        <!-- filters -->
        <div class="filters">
          <div class="filter-group"><span class="filter-label">BUSCA:</span>
            <input type="text" id="f-edit-busca" placeholder="título / financiador..." style="width:200px" oninput="renderEditais()">
          </div>
          <div class="filter-group"><span class="filter-label">ÁREA:</span>
            <select id="f-edit-area" onchange="renderEditais()"><option value="">TODAS</option></select>
          </div>
          <div class="filter-group"><span class="filter-label">STATUS:</span>
            <select id="f-edit-status" onchange="renderEditais()">
              <option value="">TODOS</option>
              <option value="ativo">Ativo</option>
              <option value="encerrado">Encerrado</option>
            </select>
          </div>
          <button class="btn" onclick="clearEditaisFilters()">LIMPAR</button>
        </div>

        <div id="editais-empty" style="display:none;" class="empty-state">
          <div style="color:var(--green3)">Nenhuma oportunidade encontrada com esses filtros</div>
          <div style="font-size:11px;color:var(--green-dim);margin-top:8px">Para carregar dados reais, execute:<br><code>python scripts/atualizar_tudo.py</code></div>
        </div>

        <div class="table-wrap" id="editais-table-wrap">
          <table>
            <thead><tr>
              <th>STATUS</th><th>PRAZO</th><th>OPORTUNIDADE</th>
              <th>FINANCIADOR</th><th>ÁREA</th><th>FONTE</th><th>LINK</th>
            </tr></thead>
            <tbody id="editais-body"></tbody>
          </table>
        </div>

      </div><!-- /view-editais -->

      <!-- ══════════════════════════ VIEW: BUSCA ══════════════════════════ -->
      <div id="view-busca" class="view">
        <div class="panel-header">
          <span class="panel-title">◈ BUSCA UNIVERSAL — PROJETOS · EMPRESAS · EDITAIS</span>
          <span id="busca-total" style="color:var(--green-dim);font-size:11px;"></span>
        </div>
        <div style="flex-shrink:0;padding:6px 12px;background:var(--bg2);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;">
          <span style="color:var(--green-dim);font-size:11px;">TEMA / MODALIDADE:</span>
          <input type="text" id="busca-input-main" placeholder="ex: canoagem, futebol, paralímpico, judô..." style="flex:1;font-size:12px;padding:4px 8px;" oninput="buscaUniversal(this.value)">
          <button class="btn" onclick="limparBusca()">✕ LIMPAR</button>
        </div>
        <div style="flex:1;overflow:auto;min-height:0;">

          <!-- Projetos -->
          <div style="border-bottom:1px solid var(--border);">
            <div style="padding:5px 12px;background:var(--bg3);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">
              <span style="color:var(--green);font-weight:bold;font-size:12px;">PROJETOS</span>
              <span id="busca-n-proj" style="color:var(--green-dim);font-size:11px;"></span>
            </div>
            <table style="width:100%;border-collapse:collapse;font-size:11px;">
              <thead><tr>
                <th style="background:var(--bg3);padding:4px 10px;text-align:left;font-weight:normal;border-bottom:1px solid var(--green-dim);font-size:10px;white-space:nowrap;">PROJETO</th>
                <th style="background:var(--bg3);padding:4px 10px;text-align:left;font-weight:normal;border-bottom:1px solid var(--green-dim);font-size:10px;white-space:nowrap;">MODALIDADE</th>
                <th style="background:var(--bg3);padding:4px 10px;text-align:left;font-weight:normal;border-bottom:1px solid var(--green-dim);font-size:10px;white-space:nowrap;">UF</th>
                <th style="background:var(--bg3);padding:4px 10px;text-align:left;font-weight:normal;border-bottom:1px solid var(--green-dim);font-size:10px;white-space:nowrap;">SALDO</th>
                <th style="background:var(--bg3);padding:4px 10px;text-align:left;font-weight:normal;border-bottom:1px solid var(--green-dim);font-size:10px;white-space:nowrap;">SCORE</th>
              </tr></thead>
              <tbody id="busca-proj-body"></tbody>
            </table>
          </div>

          <!-- Empresas -->
          <div style="border-bottom:1px solid var(--border);">
            <div style="padding:5px 12px;background:var(--bg3);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">
              <span style="color:var(--amber);font-weight:bold;font-size:12px;">EMPRESAS PATROCINADORAS</span>
              <span id="busca-n-emp" style="color:var(--green-dim);font-size:11px;"></span>
            </div>
            <table style="width:100%;border-collapse:collapse;font-size:11px;">
              <thead><tr>
                <th style="background:var(--bg3);padding:4px 10px;text-align:left;font-weight:normal;border-bottom:1px solid var(--green-dim);font-size:10px;white-space:nowrap;">EMPRESA</th>
                <th style="background:var(--bg3);padding:4px 10px;text-align:left;font-weight:normal;border-bottom:1px solid var(--green-dim);font-size:10px;white-space:nowrap;">SETOR</th>
                <th style="background:var(--bg3);padding:4px 10px;text-align:left;font-weight:normal;border-bottom:1px solid var(--green-dim);font-size:10px;white-space:nowrap;">REGIÃO</th>
                <th style="background:var(--bg3);padding:4px 10px;text-align:left;font-weight:normal;border-bottom:1px solid var(--green-dim);font-size:10px;white-space:nowrap;">POTENCIAL INV.</th>
                <th style="background:var(--bg3);padding:4px 10px;text-align:left;font-weight:normal;border-bottom:1px solid var(--green-dim);font-size:10px;white-space:nowrap;">SCORE</th>
              </tr></thead>
              <tbody id="busca-emp-body"></tbody>
            </table>
          </div>

          <!-- Editais -->
          <div>
            <div style="padding:5px 12px;background:var(--bg3);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">
              <span style="color:var(--green);font-weight:bold;font-size:12px;">EDITAIS E CHAMADAS PÚBLICAS</span>
              <span id="busca-n-edit" style="color:var(--green-dim);font-size:11px;"></span>
            </div>
            <table style="width:100%;border-collapse:collapse;font-size:11px;">
              <thead><tr>
                <th style="background:var(--bg3);padding:4px 10px;text-align:left;font-weight:normal;border-bottom:1px solid var(--green-dim);font-size:10px;white-space:nowrap;">STATUS</th>
                <th style="background:var(--bg3);padding:4px 10px;text-align:left;font-weight:normal;border-bottom:1px solid var(--green-dim);font-size:10px;white-space:nowrap;">PRAZO</th>
                <th style="background:var(--bg3);padding:4px 10px;text-align:left;font-weight:normal;border-bottom:1px solid var(--green-dim);font-size:10px;white-space:nowrap;">EDITAL</th>
                <th style="background:var(--bg3);padding:4px 10px;text-align:left;font-weight:normal;border-bottom:1px solid var(--green-dim);font-size:10px;white-space:nowrap;">FINANCIADOR</th>
                <th style="background:var(--bg3);padding:4px 10px;text-align:left;font-weight:normal;border-bottom:1px solid var(--green-dim);font-size:10px;white-space:nowrap;">ÁREA</th>
                <th style="background:var(--bg3);padding:4px 10px;text-align:left;font-weight:normal;border-bottom:1px solid var(--green-dim);font-size:10px;white-space:nowrap;">LINK</th>
              </tr></thead>
              <tbody id="busca-edit-body"></tbody>
            </table>
          </div>

        </div>
      </div><!-- /view-busca -->

      <!-- ══════════════════════════ VIEW: CONFIG ══════════════════════════ -->
      <div id="view-config" class="view">
        <div class="panel-header">
          <span class="panel-title">⚙ CONFIGURAÇÕES DO SISTEMA</span>
        </div>
        <div style="flex:1;overflow-y:auto;padding:16px 20px;max-width:720px;">

          <!-- Chaves de API -->
          <div style="margin-bottom:20px;">
            <div style="color:var(--green);font-weight:bold;font-size:12px;letter-spacing:1px;margin-bottom:4px;">━━━ CHAVES DE API ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</div>
            <div style="color:var(--green-dim);font-size:11px;margin-bottom:12px;">As chaves são salvas localmente no seu navegador (localStorage). Nunca são enviadas para nenhum servidor externo.</div>

            <!-- Portal da Transparência -->
            <div style="border:1px solid var(--border);padding:10px 14px;margin-bottom:10px;background:var(--bg2);">
              <div style="color:var(--green3);font-size:11px;margin-bottom:2px;">Portal da Transparência — Convênios &amp; Termos MROSC</div>
              <div style="color:var(--green-dim);font-size:10px;margin-bottom:6px;">Obter em: <span style="color:var(--green)">portaldatransparencia.gov.br/api-de-dados</span></div>
              <div style="display:flex;gap:6px;align-items:center;">
                <input type="password" id="input_PORTAL_TRANSPARENCIA_API_KEY" placeholder="cole sua chave aqui..."
                  style="flex:1;background:var(--bg2);border:1px solid var(--border);color:var(--green);font-family:var(--font);font-size:11px;padding:4px 8px;"
                  onfocus="desmascarar(this)" onblur="mascarar(this)">
                <button class="btn" onclick="toggleReveal('input_PORTAL_TRANSPARENCIA_API_KEY')" title="Revelar/ocultar">👁</button>
              </div>
            </div>

            <!-- Anthropic -->
            <div style="border:1px solid var(--border);padding:10px 14px;margin-bottom:12px;background:var(--bg2);">
              <div style="color:var(--green3);font-size:11px;margin-bottom:2px;">Anthropic Claude — Varredura inteligente de notícias</div>
              <div style="color:var(--green-dim);font-size:10px;margin-bottom:6px;">Obter em: <span style="color:var(--green)">console.anthropic.com</span></div>
              <div style="display:flex;gap:6px;align-items:center;">
                <input type="password" id="input_ANTHROPIC_API_KEY" placeholder="cole sua chave aqui..."
                  style="flex:1;background:var(--bg2);border:1px solid var(--border);color:var(--green);font-family:var(--font);font-size:11px;padding:4px 8px;"
                  onfocus="desmascarar(this)" onblur="mascarar(this)">
                <button class="btn" onclick="toggleReveal('input_ANTHROPIC_API_KEY')" title="Revelar/ocultar">👁</button>
              </div>
            </div>

            <div style="display:flex;gap:8px;">
              <button class="btn" onclick="saveConfig()" style="border-color:var(--green);color:var(--green);">✓ SALVAR CONFIGURAÇÕES</button>
              <button class="btn" onclick="clearConfig()">✕ LIMPAR TUDO</button>
              <button class="btn" onclick="gerarEnv()" style="margin-left:auto;">⬇ GERAR ARQUIVO .env</button>
            </div>
          </div>

          <!-- Status das fontes -->
          <div style="margin-bottom:20px;">
            <div style="color:var(--green);font-weight:bold;font-size:12px;letter-spacing:1px;margin-bottom:8px;">━━━ STATUS DAS FONTES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</div>
            <table style="width:100%;border-collapse:collapse;font-size:11px;">
              <tbody>
                <tr><td style="padding:4px 8px;color:var(--green3);">Portal da Transparência (Convênios)</td>  <td style="padding:4px 8px;" id="status_portal">—</td></tr>
                <tr><td style="padding:4px 8px;color:var(--green3);">Termos de Fomento MROSC (Lei 13.019)</td> <td style="padding:4px 8px;" id="status_mrosc">—</td></tr>
                <tr><td style="padding:4px 8px;color:var(--green3);">Claude IA — Varredura de Notícias</td>    <td style="padding:4px 8px;" id="status_claude">—</td></tr>
                <tr><td style="padding:4px 8px;color:var(--green3);">RSS: Obs. 3º Setor / Capta / GIFE</td>    <td style="padding:4px 8px;color:var(--green);">● SEMPRE ATIVO</td></tr>
                <tr><td style="padding:4px 8px;color:var(--green3);">RSS: Sebrae / Filantropia / Captadores</td><td style="padding:4px 8px;color:var(--green);">● SEMPRE ATIVO</td></tr>
                <tr><td style="padding:4px 8px;color:var(--green3);">RSS Gov.br: Esporte / Cultura / MDH / Transferegov</td><td style="padding:4px 8px;color:var(--green);">● SEMPRE ATIVO</td></tr>
                <tr><td style="padding:4px 8px;color:var(--green3);">RSS Fundações: Lemann / Itaú Social / Roberto Marinho / Gerdau</td><td style="padding:4px 8px;color:var(--green);">● SEMPRE ATIVO</td></tr>
              </tbody>
            </table>
          </div>

          <!-- Como atualizar -->
          <div>
            <div style="color:var(--green);font-weight:bold;font-size:12px;letter-spacing:1px;margin-bottom:8px;">━━━ COMO ATUALIZAR ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</div>
            <div style="color:var(--green-dim);font-size:11px;margin-bottom:6px;">Execute no terminal para atualizar todos os dados:</div>
            <div style="background:var(--bg3);border:1px solid var(--border);padding:8px 14px;font-size:11px;color:var(--green);margin-bottom:8px;">
              python scripts/atualizar_tudo.py
            </div>
            <button class="btn" onclick="navigator.clipboard.writeText('python scripts/atualizar_tudo.py').then(()=>showToast('✓ Copiado!'))">⎘ COPIAR COMANDO</button>
          </div>

        </div>
      </div><!-- /view-config -->

      <!-- ══════════════════════════ VIEW: ATUALIZAR ══════════════════════════ -->
      <div id="view-atualizar" class="view" style="overflow-y:auto;padding:20px 24px;">

        <!-- PAINEL 1: Projetos -->
        <div class="update-panel">
          <h3>&#x2501;&#x2501;&#x2501; PROJETOS &#x2014; LEI DE INCENTIVO AO ESPORTE</h3>
          <div style="font-size:11px;color:var(--green3);margin-bottom:10px;">
            Fonte oficial: <span style="color:var(--green)">Ministerio do Esporte</span>
            &nbsp;&#x2014;&nbsp; Frequencia: <span style="color:var(--green)">mensal</span>
          </div>
          <div class="status-box">
            <div class="status-row"><span class="status-label">Ultima importacao:</span>    <span class="status-value" id="upd-proj-data">—</span></div>
            <div class="status-row"><span class="status-label">Projetos carregados:</span>  <span class="status-value" id="upd-proj-total">—</span></div>
            <div class="status-row"><span class="status-label">Planilha base:</span>         <span class="status-value">projetos-ministerio-esporte.xlsx</span></div>
            <div class="status-row"><span class="status-label">Cobertura:</span>             <span class="status-value" id="upd-proj-cobertura">—</span></div>
            <div class="status-row"><span class="status-label">Valor total em captacao:</span> <span class="status-value" id="upd-proj-valor">—</span></div>
          </div>
          <div style="font-size:11px;color:var(--green3);margin-bottom:8px;">COMO ATUALIZAR:</div>
          <div style="margin-bottom:10px;">
            <div style="font-size:11px;color:var(--green-dim);margin-bottom:6px;">1. Baixe a planilha mais recente:</div>
            <a href="https://www.gov.br/esporte/pt-br/acoes-e-programas/lei-de-incentivo-ao-esporte" target="_blank" class="btn-external">&#x2197; ABRIR PAGINA DO MINISTERIO DO ESPORTE</a>
          </div>
          <div style="margin-bottom:10px;">
            <div style="font-size:11px;color:var(--green-dim);margin-bottom:6px;">2. Execute no terminal:</div>
            <button id="btn-copy-imp" class="btn-copy" onclick="copyCmd('python3 scripts/importar_ministerio_esporte.py /caminho/planilha.xlsx', 'btn-copy-imp')">[ COPIAR COMANDO ]</button>
            <code style="font-size:11px;color:var(--green3)">python3 scripts/importar_ministerio_esporte.py /caminho/planilha.xlsx</code>
          </div>
          <div>
            <div style="font-size:11px;color:var(--green-dim);margin-bottom:6px;">3. Regenere o dashboard:</div>
            <button id="btn-copy-regen1" class="btn-copy" onclick="copyCmd('python3 scripts/gerar_dashboard.py', 'btn-copy-regen1')">[ COPIAR COMANDO ]</button>
            <code style="font-size:11px;color:var(--green3)">python3 scripts/gerar_dashboard.py</code>
          </div>
        </div>

        <!-- PAINEL 2: Editais/Oportunidades -->
        <div class="update-panel">
          <h3>&#x2501;&#x2501;&#x2501; OPORTUNIDADES &#x2014; FONTES ATIVAS</h3>
          <div class="status-box">
            <div class="status-row"><span class="status-label">Ultima coleta:</span>    <span class="status-value" id="upd-edit-data">—</span></div>
            <div class="status-row"><span class="status-label">Oportunidades:</span>    <span class="status-value" id="upd-edit-ativos">—</span></div>
            <div class="status-row"><span class="status-label">Dados reais:</span>      <span class="status-value" id="upd-edit-real">—</span></div>
          </div>
          <div style="font-size:11px;color:var(--green3);margin-bottom:8px;">FONTES CONFIGURADAS:</div>
          <div style="margin-bottom:12px;">
            <div class="fonte-row"><span class="fonte-status-ok">●</span> RSS Observatorio 3o Setor</div>
            <div class="fonte-row"><span class="fonte-status-ok">●</span> RSS Capta / Prosas</div>
            <div class="fonte-row"><span class="fonte-status-ok">●</span> RSS GIFE, Filantropia, Sebrae</div>
            <div class="fonte-row"><span class="fonte-status-ok">●</span> RSS Fundacoes Empresariais</div>
            <div class="fonte-row"><span class="fonte-status-ok">●</span> RSS Fundos Publicos Gov.br</div>
            <div class="fonte-row"><span id="upd-fonte-portal">○ chave nao configurada</span>&nbsp;&nbsp;Portal da Transparencia API</div>
            <div class="fonte-row"><span id="upd-fonte-claude">○ chave nao configurada</span>&nbsp;&nbsp;Varredura IA (Claude Haiku)</div>
          </div>
          <div style="font-size:11px;color:var(--green3);margin-bottom:8px;">COMO ATUALIZAR:</div>
          <div style="margin-bottom:10px;">
            <button id="btn-copy-atu" class="btn-copy" onclick="copyCmd('python3 scripts/atualizar_tudo.py', 'btn-copy-atu')">[ COPIAR COMANDO ]</button>
            <code style="font-size:11px;color:var(--green3)">python3 scripts/atualizar_tudo.py</code>
          </div>
          <div>
            <div style="font-size:11px;color:var(--green-dim);margin-bottom:6px;">Ou agende atualizacao diaria automatica:</div>
            <button id="btn-copy-cron" class="btn-copy" onclick="copyCmd('0 7 * * * cd /caminho/projeto &amp;&amp; python3 scripts/atualizar_tudo.py >> logs/atualizacao.log 2>&amp;1', 'btn-copy-cron')">[ COPIAR CRON ]</button>
            <code style="font-size:11px;color:var(--green3)">0 7 * * * cd /caminho/projeto &amp;&amp; python3 scripts/atualizar_tudo.py >> logs/atualizacao.log 2&gt;&amp;1</code>
          </div>
        </div>

        <!-- PAINEL 3: Empresas Patrocinadoras -->
        <div class="update-panel">
          <h3>&#x2501;&#x2501;&#x2501; EMPRESAS &#x2014; BASE REAL LIE + ROUANET</h3>
          <div style="font-size:11px;color:var(--green3);margin-bottom:10px;">
            Fonte: <span style="color:var(--green)">Prosas (Paineis LIE + Rouanet, 2022-2025)</span>
            &nbsp;&#x2014;&nbsp; Filtro: <span style="color:var(--green)">total &ge; R$ 100.000</span>
          </div>
          <div class="status-box">
            <div class="status-row"><span class="status-label">Ultima importacao:</span>       <span class="status-value" id="upd-emp-data">—</span></div>
            <div class="status-row"><span class="status-label">Total de empresas:</span>       <span class="status-value" id="upd-emp-total">—</span></div>
            <div class="status-row"><span class="status-label">Setores representados:</span>   <span class="status-value" id="upd-emp-setores">—</span></div>
            <div class="status-row"><span class="status-label">Potencial total estimado:</span><span class="status-value" id="upd-emp-potencial">—</span></div>
            <div style="margin-top:8px;font-size:11px;color:var(--green3);">PORTE:</div>
            <div class="status-row"><span class="status-label">Grandes (&ge; R$ 50M):</span>  <span class="status-value" id="upd-emp-grandes">—</span></div>
            <div class="status-row"><span class="status-label">Medias (R$ 5M-50M):</span>     <span class="status-value" id="upd-emp-medias">—</span></div>
            <div class="status-row"><span class="status-label">Pequenas (R$ 500k-5M):</span>  <span class="status-value" id="upd-emp-pequenas">—</span></div>
          </div>
          <div style="font-size:11px;color:var(--green3);margin-bottom:8px;">COMO ATUALIZAR:</div>
          <div style="margin-bottom:10px;">
            <div style="font-size:11px;color:var(--green-dim);margin-bottom:6px;">1. Baixe a base atualizada do Prosas e salve em data/empresas_patrocinadores_base.csv</div>
            <div style="font-size:11px;color:var(--green-dim);margin-bottom:6px;">2. Execute:</div>
            <button id="btn-copy-imp-emp" class="btn-copy" onclick="copyCmd('python3 scripts/importar_empresas.py', 'btn-copy-imp-emp')">[ COPIAR COMANDO ]</button>
            <code style="font-size:11px;color:var(--green3)">python3 scripts/importar_empresas.py</code>
          </div>
          <div>
            <div style="font-size:11px;color:var(--green-dim);margin-bottom:6px;">3. Recalcule matches e regenere:</div>
            <button id="btn-copy-match-emp" class="btn-copy" onclick="copyCmd('python3 scripts/matching.py && python3 scripts/gerar_dashboard.py', 'btn-copy-match-emp')">[ COPIAR COMANDO ]</button>
            <code style="font-size:11px;color:var(--green3)">python3 scripts/matching.py &amp;&amp; python3 scripts/gerar_dashboard.py</code>
          </div>
        </div>

        <!-- PAINEL 4: Saude do Sistema -->
        <div class="update-panel">
          <h3>&#x2501;&#x2501;&#x2501; SAUDE DO SISTEMA</h3>
          <div class="status-box">
            <div class="status-row"><span class="status-label">Dashboard gerado em:</span>  <span class="status-value" id="upd-sys-gerado">—</span></div>
            <div class="status-row"><span class="status-label">Versao dos dados:</span>     <span class="status-value" id="upd-sys-versao">—</span></div>
            <div style="margin-top:8px;font-size:11px;color:var(--green3);">ARQUIVOS DE DADOS:</div>
            <div class="status-row"><span class="status-label">projetos_reais_tratados.csv</span>  <span class="status-value"><span id="upd-sys-projetos">—</span> registros</span></div>
            <div class="status-row"><span class="status-label">empresas_potenciais.csv</span>      <span class="status-value"><span id="upd-sys-empresas">—</span> registros</span></div>
            <div class="status-row"><span class="status-label">editais.csv</span>                   <span class="status-value"><span id="upd-sys-editais">—</span> registros</span></div>
            <div style="margin-top:8px;font-size:11px;color:var(--green3);">MATCHES CALCULADOS:</div>
            <div class="status-row"><span class="status-label">Projetos x Empresas:</span>   <span class="status-value"><span id="upd-sys-memp">—</span> pares (score &#x2265; 0.50)</span></div>
            <div class="status-row"><span class="status-label">Projetos x Oportunidades:</span> <span class="status-value"><span id="upd-sys-medit">—</span> pares (score &#x2265; 0.30)</span></div>
          </div>
          <div style="font-size:11px;color:var(--green3);margin-bottom:8px;">REGENERAR DASHBOARD:</div>
          <div style="margin-bottom:10px;">
            <button id="btn-copy-regen2" class="btn-copy" onclick="copyCmd('python3 scripts/gerar_dashboard.py', 'btn-copy-regen2')">[ COPIAR COMANDO ]</button>
            <code style="font-size:11px;color:var(--green3)">python3 scripts/gerar_dashboard.py</code>
          </div>
          <div>
            <div style="font-size:11px;color:var(--green-dim);margin-bottom:6px;">Atualizacao completa (projetos + editais + dashboard):</div>
            <button id="btn-copy-full" class="btn-copy" onclick="copyCmd('python3 scripts/atualizar_tudo.py', 'btn-copy-full')">[ COPIAR COMANDO ]</button>
            <code style="font-size:11px;color:var(--green3)">python3 scripts/atualizar_tudo.py</code>
          </div>
        </div>

      </div><!-- /view-atualizar -->

    </div><!-- /content -->
  </div><!-- /main -->

  <!-- ══ MODAL: COMO ATUALIZAR ══════════════════════════════════════════════ -->
  <div id="modal-overlay" onclick="closeModalOutside(event)">
    <div id="modal-box">
      <div class="modal-title">
        ↺ COMO ATUALIZAR OS EDITAIS
        <button onclick="closeModal()" style="background:none;border:none;color:var(--green3);font-size:16px;cursor:pointer;font-family:var(--font);">✕</button>
      </div>
      <div class="modal-body">
        <div>Para atualizar os editais com dados do dia, execute os comandos abaixo no terminal:</div>
        <div class="modal-cmd">
          <div style="color:var(--green-dim);margin-bottom:4px;"># Na pasta do projeto:</div>
          <code>python scripts/coletar_editais.py</code><br>
          <code>python scripts/matching_editais.py</code><br>
          <code>python scripts/gerar_dashboard.py</code>
        </div>
        <div style="color:var(--green-dim);font-size:11px;">Depois abra novamente o arquivo <span style="color:var(--green)">app/dashboard.html</span></div>
        <div style="margin-top:8px;color:var(--green-dim);font-size:10px;">Atalho: <span style="color:var(--green)">python scripts/atualizar_tudo.py</span> — executa os 3 passos de uma vez.</div>
      </div>
      <div class="modal-footer">
        <button class="btn" id="btn-copiar" onclick="copiarComandos()">⎘ Copiar comandos</button>
        <button class="btn" onclick="closeModal()" style="border-color:var(--green);color:var(--green);">✕ Fechar</button>
      </div>
    </div>
  </div>

  <div id="statusbar">
    HUB DE CAPTAÇÃO v2.0 &nbsp;|&nbsp; Lei de Incentivo ao Esporte &nbsp;|&nbsp;
    <span style="color:var(--green)">SISTEMA OPERACIONAL</span> &nbsp;|&nbsp;
    Dados: __HOJE__
  </div>
</div>

<script>
// ── DATA ──────────────────────────────────────────────────────────────────
const PROJETOS      = __PROJ_JSON__;
const EMPRESAS      = __EMP_JSON__;
const MATCHES       = __MATCH_JSON__;
const EDITAIS       = __EDITAIS_JSON__;
const MATCH_EDITAIS = __MATCH_EDITAIS_JSON__;
const TODOS_DEMO    = __TODOS_DEMO__;
const META_PROJETOS  = __META_PROJETOS_JSON__;
const META_EDITAIS   = __META_EDITAIS_JSON__;
const META_EMPRESAS  = __META_EMPRESAS_JSON__;
const META_SISTEMA   = __META_SISTEMA_JSON__;

// ── STATE ─────────────────────────────────────────────────────────────────
let projFiltered  = [...PROJETOS];
let empFiltered   = [...EMPRESAS];
let selectedProj  = null;
let matchProjList = [...PROJETOS];
const sortState   = {
  proj: { col: 'score_prioridade', asc: false },
  emp:  { col: 'score_empresa',    asc: false },
};

// ── HELPERS ───────────────────────────────────────────────────────────────
function fmtBRL(v) {
  v = parseFloat(v) || 0;
  if (v >= 1e9) return 'R$ ' + (v/1e9).toFixed(1) + 'B';
  if (v >= 1e6) return 'R$ ' + (v/1e6).toFixed(1) + 'M';
  if (v >= 1e3) return 'R$ ' + (v/1e3).toFixed(0) + 'K';
  return 'R$ ' + v.toFixed(0);
}
function scCls(v) {
  v = parseFloat(v) || 0;
  if (v >= 0.70) return 'score-high';
  if (v >= 0.45) return 'score-mid';
  return 'score-low';
}
function fmtSc(v) {
  return `<span class="${scCls(v)}">${parseFloat(v).toFixed(2)}</span>`;
}
function pctStr(captado, aprovado) {
  if (!aprovado || aprovado == 0) return '—';
  return (parseFloat(captado)/parseFloat(aprovado)*100).toFixed(0) + '%';
}
function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function fmtPrazo(dias) {
  const d = parseInt(dias);
  if (isNaN(d) || d === -1) return '<span class="prazo-none">—</span>';
  if (d <= 0)  return '<span class="prazo-urgent">ENCERRADO</span>';
  if (d <= 7)  return `<span class="prazo-urgent">${d}d ⚠</span>`;
  if (d <= 30) return `<span class="prazo-warn">${d}d</span>`;
  return `<span class="prazo-ok">${d}d</span>`;
}

// ── INIT ──────────────────────────────────────────────────────────────────
function init() {
  populateFilters();
  renderProjetos();
  renderEmpresas();
  renderRadar();
  renderMatchLeft();
  renderEditaisStats();
  renderEditais();
  renderTicker();
  initDemoBanner();
  initConfigView();
}

function populateFilters() {
  const ufs    = [...new Set(PROJETOS.map(p=>p.uf))].sort();
  const regs   = [...new Set(PROJETOS.map(p=>p.regiao))].sort();
  const mods   = [...new Set(PROJETOS.map(p=>p.modalidade_esportiva))].sort();
  const anos   = [...new Set(PROJETOS.map(p=>String(p.ano_aprovacao)))].sort();
  const setors = [...new Set(EMPRESAS.map(e=>e.setor))].sort();
  const regemp = [...new Set(EMPRESAS.map(e=>e.regiao_sede))].sort();
  const areasSet = new Set();
  EDITAIS.forEach(e => String(e.areas_tematicas||'').split('|').forEach(a => { const t=a.trim(); if(t) areasSet.add(t); }));
  const areas = [...areasSet].sort();

  const fill = (id, arr) => {
    const sel = document.getElementById(id);
    if (!sel) return;
    arr.forEach(v => { const o = document.createElement('option'); o.value=v; o.textContent=v; sel.appendChild(o); });
  };
  fill('f-uf', ufs); fill('f-regiao', regs); fill('f-modalidade', mods); fill('f-ano', anos);
  fill('f-emp-setor', setors); fill('f-emp-regiao', regemp);
  fill('f-edit-area', areas);
}

// ── VIEWS ─────────────────────────────────────────────────────────────────
function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('view-' + name).classList.add('active');
  var navBtn = document.getElementById('nav-' + name);
  if (navBtn) navBtn.classList.add('active');
  if (name === 'atualizar') initAtualizarView();
  if (name === 'config')    initConfigView();
}

// ── TABS (proj detail) ─────────────────────────────────────────────────────
function switchTab(tab) {
  ['emp','edit'].forEach(t => {
    document.getElementById('tb-' + t).classList.toggle('active', t === tab);
    document.getElementById('pane-' + t).classList.toggle('active', t === tab);
  });
}

// ── TABS (matching right panel) ────────────────────────────────────────────
function switchMatchTab(tab) {
  ['emp','edit'].forEach(t => {
    document.getElementById('mrt-' + t).classList.toggle('active', t === tab);
    document.getElementById('mrp-' + t).classList.toggle('active', t === tab);
  });
}

// ── FILTERS ───────────────────────────────────────────────────────────────
function applyFilters() {
  const busca    = (document.getElementById('f-busca').value||'').toLowerCase();
  const uf       = document.getElementById('f-uf').value;
  const regiao   = document.getElementById('f-regiao').value;
  const mod      = document.getElementById('f-modalidade').value;
  const ano      = document.getElementById('f-ano').value;
  const scoreMin = parseFloat(document.getElementById('f-score').value) || 0;
  const saldoMin = parseFloat(document.getElementById('f-saldo').value) || 0;

  PROJ_PAGE = 0;
  projFiltered = PROJETOS.filter(p => {
    if (busca && !p.nome_projeto.toLowerCase().includes(busca) &&
        !p.proponente.toLowerCase().includes(busca)) return false;
    if (uf     && p.uf !== uf) return false;
    if (regiao && p.regiao !== regiao) return false;
    if (mod    && p.modalidade_esportiva !== mod) return false;
    if (ano    && String(p.ano_aprovacao) !== ano) return false;
    if (parseFloat(p.score_prioridade) < scoreMin) return false;
    if (parseFloat(p.saldo_disponivel)  < saldoMin) return false;
    return true;
  });
  renderProjetos();
}

function clearFilters() {
  ['f-busca','f-score','f-saldo'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  ['f-uf','f-regiao','f-modalidade','f-ano'].forEach(id => {
    const el = document.getElementById(id); if (el) el.selectedIndex = 0;
  });
  PROJ_PAGE = 0;
  projFiltered = [...PROJETOS];
  selectedProj = null;
  document.getElementById('match-proj-name').textContent = 'Clique em um projeto acima para ver empresas e editais compatíveis';
  document.getElementById('tc-emp').textContent  = '';
  document.getElementById('tc-edit').textContent = '';
  document.getElementById('match-body').innerHTML = '';
  document.getElementById('match-edit-body').innerHTML =
    '<tr><td colspan="8" style="color:var(--green-dim);text-align:center;padding:10px;">Selecione um projeto acima</td></tr>';
  renderProjetos();
  showView('projetos');
}

function clearEmpFilters() {
  const b = document.getElementById('f-emp-busca'); if (b) b.value = '';
  ['f-emp-setor','f-emp-regiao'].forEach(id => { const el = document.getElementById(id); if (el) el.selectedIndex = 0; });
  renderEmpresas();
}

function clearEditaisFilters() {
  const b = document.getElementById('f-edit-busca'); if (b) b.value = '';
  ['f-edit-area','f-edit-status'].forEach(id => { const el = document.getElementById(id); if (el) el.selectedIndex = 0; });
  renderEditais();
}

function qfRegiao(r) {
  clearFilters();
  const sel = document.getElementById('f-regiao');
  if (sel) sel.value = r;
  applyFilters();
  showView('projetos');
}

// ── SORT ──────────────────────────────────────────────────────────────────
function sortT(type, col) {
  const state = sortState[type];
  state.asc = state.col === col ? !state.asc : false;
  state.col = col;
  const cmp = (a, b) => {
    let va = a[col], vb = b[col];
    if (va !== '' && vb !== '' && !isNaN(va) && !isNaN(vb)) { va = parseFloat(va); vb = parseFloat(vb); }
    if (va < vb) return state.asc ? -1 : 1;
    if (va > vb) return state.asc ? 1 : -1;
    return 0;
  };
  if (type === 'proj') { projFiltered.sort(cmp); renderProjetos(); }
  else                 { empFiltered.sort(cmp);  renderEmpresas(); }
  document.querySelectorAll('th').forEach(th => {
    const si = th.querySelector('.si'); if (!si) return;
    const thCol = th.getAttribute('onclick') || '';
    if (thCol.includes(`'${col}'`)) {
      th.classList.add('sorted'); si.textContent = state.asc ? '↑' : '↓';
    } else {
      th.classList.remove('sorted'); si.textContent = '⇅';
    }
  });
}

// ── RENDER PROJETOS ───────────────────────────────────────────────────────
// ── PAGINACAO DE PROJETOS ─────────────────────────────────────────────────
var PROJ_PAGE      = 0;
var PROJ_POR_PAG   = 100;

function renderProjetos() {
  var total     = projFiltered.length;
  var totalPags = Math.max(1, Math.ceil(total / PROJ_POR_PAG));
  if (PROJ_PAGE >= totalPags) PROJ_PAGE = totalPags - 1;
  var inicio = PROJ_PAGE * PROJ_POR_PAG;
  var fim    = Math.min(inicio + PROJ_POR_PAG, total);
  var pagina = projFiltered.slice(inicio, fim);

  document.getElementById('proj-count').textContent =
    total.toLocaleString('pt-BR') + ' projetos  |  pag. ' + (PROJ_PAGE+1) + '/' + totalPags;

  document.getElementById('proj-body').innerHTML = pagina.map(function(p, i) {
    var absIdx = inicio + i;
    var sel = selectedProj && selectedProj.nome_projeto === p.nome_projeto ? ' selected' : '';
    var pct = pctStr(p.valor_captado, p.valor_aprovado);
    return '<tr class="' + sel + '" onclick="selectProj(' + absIdx + ')">' +
      '<td>' + esc(p.nome_projeto) + '</td>' +
      '<td style="color:var(--green3);font-size:11px">' + esc(p.proponente) + '</td>' +
      '<td><span class="badge">' + esc(p.uf) + '</span></td>' +
      '<td style="color:var(--green3)">' + esc(p.modalidade_esportiva) + '</td>' +
      '<td style="color:var(--green3)">' + p.ano_aprovacao + '</td>' +
      '<td>' + fmtBRL(p.valor_aprovado) + '</td>' +
      '<td style="color:var(--green3)">' + fmtBRL(p.valor_captado) + ' <small style="color:var(--green-dim)">(' + pct + ')</small></td>' +
      '<td style="color:var(--amber);font-weight:bold">' + fmtBRL(p.saldo_disponivel) + '</td>' +
      '<td>' + fmtSc(p.score_prioridade) + '</td>' +
      '</tr>';
  }).join('');

  // Atualizar controles de paginacao
  var ctrl = document.getElementById('proj-pag-ctrl');
  if (ctrl) {
    ctrl.innerHTML =
      '<button class="btn" onclick="projPagAnterior()" ' + (PROJ_PAGE===0?'disabled style="opacity:.4"':'') + '>&larr; ANTERIOR</button>' +
      '&nbsp;<span style="font-size:11px;color:var(--green3)">Pag. ' + (PROJ_PAGE+1) + ' / ' + totalPags + '  (' + inicio+1 + '-' + fim + ' de ' + total.toLocaleString('pt-BR') + ')</span>&nbsp;' +
      '<button class="btn" onclick="projPagProxima()" ' + (PROJ_PAGE>=totalPags-1?'disabled style="opacity:.4"':'') + '>PROXIMO &rarr;</button>';
  }
}

function projPagAnterior() { if (PROJ_PAGE > 0) { PROJ_PAGE--; renderProjetos(); } }
function projPagProxima()   { PROJ_PAGE++; renderProjetos(); }

function selectProj(idx) {
  selectedProj = projFiltered[idx];
  _loadProjDetail(selectedProj,
    'match-proj-name', 'tc-emp', 'tc-edit', 'match-body', 'match-edit-body');
  renderProjetos();
}

function _loadProjDetail(proj, nameId, cEmpId, cEditId, empBodyId, editBodyId) {
  document.getElementById(nameId).textContent = proj.nome_projeto + '  |  ' + proj.uf + '  |  ' + proj.modalidade_esportiva;

  // companies
  const projMatches = MATCHES
    .filter(m => m.nome_projeto === proj.nome_projeto)
    .sort((a,b) => parseFloat(b.score_match) - parseFloat(a.score_match));
  document.getElementById(cEmpId).textContent = '(' + projMatches.length + ')';
  const empMap = {};
  EMPRESAS.forEach(e => { empMap[e.nome_empresa] = e; });
  document.getElementById(empBodyId).innerHTML = projMatches.length
    ? projMatches.map((m, i) => {
        const emp = empMap[m.nome_empresa] || {};
        const regiao = emp.regiao_sede || '—';
        return `<tr>
          <td style="color:var(--green-dim)">${i+1}</td>
          <td style="font-weight:bold">${esc(m.nome_empresa)}</td>
          <td style="color:var(--green3);font-size:11px">${esc(emp.setor||'—')}</td>
          <td><span class="badge">${esc(emp.uf_sede||'—')}</span></td>
          <td style="color:var(--amber)">${fmtBRL(emp.potencial_investimento)}</td>
          <td style="color:var(--green3)">${parseFloat(m.score_geo||0).toFixed(2)}</td>
          <td style="color:var(--green3)">${parseFloat(m.score_setor||0).toFixed(2)}</td>
          <td style="color:var(--green3)">${parseFloat(m.score_financeiro||0).toFixed(2)}</td>
          <td>${fmtSc(m.score_match)}</td>
        </tr>`;
      }).join('')
    : '<tr><td colspan="9" style="color:var(--green-dim);text-align:center;padding:10px;">Nenhuma empresa compatível</td></tr>';

  // editais
  const editMatches = MATCH_EDITAIS
    .filter(m => m.nome_projeto === proj.nome_projeto)
    .sort((a,b) => parseFloat(b.score_match) - parseFloat(a.score_match));
  document.getElementById(cEditId).textContent = '(' + editMatches.length + ')';
  document.getElementById(editBodyId).innerHTML = editMatches.length
    ? editMatches.map(m => {
        const area = String(m.areas_tematicas||m.titulo_edital||'').split('|')[0].trim().substring(0,30) || '—';
        const textoAreaM = (m.titulo_edital||'') + (m.areas_tematicas||'') + (m.financiador||'');
        const areaBdgM = _areaBadge(textoAreaM);
        const link = String(m.url_edital||'').length > 5
          ? `<a href="${esc(m.url_edital)}" target="_blank" style="color:var(--amber);text-decoration:none;font-weight:bold;">[→]</a>`
          : '<span style="color:var(--green-dim)">—</span>';
        return `<tr>
          <td>${fmtSc(m.score_match)}</td>
          <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;font-size:11px">${esc(m.titulo_edital)}</td>
          <td style="color:var(--green3);font-size:11px">${esc(m.financiador)}</td>
          <td>${fmtPrazo(m.dias_restantes)}</td>
          <td style="font-size:10px;max-width:110px;overflow:hidden;text-overflow:ellipsis">${areaBdgM} ${esc(area)}</td>
          <td style="color:var(--green3)">${parseFloat(m.score_uf||0).toFixed(2)}</td>
          <td style="color:var(--green3)">${parseFloat(m.score_tematico||0).toFixed(2)}</td>
          <td>${link}</td>
        </tr>`;
      }).join('')
    : '<tr><td colspan="8" style="color:var(--green-dim);text-align:center;padding:10px;">Nenhum edital compatível</td></tr>';
}

// ── RENDER EMPRESAS ───────────────────────────────────────────────────────
function renderEmpresas() {
  const busca  = (document.getElementById('f-emp-busca').value||'').toLowerCase();
  const setor  = document.getElementById('f-emp-setor').value;
  const regiao = document.getElementById('f-emp-regiao').value;
  empFiltered = EMPRESAS.filter(e => {
    if (busca  && !e.nome_empresa.toLowerCase().includes(busca) &&
        !e.setor.toLowerCase().includes(busca)) return false;
    if (setor  && e.setor !== setor) return false;
    if (regiao && e.regiao_sede !== regiao) return false;
    return true;
  });
  empFiltered.sort((a,b) => parseFloat(b.score_empresa) - parseFloat(a.score_empresa));
  document.getElementById('emp-count').textContent = empFiltered.length + ' empresas';
  document.getElementById('emp-body').innerHTML = empFiltered.map(e => {
    const site = String(e.site||'').replace(/https?:\/\//,'').split('/')[0];
    const intl = e.regiao_sede === 'Internacional' ? ' 🌐' : '';
    return `<tr>
      <td>${fmtSc(e.score_empresa)}</td>
      <td style="font-weight:bold">${esc(e.nome_empresa)}${intl}</td>
      <td style="color:var(--green3);font-size:11px">${esc(e.setor)}</td>
      <td><span class="badge">${esc(e.uf_sede)}</span></td>
      <td style="color:var(--green3)">${esc(e.regiao_sede)}</td>
      <td>${fmtBRL(e.faturamento_anual)}</td>
      <td style="color:var(--amber);font-weight:bold">${fmtBRL(e.potencial_investimento)}</td>
      <td><a href="${esc(e.site)}" target="_blank" style="color:var(--green-dim);font-size:10px;text-decoration:none"
             onmouseover="this.style.color='var(--green)'" onmouseout="this.style.color='var(--green-dim)'">${esc(site)}</a></td>
    </tr>`;
  }).join('');
}

// ── RENDER RADAR ──────────────────────────────────────────────────────────
function renderRadar() {
  const hoje = new Date();
  const maioresSaldos = [...PROJETOS].sort((a,b) => parseFloat(b.saldo_disponivel) - parseFloat(a.saldo_disponivel)).slice(0,14);
  const comDias = PROJETOS.map(p => {
    const fim  = new Date(p.data_fim_captacao);
    const dias = Math.floor((fim - hoje) / (1000*60*60*24));
    return { ...p, _dias: dias };
  });
  const encerrando = comDias.filter(p => p._dias >= 0 && p._dias <= 120).sort((a,b) => a._dias - b._dias).slice(0,14);
  const altaPrio   = PROJETOS.filter(p => parseFloat(p.score_prioridade) >= 0.70)
    .sort((a,b) => parseFloat(b.score_prioridade) - parseFloat(a.score_prioridade)).slice(0,14);
  const momentum   = PROJETOS.filter(p => {
    const pct = parseFloat(p.valor_captado)/(parseFloat(p.valor_aprovado)||1);
    return pct > 0.3 && parseFloat(p.saldo_disponivel) > 200000;
  }).sort((a,b) => parseFloat(b.saldo_disponivel) - parseFloat(a.saldo_disponivel)).slice(0,14);

  document.getElementById('r1-c').textContent = `(${maioresSaldos.length})`;
  document.getElementById('r2-c').textContent = `(${encerrando.length})`;
  document.getElementById('r3-c').textContent = `(${altaPrio.length})`;
  document.getElementById('r4-c').textContent = `(${momentum.length})`;

  document.getElementById('r-saldos').innerHTML = maioresSaldos.map(p =>
    `<div class="radar-row"><span class="radar-name">${esc(p.nome_projeto)}</span>
     <span class="radar-uf">${p.uf}</span><span class="radar-val">${fmtBRL(p.saldo_disponivel)}</span></div>`).join('');

  document.getElementById('r-encerrando').innerHTML = encerrando.length
    ? encerrando.map(p =>
        `<div class="radar-row"><span class="radar-name">${esc(p.nome_projeto)}</span>
         <span class="radar-uf">${p.uf}</span>
         <span class="radar-val" style="color:${p._dias<=30?'var(--red)':'var(--amber)'}">${p._dias}d</span></div>`).join('')
    : '<div class="radar-row"><span class="radar-name" style="color:var(--green-dim)">Nenhum encerrando em breve</span></div>';

  document.getElementById('r-prioridade').innerHTML = altaPrio.map(p =>
    `<div class="radar-row"><span class="radar-name">${esc(p.nome_projeto)}</span>
     <span class="radar-uf">${p.uf}</span><span class="radar-val score-high">${parseFloat(p.score_prioridade).toFixed(2)}</span></div>`).join('');

  document.getElementById('r-momentum').innerHTML = momentum.map(p => {
    const pct = (parseFloat(p.valor_captado)/(parseFloat(p.valor_aprovado)||1)*100).toFixed(0);
    return `<div class="radar-row"><span class="radar-name">${esc(p.nome_projeto)}</span>
      <span class="radar-uf">${p.uf}</span>
      <span class="radar-val">${fmtBRL(p.saldo_disponivel)} <small style="color:var(--green3)">${pct}%</small></span></div>`;
  }).join('');
}

// ── RENDER MATCHING LEFT ──────────────────────────────────────────────────
function renderMatchLeft() {
  const busca = (document.getElementById('f-match-busca').value||'').toLowerCase();
  matchProjList = busca
    ? PROJETOS.filter(p => p.nome_projeto.toLowerCase().includes(busca) || p.uf.toLowerCase().includes(busca))
    : [...PROJETOS];
  matchProjList.sort((a,b) => parseFloat(b.score_prioridade) - parseFloat(a.score_prioridade));
  document.getElementById('matching-proj-count').textContent = matchProjList.length + ' projetos';
  document.getElementById('match-left-body').innerHTML = matchProjList.map((p, i) => {
    const sel = selectedProj && selectedProj.nome_projeto === p.nome_projeto ? ' selected' : '';
    return `<tr class="${sel}" onclick="selectMatchProj(${i})">
      <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;">${esc(p.nome_projeto)}</td>
      <td><span class="badge">${esc(p.uf)}</span></td>
      <td style="color:var(--amber)">${fmtBRL(p.saldo_disponivel)}</td>
    </tr>`;
  }).join('');
}

function selectMatchProj(idx) {
  selectedProj = matchProjList[idx];
  document.getElementById('match-right-empty').style.display  = 'none';
  document.getElementById('match-right-detail').style.display = 'flex';
  document.getElementById('mr-proj-name').textContent = selectedProj.nome_projeto;
  document.getElementById('mr-proj-meta').textContent =
    selectedProj.uf + ' | ' + selectedProj.modalidade_esportiva + ' | Saldo: ' + fmtBRL(selectedProj.saldo_disponivel);
  _loadProjDetail(selectedProj,
    'mr-proj-name', 'mrc-emp', 'mrc-edit', 'mr-emp-body', 'mr-edit-body');
  renderMatchLeft();
}

// ── RENDER EDITAIS STATS ──────────────────────────────────────────────────
function renderEditaisStats() {
  if (!EDITAIS || EDITAIS.length === 0) return;
  const ativos = EDITAIS.filter(e => String(e.status||'').toLowerCase() === 'ativo');
  const em30   = ativos.filter(e => { const d = parseInt(e.dias_restantes); return d >= 0 && d <= 30; });
  const em7    = ativos.filter(e => { const d = parseInt(e.dias_restantes); return d >= 0 && d <= 7;  });
  document.getElementById('es-ativos').textContent  = ativos.length;
  document.getElementById('es-30d').textContent     = em30.length;
  document.getElementById('es-7d').textContent      = em7.length;
  document.getElementById('es-updated').textContent = '__HOJE__';
}

// ── FILTROS DE AREA ───────────────────────────────────────────────────────
let _areaFiltroAtual = 'todos';

function filtrarAreaEditais(area) {
  _areaFiltroAtual = area;
  document.querySelectorAll('.filter-area-btn').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('fab-' + area);
  if (btn) btn.classList.add('active');
  renderEditais();
}

function _filtrarPorArea(editais) {
  if (_areaFiltroAtual === 'todos') return editais;
  const mapa = {
    'esporte':  ['esporte','atletismo','futebol','olympic','paralimpic','sport','swim','basquete','volei','ginastic','modalidade'],
    'cultura':  ['cultura','rouanet','arte','music','teatro','cinema','audiovisual','patrimoni','cultur'],
    'educacao': ['educacao','educação','escola','jovem','adolescente','criança','infancia','juventude','aprendiz'],
    'social':   ['social','osc','assistencia','vulneravel','diversidade','inclusao','terceiro setor','comunidade','habitacao'],
  };
  const palavras = mapa[_areaFiltroAtual] || [];
  return editais.filter(e => {
    const texto = ((e.titulo||'') + (e.areas_tematicas||'') + (e.financiador||'')).toLowerCase();
    if (_areaFiltroAtual === 'outros') {
      const todas = Object.values(mapa).flat();
      return !todas.some(p => texto.includes(p));
    }
    return palavras.some(p => texto.includes(p));
  });
}

function _areaBadge(texto) {
  const t = (texto||'').toLowerCase();
  if (['esporte','atletismo','futebol','olympic','paralimpic','sport','modalidade','swim','basquete','volei','ginastic'].some(p => t.includes(p)))
    return '<span class="area-badge" style="background:rgba(0,255,65,.15);color:var(--green);border:1px solid var(--green)">ESP</span>';
  if (['cultura','rouanet','arte','music','teatro','cinema','audiovisual','patrimoni'].some(p => t.includes(p)))
    return '<span class="area-badge" style="background:rgba(181,123,238,.15);color:#b57bee;border:1px solid #b57bee">CUL</span>';
  if (['educacao','educação','escola','jovem','adolescente','infancia','juventude'].some(p => t.includes(p)))
    return '<span class="area-badge" style="background:rgba(94,184,255,.15);color:#5eb8ff;border:1px solid #5eb8ff">EDU</span>';
  if (['social','osc','assistencia','vulneravel','diversidade','inclusao','comunidade'].some(p => t.includes(p)))
    return '<span class="area-badge" style="background:rgba(255,165,0,.15);color:var(--amber);border:1px solid var(--amber)">SOC</span>';
  return '<span class="area-badge" style="background:rgba(0,255,65,.05);color:var(--green3);border:1px solid var(--border)">OUT</span>';
}

// ── RENDER EDITAIS ────────────────────────────────────────────────────────
function renderEditais() {
  const busca  = (document.getElementById('f-edit-busca').value||'').toLowerCase();
  const area   = document.getElementById('f-edit-area').value;
  const status = document.getElementById('f-edit-status').value;

  if (!EDITAIS || EDITAIS.length === 0) {
    document.getElementById('editais-empty').style.display = 'flex';
    document.getElementById('editais-table-wrap').style.display = 'none';
    document.getElementById('editais-count').textContent = '0 editais';
    return;
  }
  document.getElementById('editais-empty').style.display = 'none';
  document.getElementById('editais-table-wrap').style.display = 'flex';

  let filtered = EDITAIS.filter(e => {
    if (busca && !String(e.titulo||'').toLowerCase().includes(busca) &&
        !String(e.financiador||'').toLowerCase().includes(busca)) return false;
    if (area && !String(e.areas_tematicas||'').toLowerCase().includes(area.toLowerCase())) return false;
    if (status && String(e.status||'').toLowerCase() !== status) return false;
    return true;
  });
  filtered = _filtrarPorArea(filtered);
  filtered.sort((a, b) => {
    const da = parseInt(a.dias_restantes), db = parseInt(b.dias_restantes);
    const ia = isNaN(da) || da < 0 ? 99999 : da;
    const ib = isNaN(db) || db < 0 ? 99999 : db;
    return ia - ib;
  });
  document.getElementById('editais-count').textContent = filtered.length + ' editais';
  document.getElementById('editais-body').innerHTML = filtered.map(e => {
    const st = String(e.status||'').toLowerCase();
    const stBdg = st === 'ativo'
      ? '<span class="badge st-ativo">ATIVO</span>'
      : '<span class="badge st-encerrado">ENC.</span>';
    const area1 = String(e.areas_tematicas||'').split('|')[0].trim() || '—';
    const textoArea = (e.titulo||'') + (e.areas_tematicas||'') + (e.financiador||'');
    const areaBdg = _areaBadge(textoArea);
    const link = String(e.url_original||'').length > 5
      ? `<a href="${esc(e.url_original)}" target="_blank" style="color:var(--amber);text-decoration:none;font-weight:bold;">[→]</a>`
      : '<span style="color:var(--green-dim)">—</span>';
    return `<tr>
      <td>${stBdg}</td>
      <td>${fmtPrazo(e.dias_restantes)}</td>
      <td style="max-width:260px;overflow:hidden;text-overflow:ellipsis;font-size:11px">${esc(e.titulo)}</td>
      <td style="color:var(--green3);font-size:11px">${esc(e.financiador)}</td>
      <td style="font-size:10px;max-width:140px;overflow:hidden;text-overflow:ellipsis">${areaBdg} ${esc(area1)}</td>
      <td style="color:var(--green-dim);font-size:10px">${esc(e.fonte)}</td>
      <td>${link}</td>
    </tr>`;
  }).join('');
}

// ── MODAL: ATUALIZAR ──────────────────────────────────────────────────────
function openModal() {
  document.getElementById('modal-overlay').classList.add('open');
}
function closeModal() {
  document.getElementById('modal-overlay').classList.remove('open');
  const btn = document.getElementById('btn-copiar');
  if (btn) { btn.textContent = '⎘ Copiar comandos'; btn.disabled = false; }
}
function closeModalOutside(e) {
  if (e.target === document.getElementById('modal-overlay')) closeModal();
}
function copiarComandos() {
  const cmds = 'python scripts/coletar_editais.py\npython scripts/matching_editais.py\npython scripts/gerar_dashboard.py';
  navigator.clipboard.writeText(cmds).then(() => {
    const btn = document.getElementById('btn-copiar');
    btn.textContent = '✓ Copiado!';
    btn.disabled = true;
    setTimeout(() => { btn.textContent = '⎘ Copiar comandos'; btn.disabled = false; }, 2500);
  }).catch(() => {
    alert('Comandos:\n\n' + cmds);
  });
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ── AVISO SEM DADOS ────────────────────────────────────────────────────────
function initDemoBanner() {
  // Mostra banner apenas quando nao ha nenhuma oportunidade carregada
  const b = document.getElementById('demo-banner');
  if (b) b.style.display = (EDITAIS.length === 0) ? 'block' : 'none';
}

// ── TICKER ────────────────────────────────────────────────────────────────
function renderTicker() {
  const items = [...PROJETOS].sort((a,b) => parseFloat(b.saldo_disponivel) - parseFloat(a.saldo_disponivel)).slice(0,30);
  document.getElementById('ticker-inner').innerHTML = items.map(p =>
    `<span class="tick-item">
      <span class="tick-name">${esc(p.nome_projeto.substring(0,32))}</span> &nbsp;
      <span class="tick-val">${fmtBRL(p.saldo_disponivel)}</span> &nbsp;
      <span style="color:var(--green-dim)">${p.uf} · ${esc(p.modalidade_esportiva)}</span>
    </span>`).join('');
}

// ── COPIAR COMANDO ────────────────────────────────────────────────────────
function copyCmd(texto, btnId) {
  var cmd = texto.replace(/&amp;/g,'&').replace(/&gt;/g,'>').replace(/&lt;/g,'<');
  var btn = document.getElementById(btnId);
  var original = btn ? btn.textContent : '';
  function feedback() {
    if (!btn) return;
    btn.textContent = '[ ✓ COPIADO ]';
    btn.classList.add('copied');
    setTimeout(function(){ btn.textContent = original; btn.classList.remove('copied'); }, 2000);
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(cmd).then(feedback).catch(function(){
      _copyFallback(cmd); feedback();
    });
  } else {
    _copyFallback(cmd); feedback();
  }
}
function _copyFallback(texto) {
  var ta = document.createElement('textarea');
  ta.value = texto;
  ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0;';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); } catch(e){}
  document.body.removeChild(ta);
}

// ── VIEW ATUALIZAR ────────────────────────────────────────────────────────
function initAtualizarView() {
  // Painel 1 — Projetos
  document.getElementById('upd-proj-data').textContent    = META_PROJETOS.ultima_importacao || '—';
  document.getElementById('upd-proj-total').textContent   = (META_PROJETOS.total_projetos||0).toLocaleString('pt-BR') + ' projetos ativos';
  document.getElementById('upd-proj-cobertura').textContent =
    (META_PROJETOS.ano_min||'?') + ' a ' + (META_PROJETOS.ano_max||'?') +
    ' · ' + (META_PROJETOS.total_ufs||0) + ' UFs · ' +
    (META_PROJETOS.total_modalidades||0) + ' modalidades';
  var vt = META_PROJETOS.valor_total || 0;
  document.getElementById('upd-proj-valor').textContent   = 'R$ ' + (vt/1e9).toFixed(2).replace('.',',') + ' bi';

  // Painel 2 — Editais
  document.getElementById('upd-edit-data').textContent    = META_EDITAIS.ultima_coleta || '—';
  document.getElementById('upd-edit-ativos').textContent  =
    (META_EDITAIS.total_ativos||0) + ' ativos (' + (META_EDITAIS.total_encerrados||0) + ' encerrados)';

  var badgeReal = document.getElementById('upd-edit-real');
  if (badgeReal) {
    badgeReal.innerHTML = META_EDITAIS.tem_dados_reais
      ? '<span class="fonte-status-ok">● DADOS REAIS</span>'
      : '<span class="demo-badge">⚠ SEM DADOS REAIS</span>';
  }
  var sp = document.getElementById('upd-fonte-portal');
  if (sp) sp.innerHTML = META_EDITAIS.tem_portal_key
    ? '<span class="fonte-status-ok">● ativo</span>'
    : '<span class="fonte-status-off">○ chave nao configurada</span>';
  var sc = document.getElementById('upd-fonte-claude');
  if (sc) sc.innerHTML = META_EDITAIS.tem_anthropic_key
    ? '<span class="fonte-status-ok">● ativo</span>'
    : '<span class="fonte-status-off">○ chave nao configurada</span>';

  // Painel 3 — Sistema
  // Painel Empresas
  document.getElementById('upd-emp-data').textContent      = META_EMPRESAS.ultima_importacao || '—';
  document.getElementById('upd-emp-total').textContent     = (META_EMPRESAS.total_empresas||0).toLocaleString('pt-BR') + ' grupos empresariais';
  document.getElementById('upd-emp-setores').textContent   = (META_EMPRESAS.n_setores||0) + ' setores';
  var pt = META_EMPRESAS.potencial_total || 0;
  document.getElementById('upd-emp-potencial').textContent = 'R$ ' + (pt/1e9).toFixed(1) + 'B/ano (estimado)';
  document.getElementById('upd-emp-grandes').textContent   = (META_EMPRESAS.n_grandes||0).toLocaleString('pt-BR') + ' grupos';
  document.getElementById('upd-emp-medias').textContent    = (META_EMPRESAS.n_medias||0).toLocaleString('pt-BR') + ' grupos';
  document.getElementById('upd-emp-pequenas').textContent  = (META_EMPRESAS.n_pequenas||0).toLocaleString('pt-BR') + ' grupos';

  document.getElementById('upd-sys-gerado').textContent   = META_SISTEMA.dashboard_gerado || '—';
  document.getElementById('upd-sys-versao').textContent   = META_SISTEMA.versao || '—';
  document.getElementById('upd-sys-projetos').textContent = (META_SISTEMA.n_projetos||0).toLocaleString('pt-BR');
  document.getElementById('upd-sys-empresas').textContent = (META_SISTEMA.n_empresas||0).toLocaleString('pt-BR');
  document.getElementById('upd-sys-editais').textContent  = (META_SISTEMA.n_editais||0).toLocaleString('pt-BR');
  document.getElementById('upd-sys-memp').textContent     = (META_SISTEMA.n_match_proj_emp||0).toLocaleString('pt-BR');
  document.getElementById('upd-sys-medit').textContent    = (META_SISTEMA.n_match_editais||0).toLocaleString('pt-BR');
}

// ── BUSCA UNIVERSAL ───────────────────────────────────────────────────────
function buscaUniversal(termo) {
  const t = (termo||'').toLowerCase().trim();
  const searchInput = document.getElementById('sidebar-search');
  const mainInput = document.getElementById('busca-input-main');
  if (searchInput && searchInput.value !== termo) searchInput.value = termo;
  if (mainInput && mainInput.value !== termo) mainInput.value = termo;
  if (!t) { limparBusca(); return; }
  showView('busca');
  document.getElementById('nav-busca').style.display = 'block';

  const projR = PROJETOS.filter(p =>
    (p.modalidade_esportiva||'').toLowerCase().includes(t) ||
    (p.nome_projeto||'').toLowerCase().includes(t) ||
    (p.proponente||'').toLowerCase().includes(t) ||
    (p.uf||'').toLowerCase().includes(t)
  ).sort((a,b) => parseFloat(b.score_prioridade||0)-parseFloat(a.score_prioridade||0)).slice(0,30);

  const empR = EMPRESAS.filter(e =>
    (e.setor||'').toLowerCase().includes(t) ||
    (e.nome_empresa||'').toLowerCase().includes(t) ||
    (e.descricao||'').toLowerCase().includes(t) ||
    (e.regiao_sede||'').toLowerCase().includes(t)
  ).sort((a,b) => parseFloat(b.score_empresa||0)-parseFloat(a.score_empresa||0)).slice(0,30);

  const editR = EDITAIS.filter(e =>
    String(e.areas_tematicas||'').toLowerCase().includes(t) ||
    String(e.titulo||'').toLowerCase().includes(t) ||
    String(e.financiador||'').toLowerCase().includes(t) ||
    String(e.descricao||'').toLowerCase().includes(t)
  ).sort((a,b) => {
    const da=parseInt(a.dias_restantes), db=parseInt(b.dias_restantes);
    return (isNaN(da)||da<0?99999:da)-(isNaN(db)||db<0?99999:db);
  }).slice(0,30);

  const total = projR.length + empR.length + editR.length;
  document.getElementById('busca-total').textContent = total + ' resultados para "' + termo + '"';
  document.getElementById('busca-n-proj').textContent = projR.length + ' projetos';
  document.getElementById('busca-n-emp').textContent = empR.length + ' empresas';
  document.getElementById('busca-n-edit').textContent = editR.length + ' editais';

  document.getElementById('busca-proj-body').innerHTML = projR.map(p =>
    '<tr>' +
    '<td style="padding:3px 10px;border-bottom:1px solid #001100;">' + esc(p.nome_projeto) + '</td>' +
    '<td style="padding:3px 10px;border-bottom:1px solid #001100;color:var(--green3)">' + esc(p.modalidade_esportiva) + '</td>' +
    '<td style="padding:3px 10px;border-bottom:1px solid #001100;"><span class="badge">' + esc(p.uf) + '</span></td>' +
    '<td style="padding:3px 10px;border-bottom:1px solid #001100;color:var(--amber)">' + fmtBRL(p.saldo_disponivel) + '</td>' +
    '<td style="padding:3px 10px;border-bottom:1px solid #001100;">' + fmtSc(p.score_prioridade) + '</td>' +
    '</tr>'
  ).join('') || '<tr><td colspan="5" style="padding:8px 10px;color:var(--green-dim)">Nenhum projeto encontrado</td></tr>';

  document.getElementById('busca-emp-body').innerHTML = empR.map(function(e) {
    var intl = e.regiao_sede === 'Internacional' ? ' 🌐' : '';
    return '<tr>' +
    '<td style="padding:3px 10px;border-bottom:1px solid #001100;font-weight:bold">' + esc(e.nome_empresa) + intl + '</td>' +
    '<td style="padding:3px 10px;border-bottom:1px solid #001100;color:var(--green3);font-size:10px">' + esc(e.setor) + '</td>' +
    '<td style="padding:3px 10px;border-bottom:1px solid #001100;color:var(--green3)">' + esc(e.regiao_sede) + '</td>' +
    '<td style="padding:3px 10px;border-bottom:1px solid #001100;color:var(--amber)">' + fmtBRL(e.potencial_investimento) + '</td>' +
    '<td style="padding:3px 10px;border-bottom:1px solid #001100;">' + fmtSc(e.score_empresa) + '</td>' +
    '</tr>';
  }).join('') || '<tr><td colspan="5" style="padding:8px 10px;color:var(--green-dim)">Nenhuma empresa encontrada</td></tr>';

  document.getElementById('busca-edit-body').innerHTML = editR.map(function(e) {
    var st = String(e.status||'').toLowerCase();
    var stBdg = st==='ativo' ? '<span class="badge st-ativo">ATIVO</span>' : '<span class="badge st-encerrado">ENC.</span>';
    var area1 = String(e.areas_tematicas||'').split('|')[0].trim()||'—';
    var link = String(e.url_original||'').length>5
      ? '<a href="' + esc(e.url_original) + '" target="_blank" style="color:var(--amber);text-decoration:none;font-weight:bold;">[&#x2192;]</a>'
      : '—';
    return '<tr>' +
    '<td style="padding:3px 10px;border-bottom:1px solid #001100;">' + stBdg + '</td>' +
    '<td style="padding:3px 10px;border-bottom:1px solid #001100;">' + fmtPrazo(e.dias_restantes) + '</td>' +
    '<td style="padding:3px 10px;border-bottom:1px solid #001100;font-size:11px;max-width:220px;overflow:hidden;text-overflow:ellipsis;">' + esc(e.titulo) + '</td>' +
    '<td style="padding:3px 10px;border-bottom:1px solid #001100;color:var(--green3);font-size:11px">' + esc(e.financiador) + '</td>' +
    '<td style="padding:3px 10px;border-bottom:1px solid #001100;color:var(--green3);font-size:10px">' + esc(area1) + '</td>' +
    '<td style="padding:3px 10px;border-bottom:1px solid #001100;">' + link + '</td>' +
    '</tr>';
  }).join('') || '<tr><td colspan="6" style="padding:8px 10px;color:var(--green-dim)">Nenhum edital encontrado</td></tr>';
}

function limparBusca() {
  var s = document.getElementById('sidebar-search'); if(s) s.value='';
  var m = document.getElementById('busca-input-main'); if(m) m.value='';
  var nb = document.getElementById('nav-busca'); if(nb) nb.style.display='none';
  showView('projetos');
}

// ── CONFIG VIEW ────────────────────────────────────────────────────────────
function initConfigView() {
  ['PORTAL_TRANSPARENCIA_API_KEY','ANTHROPIC_API_KEY'].forEach(function(k) {
    var val = localStorage.getItem('hub_'+k)||'';
    var input = document.getElementById('input_'+k);
    if (!input) return;
    input.dataset.realValue = val;
    input.dataset.masked = val ? 'true' : 'false';
    input.value = val ? ('•'.repeat(Math.max(0,val.length-4))+val.slice(-4)) : '';
  });
  updateStatusFontes();
}

function desmascarar(input) {
  if (input.dataset.masked === 'true') {
    input.value = input.dataset.realValue || '';
    input.dataset.masked = 'false';
  }
}

function mascarar(input) {
  var val = input.value.trim();
  if (val && !val.startsWith('•') && val !== input.dataset.realValue) {
    input.dataset.realValue = val;
  }
  var stored = input.dataset.realValue || '';
  if (stored) {
    input.value = '•'.repeat(Math.max(0,stored.length-4)) + stored.slice(-4);
    input.dataset.masked = 'true';
  }
}

function toggleReveal(id) {
  var input = document.getElementById(id);
  if (!input) return;
  if (input.dataset.masked === 'true' || input.type === 'password') {
    desmascarar(input);
  } else {
    mascarar(input);
  }
}

function saveConfig() {
  ['PORTAL_TRANSPARENCIA_API_KEY','ANTHROPIC_API_KEY'].forEach(function(k) {
    var input = document.getElementById('input_'+k);
    if (!input) return;
    var val = (input.dataset.realValue||'').trim();
    if (!val || val.startsWith('•')) val = input.value.trim();
    if (val && !val.startsWith('•')) {
      localStorage.setItem('hub_'+k, val);
      input.dataset.realValue = val;
    }
  });
  updateStatusFontes();
  showToast('✓ Configurações salvas com sucesso');
}

function clearConfig() {
  if (!confirm('Limpar todas as chaves salvas?')) return;
  localStorage.removeItem('hub_PORTAL_TRANSPARENCIA_API_KEY');
  localStorage.removeItem('hub_ANTHROPIC_API_KEY');
  initConfigView();
  showToast('Configurações limpas.');
}

function updateStatusFontes() {
  var temPortal = !!localStorage.getItem('hub_PORTAL_TRANSPARENCIA_API_KEY');
  var temClaude = !!localStorage.getItem('hub_ANTHROPIC_API_KEY');
  var sp = document.getElementById('status_portal');
  var sm = document.getElementById('status_mrosc');
  var sc = document.getElementById('status_claude');
  if(sp) { sp.textContent = temPortal ? '● ATIVO' : '○ CHAVE NÃO CONFIGURADA'; sp.style.color = temPortal ? 'var(--green)' : 'var(--amber)'; }
  if(sm) { sm.textContent = temPortal ? '● ATIVO' : '○ CHAVE NÃO CONFIGURADA'; sm.style.color = temPortal ? 'var(--green)' : 'var(--amber)'; }
  if(sc) { sc.textContent = temClaude ? '● ATIVO' : '○ CHAVE NÃO CONFIGURADA'; sc.style.color = temClaude ? 'var(--green)' : 'var(--amber)'; }
}

function gerarEnv() {
  var portal = localStorage.getItem('hub_PORTAL_TRANSPARENCIA_API_KEY')||'';
  var claude = localStorage.getItem('hub_ANTHROPIC_API_KEY')||'';
  var conteudo = '# Hub de Captação — Chaves de API\nPORTAL_TRANSPARENCIA_API_KEY='+portal+'\nANTHROPIC_API_KEY='+claude+'\n';
  var blob = new Blob([conteudo], {type:'text/plain'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = '.env';
  a.click();
}

function showToast(msg) {
  var t = document.createElement('div');
  t.style.cssText = 'position:fixed;bottom:24px;right:24px;background:var(--bg3);border:1px solid var(--green);color:var(--green);padding:10px 20px;font-family:monospace;font-size:13px;z-index:9999;';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(function(){t.remove();}, 3000);
}

// ── BOOT ──────────────────────────────────────────────────────────────────
init();
</script>
</body>
</html>"""


if __name__ == '__main__':
    gerar_dashboard()
