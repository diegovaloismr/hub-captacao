# -*- coding: utf-8 -*-
"""
Hub de Captação — Servidor Web
Uso local:  uvicorn main:app --reload
Produção:   gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker
"""
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import math, os
from pathlib import Path
from database import get_conn, init_db, reload_db

app = FastAPI(title="Hub de Captação", version="2.0")

app.add_middleware(CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.mount("/static", StaticFiles(directory="app"), name="static")

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def root():
    return FileResponse("app/index.html")

# ── STATS ──────────────────────────────────────────────────────────────────

@app.get("/api/stats")
def stats():
    conn = get_conn()
    c = conn.cursor()

    def count(tabela, where=""):
        try:
            return c.execute(f"SELECT COUNT(*) FROM {tabela} {where}").fetchone()[0]
        except Exception:
            return 0

    def soma(tabela, campo, where=""):
        try:
            return c.execute(f"SELECT SUM({campo}) FROM {tabela} {where}").fetchone()[0] or 0
        except Exception:
            return 0

    try:
        return {
            'esporte': {
                'n_projetos':  count('projetos'),
                'valor_total': soma('projetos', 'saldo_disponivel'),
                'n_empresas':  count('empresas'),
                'n_matches':   count('match_empresas'),
            },
            'cultura': {
                'n_projetos':  count('projetos_rouanet'),
                'valor_total': soma('projetos_rouanet', 'saldo_disponivel'),
                'n_empresas':  count('empresas'),
                'n_matches':   count('match_rouanet'),
                'n_editais':   count('match_editais_rouanet'),
            },
            'educacao': {
                'n_projetos':  0,
                'valor_total': 0,
                'n_empresas':  0,
                'n_matches':   0,
            },
            'social': {
                'n_projetos':  0,
                'valor_total': 0,
                'n_empresas':  0,
                'n_matches':   0,
            },
            'editais': {
                'n_ativos':   count('editais', "WHERE status='ativo'"),
                'n_esporte':  count('editais', "WHERE status='ativo' AND (LOWER(areas_tematicas) LIKE '%esporte%' OR LOWER(titulo) LIKE '%esporte%')"),
                'n_cultura':  count('editais', "WHERE status='ativo' AND (LOWER(areas_tematicas) LIKE '%cultura%' OR LOWER(titulo) LIKE '%cultura%')"),
                'n_educacao': count('editais', "WHERE status='ativo' AND (LOWER(areas_tematicas) LIKE '%educacao%' OR LOWER(titulo) LIKE '%educação%')"),
                'n_social':   count('editais', "WHERE status='ativo' AND (LOWER(areas_tematicas) LIKE '%social%' OR LOWER(titulo) LIKE '%social%')"),
            },
        }
    finally:
        conn.close()

# ── PROJETOS ───────────────────────────────────────────────────────────────

@app.get("/api/projetos")
def listar_projetos(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=10, le=200),
    busca: str = Query(""),
    uf: str = Query(""),
    regiao: str = Query(""),
    modalidade: str = Query(""),
    ano: str = Query(""),
    lei: str = Query("LIE"),
    order_by: str = Query("score_prioridade"),
):
    tabela = 'projetos_rouanet' if lei == 'Rouanet' else 'projetos'
    campo_mod = 'segmento_cultural' if lei == 'Rouanet' else 'modalidade_esportiva'

    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{tabela}'")
        if not c.fetchone():
            return {"total": 0, "paginas": 1, "pagina": 1, "projetos": [], "filtros": {}}

        where, params = [], []
        if busca:
            where.append("(nome_projeto LIKE ? OR proponente LIKE ?)")
            params += [f"%{busca}%"] * 2
        if uf:
            where.append("uf = ?"); params.append(uf)
        if regiao:
            where.append("regiao = ?"); params.append(regiao)
        if modalidade:
            where.append(f"{campo_mod} LIKE ?"); params.append(f"%{modalidade}%")
        if ano:
            where.append("ano_aprovacao = ?"); params.append(ano)

        sql_where = ("WHERE " + " AND ".join(where)) if where else ""
        cols_validas = {"score_prioridade", "saldo_disponivel", "valor_aprovado",
                        "data_fim_captacao", "nome_projeto", "proponente"}
        ob = order_by if order_by in cols_validas else "score_prioridade"

        total = c.execute(f"SELECT COUNT(*) FROM {tabela} {sql_where}", params).fetchone()[0]
        offset = (pagina - 1) * por_pagina
        rows = c.execute(
            f"SELECT * FROM {tabela} {sql_where} ORDER BY {ob} DESC LIMIT ? OFFSET ?",
            params + [por_pagina, offset]
        ).fetchall()

        ufs  = [r[0] for r in c.execute(f"SELECT DISTINCT uf FROM {tabela} ORDER BY uf").fetchall()]
        regs = [r[0] for r in c.execute(f"SELECT DISTINCT regiao FROM {tabela} ORDER BY regiao").fetchall()]
        anos = [r[0] for r in c.execute(f"SELECT DISTINCT ano_aprovacao FROM {tabela} ORDER BY ano_aprovacao DESC").fetchall()]

        return {
            "total": total,
            "paginas": math.ceil(total / por_pagina) if total else 1,
            "pagina": pagina,
            "projetos": [dict(r) for r in rows],
            "filtros": {"ufs": ufs, "regioes": regs, "anos": anos},
        }
    finally:
        conn.close()

@app.get("/api/projeto/{nome_projeto:path}")
def detalhe_projeto(nome_projeto: str, lei: str = Query("LIE")):
    tabela_proj    = 'projetos_rouanet' if lei == 'Rouanet' else 'projetos'
    tabela_match   = 'match_rouanet'    if lei == 'Rouanet' else 'match_empresas'
    tabela_editais = 'match_editais_rouanet' if lei == 'Rouanet' else 'match_editais'

    conn = get_conn()
    c = conn.cursor()
    try:
        proj = c.execute(f"SELECT * FROM {tabela_proj} WHERE nome_projeto = ?",
                         [nome_projeto]).fetchone()
        if not proj:
            return JSONResponse({"erro": "Projeto não encontrado"}, status_code=404)

        empresas = c.execute(
            f"""SELECT me.*, e.setor, e.uf_sede, e.descricao, e.potencial_investimento,
                       e.faturamento_anual, e.lucro_liquido
               FROM {tabela_match} me
               LEFT JOIN empresas e ON e.nome_empresa = me.nome_empresa
               WHERE me.nome_projeto = ?
               ORDER BY me.score_match DESC LIMIT 20""",
            [nome_projeto]
        ).fetchall()

        c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{tabela_editais}'")
        editais = []
        if c.fetchone():
            editais = c.execute(
                f"""SELECT * FROM {tabela_editais}
                   WHERE nome_projeto = ?
                   ORDER BY score_match DESC LIMIT 15""",
                [nome_projeto]
            ).fetchall()

        return {
            "projeto":  dict(proj),
            "empresas": [dict(r) for r in empresas],
            "editais":  [dict(r) for r in editais],
        }
    finally:
        conn.close()

# ── EMPRESAS ───────────────────────────────────────────────────────────────

@app.get("/api/empresas")
def listar_empresas(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=10, le=200),
    busca: str = Query(""),
    setor: str = Query(""),
    regiao: str = Query(""),
):
    conn = get_conn()
    c = conn.cursor()
    try:
        where, params = [], []
        if busca:
            where.append("(nome_empresa LIKE ? OR descricao LIKE ?)")
            params += [f"%{busca}%"] * 2
        if setor:
            where.append("setor = ?"); params.append(setor)
        if regiao:
            where.append("regiao_sede = ?"); params.append(regiao)

        sql_where = ("WHERE " + " AND ".join(where)) if where else ""
        total  = c.execute(f"SELECT COUNT(*) FROM empresas {sql_where}", params).fetchone()[0]
        offset = (pagina - 1) * por_pagina
        rows   = c.execute(
            f"SELECT * FROM empresas {sql_where} ORDER BY score_empresa DESC LIMIT ? OFFSET ?",
            params + [por_pagina, offset]
        ).fetchall()
        setors = [r[0] for r in c.execute("SELECT DISTINCT setor FROM empresas ORDER BY setor").fetchall()]
        regs   = [r[0] for r in c.execute("SELECT DISTINCT regiao_sede FROM empresas ORDER BY regiao_sede").fetchall()]
        return {
            "total": total,
            "paginas": math.ceil(total / por_pagina) if total else 1,
            "pagina": pagina,
            "empresas": [dict(r) for r in rows],
            "filtros": {"setores": setors, "regioes": regs},
        }
    finally:
        conn.close()

# ── EDITAIS ────────────────────────────────────────────────────────────────

@app.get("/api/editais")
def listar_editais(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=10, le=200),
    busca: str = Query(""),
    area: str = Query(""),
    status: str = Query("ativo"),
):
    conn = get_conn()
    c = conn.cursor()
    try:
        where, params = [], []
        if status:
            where.append("status = ?"); params.append(status)
        if busca:
            where.append("(titulo LIKE ? OR financiador LIKE ?)"); params += [f"%{busca}%"] * 2
        if area and area != 'todos':
            mapa = {
                'esporte':  ['esporte','olimp','paralim','sport','atletism','futebol',
                             'basquete','volei','natacao','ginastic','modalidade','lie'],
                'cultura':  ['cultura','rouanet','arte','music','teatro','cinema',
                             'audiovisual','danca','literatura','patrimoni','funarte',
                             'minc','salic','paulo gustavo','circo','artesanat'],
                'educacao': ['educacao','educação','escola','juventude','crianca',
                             'adolescente','fnde','aprendiz','formacao','capacitac'],
                'social':   ['social','osc','assistencia','diversidade','inclusao',
                             'comunidade','mrosc','vulneravel','habitacao','idoso'],
            }
            palavras = mapa.get(area, [])
            if palavras:
                cond = " OR ".join(["(LOWER(titulo) LIKE ? OR LOWER(areas_tematicas) LIKE ?)"] * len(palavras))
                where.append(f"({cond})")
                for p in palavras:
                    params += [f"%{p}%", f"%{p}%"]

        sql_where = ("WHERE " + " AND ".join(where)) if where else ""
        total  = c.execute(f"SELECT COUNT(*) FROM editais {sql_where}", params).fetchone()[0]
        offset = (pagina - 1) * por_pagina
        rows   = c.execute(
            f"""SELECT * FROM editais {sql_where}
                ORDER BY
                  CASE WHEN dias_restantes >= 0 THEN dias_restantes ELSE 9999 END ASC
                LIMIT ? OFFSET ?""",
            params + [por_pagina, offset]
        ).fetchall()
        return {
            "total": total,
            "paginas": math.ceil(total / por_pagina) if total else 1,
            "pagina": pagina,
            "editais": [dict(r) for r in rows],
        }
    finally:
        conn.close()

# ── EMENDAS PARLAMENTARES ──────────────────────────────────────────────────

@app.get("/api/emendas-projeto")
def emendas_projeto(nome_projeto: str = Query(...), lei: str = Query("LIE")):
    """Retorna emendas parlamentares compatíveis com o projeto."""
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='match_emendas'")
        if not c.fetchone():
            return {"emendas": [], "aviso": "Execute importar_emendas.py e matching_emendas.py"}
        rows = c.execute(
            """SELECT * FROM match_emendas
               WHERE nome_projeto = ? AND lei = ?
               ORDER BY score_match DESC LIMIT 15""",
            [nome_projeto, lei]
        ).fetchall()
        return {"emendas": [dict(r) for r in rows]}
    finally:
        conn.close()


# ── INCENTIVOS FISCAIS ─────────────────────────────────────────────────────

import json as json_lib

@app.get("/api/incentivos/{uf}")
def incentivos_por_uf(uf: str, tipo: str = Query("")):
    """Retorna leis de incentivo disponíveis para uma UF."""
    json_path = Path(__file__).parent / 'data' / 'incentivos_fiscais.json'
    if not json_path.exists():
        return {"incentivos": [], "uf": uf}
    with open(json_path, encoding='utf-8') as f:
        todos = json_lib.load(f)
    uf = uf.strip().upper()
    resultado = [i for i in todos if i['uf'] == uf or i['uf'] == 'TODOS']
    if tipo:
        resultado = [i for i in resultado if i['tipo'].lower() == tipo.lower()]
    resultado.sort(key=lambda x: (0 if x['uf'] == uf else 1, x['nome']))
    return {"incentivos": resultado, "uf": uf}


# ── NOTÍCIAS (ticker) ──────────────────────────────────────────────────────

@app.get("/api/noticias")
def ultimas_noticias():
    """Retorna últimas notícias do Observatório 3º Setor para o ticker."""
    try:
        import feedparser
    except (ImportError, ModuleNotFoundError):
        import sys, os as _os
        sys.path.insert(0, str(Path(__file__).parent / 'scripts'))
        import _rss_parser as feedparser
    feeds = [
        'https://observatorio3setor.org.br/category/noticias/editais/feed/',
        'https://blog.prosas.com.br/categoria/editais/feed/',
    ]
    noticias = []
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                titulo = entry.get('title', '').strip()
                link   = entry.get('link', '')
                if titulo:
                    noticias.append({'titulo': titulo, 'link': link})
        except Exception:
            pass
    if not noticias:
        noticias = [
            {'titulo': 'Hub de Captação — Terminal de Inteligência v2.0', 'link': ''},
            {'titulo': 'Projetos LIE + Rouanet disponíveis para matching', 'link': ''},
        ]
    return noticias[:15]


# ── ADMIN ──────────────────────────────────────────────────────────────────

@app.post("/api/reload")
def recarregar_banco():
    try:
        reload_db()
        return {"ok": True, "mensagem": "Banco recarregado com sucesso."}
    except Exception as e:
        return JSONResponse({"ok": False, "erro": str(e)}, status_code=500)
