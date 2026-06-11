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

app = FastAPI(title="Hub de Captação", version="1.0")

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
    r = {}
    try:
        r['n_projetos']  = c.execute("SELECT COUNT(*) FROM projetos").fetchone()[0]
        r['n_empresas']  = c.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
        r['n_editais']   = c.execute("SELECT COUNT(*) FROM editais WHERE status='ativo'").fetchone()[0]
        r['n_matches']   = c.execute("SELECT COUNT(*) FROM match_empresas").fetchone()[0]
        r['valor_total'] = c.execute("SELECT SUM(saldo_disponivel) FROM projetos").fetchone()[0] or 0
        r['pot_total']   = c.execute("SELECT SUM(potencial_investimento) FROM empresas").fetchone()[0] or 0
    except Exception:
        r = {'n_projetos': 0, 'n_empresas': 0, 'n_editais': 0, 'n_matches': 0, 'valor_total': 0, 'pot_total': 0}
    finally:
        conn.close()
    return r

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
    order_by: str = Query("score_prioridade"),
):
    conn = get_conn()
    c = conn.cursor()
    try:
        where, params = [], []
        if busca:
            where.append("(nome_projeto LIKE ? OR proponente LIKE ? OR modalidade_esportiva LIKE ?)")
            params += [f"%{busca}%"] * 3
        if uf:
            where.append("uf = ?"); params.append(uf)
        if regiao:
            where.append("regiao = ?"); params.append(regiao)
        if modalidade:
            where.append("modalidade_esportiva LIKE ?"); params.append(f"%{modalidade}%")
        if ano:
            where.append("ano_aprovacao = ?"); params.append(ano)

        sql_where = ("WHERE " + " AND ".join(where)) if where else ""
        cols_validas = {"score_prioridade","saldo_disponivel","valor_aprovado",
                        "data_fim_captacao","nome_projeto","proponente"}
        ob = order_by if order_by in cols_validas else "score_prioridade"

        total = c.execute(f"SELECT COUNT(*) FROM projetos {sql_where}", params).fetchone()[0]
        offset = (pagina - 1) * por_pagina
        rows = c.execute(
            f"SELECT * FROM projetos {sql_where} ORDER BY {ob} DESC LIMIT ? OFFSET ?",
            params + [por_pagina, offset]
        ).fetchall()

        ufs  = [r[0] for r in c.execute("SELECT DISTINCT uf FROM projetos ORDER BY uf").fetchall()]
        regs = [r[0] for r in c.execute("SELECT DISTINCT regiao FROM projetos ORDER BY regiao").fetchall()]
        anos = [r[0] for r in c.execute("SELECT DISTINCT ano_aprovacao FROM projetos ORDER BY ano_aprovacao DESC").fetchall()]

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
def detalhe_projeto(nome_projeto: str):
    conn = get_conn()
    c = conn.cursor()
    try:
        proj = c.execute("SELECT * FROM projetos WHERE nome_projeto = ?",
                         [nome_projeto]).fetchone()
        if not proj:
            return JSONResponse({"erro": "Projeto não encontrado"}, status_code=404)

        empresas = c.execute(
            """SELECT me.*, e.setor, e.uf_sede, e.descricao, e.potencial_investimento
               FROM match_empresas me
               LEFT JOIN empresas e ON e.nome_empresa = me.nome_empresa
               WHERE me.nome_projeto = ?
               ORDER BY me.score_match DESC LIMIT 20""",
            [nome_projeto]
        ).fetchall()

        editais = c.execute(
            """SELECT * FROM match_editais
               WHERE nome_projeto = ?
               ORDER BY score_match DESC LIMIT 15""",
            [nome_projeto]
        ).fetchall()

        return {
            "projeto": dict(proj),
            "empresas": [dict(r) for r in empresas],
            "editais": [dict(r) for r in editais],
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
                'esporte':  ['esporte','olimp','paralim','sport','atletism','futebol','basquete','volei','natacao','ginastic'],
                'cultura':  ['cultura','rouanet','arte','music','teatro','cinema','audiovisual'],
                'educacao': ['educacao','educação','escola','juventude','crianca','adolescente'],
                'social':   ['social','osc','assistencia','diversidade','inclusao','comunidade'],
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

# ── ADMIN ──────────────────────────────────────────────────────────────────

@app.post("/api/reload")
def recarregar_banco():
    try:
        reload_db()
        return {"ok": True, "mensagem": "Banco recarregado com sucesso."}
    except Exception as e:
        return JSONResponse({"ok": False, "erro": str(e)}, status_code=500)
