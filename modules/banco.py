"""
Banco de dados SQLite — histórico de análises, denúncias e notícias vistas.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "dados" / "historico.db"


def conexao():
    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def inicializar():
    with conexao() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS analises (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            data            TEXT NOT NULL,
            municipio_ibge  TEXT NOT NULL,
            municipio_nome  TEXT NOT NULL,
            total           INTEGER DEFAULT 0,
            alto_risco      INTEGER DEFAULT 0,
            medio_risco     INTEGER DEFAULT 0,
            resultado_json  TEXT
        );

        CREATE TABLE IF NOT EXISTS denuncias (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            data        TEXT NOT NULL,
            descricao   TEXT NOT NULL,
            local       TEXT,
            lat         REAL,
            lon         REAL,
            foto_path   TEXT,
            status      TEXT DEFAULT 'nova'
        );

        CREATE TABLE IF NOT EXISTS noticias (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            data    TEXT NOT NULL,
            titulo  TEXT NOT NULL,
            url     TEXT UNIQUE,
            fonte   TEXT,
            resumo  TEXT
        );

        CREATE TABLE IF NOT EXISTS municipios_comparados (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            data        TEXT NOT NULL,
            ibge        TEXT NOT NULL,
            nome        TEXT NOT NULL,
            score_medio REAL,
            alto_risco  INTEGER,
            total       INTEGER,
            resumo_json TEXT
        );
        """)


def salvar_analise(municipio_ibge, municipio_nome, resultados):
    alto  = sum(1 for r in resultados if r["score"] >= 70)
    medio = sum(1 for r in resultados if 40 <= r["score"] < 70)
    with conexao() as con:
        con.execute(
            """INSERT INTO analises
               (data, municipio_ibge, municipio_nome, total, alto_risco, medio_risco, resultado_json)
               VALUES (?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(), municipio_ibge, municipio_nome,
             len(resultados), alto, medio, json.dumps(resultados, default=str, ensure_ascii=False)),
        )


def historico_analises(municipio_ibge, limite=12):
    with conexao() as con:
        rows = con.execute(
            """SELECT data, total, alto_risco, medio_risco
               FROM analises WHERE municipio_ibge=?
               ORDER BY data DESC LIMIT ?""",
            (municipio_ibge, limite),
        ).fetchall()
    return [dict(r) for r in rows]


def salvar_denuncia(descricao, local="", lat=None, lon=None, foto_path=None):
    with conexao() as con:
        cur = con.execute(
            """INSERT INTO denuncias (data, descricao, local, lat, lon, foto_path)
               VALUES (?,?,?,?,?,?)""",
            (datetime.now().isoformat(), descricao, local, lat, lon, foto_path),
        )
        return cur.lastrowid


def listar_denuncias():
    with conexao() as con:
        rows = con.execute(
            "SELECT * FROM denuncias ORDER BY data DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def salvar_noticias(noticias):
    with conexao() as con:
        for n in noticias:
            try:
                con.execute(
                    """INSERT OR IGNORE INTO noticias (data, titulo, url, fonte, resumo)
                       VALUES (?,?,?,?,?)""",
                    (n.get("data", datetime.now().isoformat()),
                     n["titulo"], n["url"], n.get("fonte", ""), n.get("resumo", "")),
                )
            except Exception:
                pass


def listar_noticias(limite=30):
    with conexao() as con:
        rows = con.execute(
            "SELECT * FROM noticias ORDER BY data DESC LIMIT ?", (limite,)
        ).fetchall()
    return [dict(r) for r in rows]


def salvar_comparacao(ibge, nome, resultados):
    alto  = sum(1 for r in resultados if r["score"] >= 70)
    scores = [r["score"] for r in resultados]
    media = sum(scores) / len(scores) if scores else 0
    with conexao() as con:
        con.execute(
            """INSERT INTO municipios_comparados
               (data, ibge, nome, score_medio, alto_risco, total, resumo_json)
               VALUES (?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(), ibge, nome, round(media, 1),
             alto, len(resultados),
             json.dumps({"scores": scores}, ensure_ascii=False)),
        )


def comparacao_municipios():
    with conexao() as con:
        rows = con.execute(
            """SELECT ibge, nome, score_medio, alto_risco, total, MAX(data) as data
               FROM municipios_comparados GROUP BY ibge ORDER BY score_medio DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


inicializar()
