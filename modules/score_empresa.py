"""
Score histórico por empresa — rastreia como o risco de cada CNPJ evolui no tempo.
Uma empresa que sobe de 20 para 80 em 6 meses é mais suspeita do que
uma que sempre esteve em 80.
"""
import re
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "dados" / "historico.db"


def _con():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _inicializar():
    with _con() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS empresa_scores (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            data     TEXT NOT NULL,
            cnpj     TEXT NOT NULL,
            nome     TEXT,
            score    INTEGER DEFAULT 0,
            flags    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_empresa_scores_cnpj ON empresa_scores(cnpj);
        """)


_inicializar()


def _limpar_cnpj(v):
    return re.sub(r"\D", "", str(v or ""))


# ── Escrita ───────────────────────────────────────────────────────────────────

def registrar_scores(resultados_monitor):
    """Salva o score atual de cada empresa no banco."""
    with _con() as con:
        for r in resultados_monitor:
            c    = r.get("contrato", {})
            cnpj = _limpar_cnpj(c.get("cnpjContratado"))
            if not cnpj:
                continue
            con.execute(
                """INSERT INTO empresa_scores (data, cnpj, nome, score, flags)
                   VALUES (?,?,?,?,?)""",
                (
                    datetime.now().strftime("%Y-%m-%d"),
                    cnpj,
                    str(c.get("nomeContratado") or "")[:120],
                    r.get("score", 0),
                    "; ".join(r.get("flags", [])[:5]),
                ),
            )


# ── Leitura ───────────────────────────────────────────────────────────────────

def historico_empresa(cnpj):
    """Retorna o histórico de scores de uma empresa específica."""
    cnpj = _limpar_cnpj(cnpj)
    with _con() as con:
        rows = con.execute(
            """SELECT data, score, flags
               FROM empresa_scores WHERE cnpj=?
               ORDER BY data ASC""",
            (cnpj,),
        ).fetchall()
    return [dict(r) for r in rows]


def ranking_empresas(limite=20):
    """
    Ranking das empresas com maior score médio histórico.
    Inclui tendência: subindo / descendo / estável.
    """
    with _con() as con:
        rows = con.execute(
            """SELECT cnpj, MAX(nome) as nome,
                      AVG(score) as score_medio,
                      MAX(score) as score_max,
                      COUNT(*) as aparicoes,
                      MIN(data) as primeira_vez,
                      MAX(data) as ultima_vez
               FROM empresa_scores
               GROUP BY cnpj
               HAVING COUNT(*) >= 1
               ORDER BY score_medio DESC
               LIMIT ?""",
            (limite,),
        ).fetchall()

    resultado = []
    for r in rows:
        hist      = historico_empresa(r["cnpj"])
        tendencia = _calcular_tendencia(hist)
        resultado.append({
            **dict(r),
            "score_medio":  round(r["score_medio"], 1),
            "tendencia":    tendencia,
            "historico":    hist,
        })
    return resultado


def empresas_em_alta(limite=10):
    """
    Empresas com score crescendo — as mais preocupantes.
    Crescimento = score atual > média histórica em mais de 20 pontos.
    """
    ranking = ranking_empresas(50)
    em_alta = []
    for e in ranking:
        hist = e.get("historico", [])
        if len(hist) < 2:
            continue
        score_atual  = hist[-1]["score"]
        score_antigo = hist[0]["score"]
        delta        = score_atual - score_antigo
        if delta >= 20:
            em_alta.append({**e, "delta": delta})
    em_alta.sort(key=lambda x: x["delta"], reverse=True)
    return em_alta[:limite]


def _calcular_tendencia(historico):
    """
    Calcula tendência simples com base nos dois últimos pontos.
    Retorna: "subindo", "descendo", "estável" ou "novo"
    """
    if len(historico) < 2:
        return "novo"
    ultimo     = historico[-1]["score"]
    penultimo  = historico[-2]["score"]
    delta      = ultimo - penultimo
    if delta >  15: return "subindo"
    if delta < -15: return "descendo"
    return "estável"


def resumo_empresas():
    """Resumo rápido para o dashboard."""
    with _con() as con:
        total  = con.execute("SELECT COUNT(DISTINCT cnpj) FROM empresa_scores").fetchone()[0]
        alto   = con.execute(
            "SELECT COUNT(DISTINCT cnpj) FROM empresa_scores WHERE score >= 70"
        ).fetchone()[0]
        subindo = len(empresas_em_alta(50))
    return {"total_empresas": total, "alto_risco": alto, "em_alta": subindo}
