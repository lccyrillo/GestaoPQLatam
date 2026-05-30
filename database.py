"""Inicialização e helpers do banco de dados SQLite."""

import sqlite3
import json
import os
import sys

# Quando empacotado pelo PyInstaller (frozen), o .exe fica em sys.executable.
# O banco deve ficar ao lado do .exe, não na pasta temporária de extração.
if getattr(sys, 'frozen', False):
    _BASE = os.path.dirname(sys.executable)
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(_BASE, 'dados.db')


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS cartoes (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                nome    TEXT    NOT NULL,
                tipo    TEXT    NOT NULL,
                ativo   INTEGER NOT NULL DEFAULT 1,
                criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS clube_latam (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                plano       TEXT    NOT NULL,
                data_inicio DATE    NOT NULL,
                data_fim    DATE,
                ativo       INTEGER NOT NULL DEFAULT 1,
                criado_em   DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS atividades (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo            TEXT    NOT NULL,
                descricao       TEXT    NOT NULL,
                data_atividade  DATE    NOT NULL,
                status          TEXT    NOT NULL DEFAULT 'pendente',
                pq_estimado     REAL    NOT NULL DEFAULT 0,
                pq_confirmado   REAL,
                dados_brutos    TEXT,
                cartao_id       INTEGER REFERENCES cartoes(id),
                criado_em       DATETIME DEFAULT CURRENT_TIMESTAMP,
                atualizado_em   DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        ''')


# ── Cartões ──────────────────────────────────────────────────────────────────

def listar_cartoes(apenas_ativos=False):
    with get_conn() as conn:
        q = 'SELECT * FROM cartoes'
        if apenas_ativos:
            q += ' WHERE ativo = 1'
        q += ' ORDER BY nome'
        return [dict(r) for r in conn.execute(q).fetchall()]


def obter_cartao(cartao_id):
    with get_conn() as conn:
        r = conn.execute('SELECT * FROM cartoes WHERE id = ?', (cartao_id,)).fetchone()
        return dict(r) if r else None


def salvar_cartao(nome, tipo, ativo, cartao_id=None):
    with get_conn() as conn:
        if cartao_id:
            conn.execute(
                'UPDATE cartoes SET nome=?, tipo=?, ativo=? WHERE id=?',
                (nome, tipo, ativo, cartao_id)
            )
        else:
            conn.execute(
                'INSERT INTO cartoes (nome, tipo, ativo) VALUES (?,?,?)',
                (nome, tipo, ativo)
            )


def excluir_cartao(cartao_id):
    with get_conn() as conn:
        conn.execute('DELETE FROM cartoes WHERE id = ?', (cartao_id,))


# ── Clube LATAM ───────────────────────────────────────────────────────────────

def obter_clube_ativo():
    with get_conn() as conn:
        r = conn.execute(
            'SELECT * FROM clube_latam WHERE ativo = 1 ORDER BY data_inicio DESC LIMIT 1'
        ).fetchone()
        return dict(r) if r else None


def listar_clube():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            'SELECT * FROM clube_latam ORDER BY data_inicio DESC'
        ).fetchall()]


def salvar_clube(plano, data_inicio, data_fim, ativo, clube_id=None):
    with get_conn() as conn:
        if clube_id:
            conn.execute(
                'UPDATE clube_latam SET plano=?, data_inicio=?, data_fim=?, ativo=? WHERE id=?',
                (plano, data_inicio, data_fim or None, ativo, clube_id)
            )
        else:
            conn.execute(
                'INSERT INTO clube_latam (plano, data_inicio, data_fim, ativo) VALUES (?,?,?,?)',
                (plano, data_inicio, data_fim or None, ativo)
            )


def excluir_clube(clube_id):
    with get_conn() as conn:
        conn.execute('DELETE FROM clube_latam WHERE id = ?', (clube_id,))


# ── Atividades ────────────────────────────────────────────────────────────────

def listar_atividades(ano=None, tipo=None, status=None):
    with get_conn() as conn:
        q = '''
            SELECT a.*, c.nome as cartao_nome, c.tipo as cartao_tipo
            FROM atividades a
            LEFT JOIN cartoes c ON a.cartao_id = c.id
            WHERE 1=1
        '''
        params = []
        if ano:
            q += ' AND strftime("%Y", a.data_atividade) = ?'
            params.append(str(ano))
        if tipo:
            q += ' AND a.tipo = ?'
            params.append(tipo)
        if status:
            q += ' AND a.status = ?'
            params.append(status)
        q += ' ORDER BY a.data_atividade DESC, a.criado_em DESC'
        rows = conn.execute(q, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d['dados'] = json.loads(d['dados_brutos']) if d['dados_brutos'] else {}
            result.append(d)
        return result


def obter_atividade(atividade_id):
    with get_conn() as conn:
        r = conn.execute(
            '''SELECT a.*, c.nome as cartao_nome, c.tipo as cartao_tipo
               FROM atividades a
               LEFT JOIN cartoes c ON a.cartao_id = c.id
               WHERE a.id = ?''',
            (atividade_id,)
        ).fetchone()
        if not r:
            return None
        d = dict(r)
        d['dados'] = json.loads(d['dados_brutos']) if d['dados_brutos'] else {}
        return d


def criar_atividade(tipo, descricao, data_atividade, pq_estimado, dados_brutos, cartao_id=None):
    with get_conn() as conn:
        cur = conn.execute(
            '''INSERT INTO atividades
               (tipo, descricao, data_atividade, pq_estimado, dados_brutos, cartao_id)
               VALUES (?,?,?,?,?,?)''',
            (tipo, descricao, data_atividade, pq_estimado,
             json.dumps(dados_brutos, ensure_ascii=False), cartao_id)
        )
        return cur.lastrowid


def validar_atividade(atividade_id, pq_confirmado):
    with get_conn() as conn:
        conn.execute(
            '''UPDATE atividades
               SET status='confirmado', pq_confirmado=?,
                   atualizado_em=CURRENT_TIMESTAMP
               WHERE id=?''',
            (pq_confirmado, atividade_id)
        )


def excluir_atividade(atividade_id):
    with get_conn() as conn:
        conn.execute('DELETE FROM atividades WHERE id = ?', (atividade_id,))


def pq_cartao_no_ano(cartao_id, ano, excluir_id=None):
    """Soma pq_estimado de atividades de cartão no ano (para controle do limite anual)."""
    with get_conn() as conn:
        q = '''SELECT COALESCE(SUM(pq_estimado), 0)
               FROM atividades
               WHERE tipo='cartao_itau'
                 AND cartao_id=?
                 AND strftime('%Y', data_atividade)=?'''
        params = [cartao_id, str(ano)]
        if excluir_id:
            q += ' AND id != ?'
            params.append(excluir_id)
        return conn.execute(q, params).fetchone()[0]


def totais_extrato(ano=None):
    with get_conn() as conn:
        params = []
        filtro_ano = ''
        if ano:
            filtro_ano = "AND strftime('%Y', data_atividade) = ?"
            params.append(str(ano))

        row = conn.execute(f'''
            SELECT
                COALESCE(SUM(pq_estimado), 0)    AS total_estimado,
                COALESCE(SUM(CASE WHEN status='confirmado' THEN pq_confirmado ELSE 0 END), 0)
                                                 AS total_confirmado,
                COUNT(*)                          AS total_atividades,
                SUM(CASE WHEN status='pendente' THEN 1 ELSE 0 END) AS pendentes
            FROM atividades WHERE 1=1 {filtro_ano}
        ''', params).fetchone()
        return dict(row)
