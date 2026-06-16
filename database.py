# -*- coding: utf-8 -*-
import sqlite3, pandas as pd, os, fcntl
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get('DATA_DIR', BASE_DIR / 'data'))
DB_PATH  = Path(os.environ.get('DB_PATH',  DATA_DIR / 'hub.db'))

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    DATA_DIR.mkdir(exist_ok=True)

    lock_path = DATA_DIR / '.db_init.lock'
    lock_file = open(lock_path, 'w')
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX)

        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projetos'")
        if c.fetchone():
            conn.close()
            return

        print('[DB] Inicializando banco de dados...')
        csvs = {
            'projetos':              DATA_DIR / 'projetos_reais_tratados.csv',
            'empresas':              DATA_DIR / 'empresas_potenciais.csv',
            'editais':               DATA_DIR / 'editais.csv',
            'match_empresas':        DATA_DIR / 'match_inteligente.csv',
            'match_editais':         DATA_DIR / 'match_editais.csv',
            'projetos_rouanet':      DATA_DIR / 'projetos_rouanet.csv',
            'match_rouanet':         DATA_DIR / 'match_rouanet.csv',
            'match_editais_rouanet': DATA_DIR / 'match_editais_rouanet.csv',
        }
        for tabela, path in csvs.items():
            if path.exists():
                df = pd.read_csv(path).fillna('')
                try:
                    df.to_sql(tabela, conn, if_exists='fail', index=False)
                    print(f'  [OK] {tabela}: {len(df)} registros')
                except Exception:
                    print(f'  [SKIP] {tabela}: já existe, mantendo dados atuais')
            else:
                print(f'  [AVISO] {path.name} nao encontrado — tabela {tabela} vazia')

        indices = [
            "CREATE INDEX IF NOT EXISTS idx_proj_score    ON projetos(score_prioridade DESC)",
            "CREATE INDEX IF NOT EXISTS idx_proj_uf       ON projetos(uf)",
            "CREATE INDEX IF NOT EXISTS idx_proj_nome     ON projetos(nome_projeto)",
            "CREATE INDEX IF NOT EXISTS idx_emp_score     ON empresas(score_empresa DESC)",
            "CREATE INDEX IF NOT EXISTS idx_me_proj       ON match_empresas(nome_projeto)",
            "CREATE INDEX IF NOT EXISTS idx_med_proj      ON match_editais(nome_projeto)",
            "CREATE INDEX IF NOT EXISTS idx_edit_stat     ON editais(status)",
            "CREATE INDEX IF NOT EXISTS idx_rouanet_score ON projetos_rouanet(score_prioridade DESC)",
            "CREATE INDEX IF NOT EXISTS idx_rouanet_uf    ON projetos_rouanet(uf)",
            "CREATE INDEX IF NOT EXISTS idx_mr_proj       ON match_rouanet(nome_projeto)",
            "CREATE INDEX IF NOT EXISTS idx_mer_proj      ON match_editais_rouanet(nome_projeto)",
        ]
        for idx in indices:
            try:
                c.execute(idx)
            except Exception:
                pass
        conn.commit()
        conn.close()
        print('[DB] Banco inicializado com sucesso.')

    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()

def reload_db():
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()
