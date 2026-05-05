"""
API Pública REST — expõe os dados analisados para jornalistas, ONGs e outros sistemas.
"""
import json
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

RESULTADO_JSON = Path(__file__).parent.parent / "resultados_monitor.json"

router = APIRouter(prefix="/v1", tags=["público"])

_chamadas: dict = defaultdict(list)
LIMITE_POR_MINUTO = 60


def _rate_limit(request: Request):
    ip  = request.client.host if request.client else "unknown"
    now = time.time()
    _chamadas[ip] = [t for t in _chamadas[ip] if now - t < 60]
    if len(_chamadas[ip]) >= LIMITE_POR_MINUTO:
        raise HTTPException(status_code=429,
                            detail="Rate limit atingido. Máximo 60 req/min.")
    _chamadas[ip].append(now)


def _monitor():
    if not RESULTADO_JSON.exists():
        return []
    return json.loads(RESULTADO_JSON.read_text(encoding="utf-8"))


def _fmt_contrato(r: dict) -> dict:
    c  = r.get("contrato", {})
    return {
        "score":        r.get("score", 0),
        "nivel":        r.get("nivel", ""),
        "empresa":      c.get("nomeContratado", ""),
        "cnpj":         c.get("cnpjContratado", ""),
        "objeto":       str(c.get("objetoCompra") or "")[:200],
        "valor":        float(c.get("valorInicialCompra") or c.get("valor") or 0),
        "modalidade":   c.get("modalidadeCompra", ""),
        "flags":        r.get("flags", []),
        "sancoes_ceis": len((r.get("sancoes") or {}).get("ceis", [])),
        "sancoes_cnep": len((r.get("sancoes") or {}).get("cnep", [])),
        "analisado_em": r.get("analisado_em", "")[:10],
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
def documentacao():
    return {
        "api":    "Transparência Alenquer/PA",
        "versao": "1.0",
        "base":   "/v1",
        "endpoints": {
            "GET /v1/municipio":       "Resumo do município",
            "GET /v1/contratos":       "Lista de contratos analisados",
            "GET /v1/contratos/risco": "Contratos de alto/médio risco",
            "GET /v1/empresa/{cnpj}":  "Histórico de uma empresa",
            "GET /v1/estatisticas":    "Estatísticas gerais",
            "GET /v1/status":          "Status da última análise",
        },
        "rate_limit": f"{LIMITE_POR_MINUTO} req/min por IP",
        "municipio":  "Alenquer/PA — IBGE 1500404",
    }


@router.get("/status", dependencies=[Depends(_rate_limit)])
def status():
    dados = _monitor()
    if not dados:
        return {"status": "sem_dados", "mensagem": "Monitor não executado ainda"}
    ultima = dados[0].get("analisado_em", "")[:10] if dados else ""
    return {
        "status":         "ok",
        "total":          len(dados),
        "alto_risco":     sum(1 for r in dados if r.get("score", 0) >= 70),
        "medio_risco":    sum(1 for r in dados if 40 <= r.get("score", 0) < 70),
        "ultima_analise": ultima,
        "municipio":      "Alenquer/PA",
        "ibge":           "1500404",
    }


@router.get("/municipio", dependencies=[Depends(_rate_limit)])
def municipio():
    from modules.banco import historico_analises
    hist = historico_analises("1500404", limite=6)
    return {
        "nome":               "Alenquer",
        "uf":                 "PA",
        "ibge":               "1500404",
        "regiao":             "Baixo Amazonas",
        "historico_analises": hist,
    }


@router.get("/contratos", dependencies=[Depends(_rate_limit)])
def contratos(
    limite: int = Query(default=20, le=100),
    pagina: int = Query(default=1, ge=1),
    nivel:  Optional[str] = Query(default=None),
):
    dados = _monitor()
    if nivel:
        mapa  = {"alto": (70, 100), "medio": (40, 69), "baixo": (0, 39)}
        faixa = mapa.get(nivel.lower(), (0, 100))
        dados = [r for r in dados if faixa[0] <= r.get("score", 0) <= faixa[1]]
    dados  = sorted(dados, key=lambda x: x.get("score", 0), reverse=True)
    inicio = (pagina - 1) * limite
    return {
        "total":  len(dados),
        "pagina": pagina,
        "limite": limite,
        "dados":  [_fmt_contrato(r) for r in dados[inicio: inicio + limite]],
    }


@router.get("/contratos/risco", dependencies=[Depends(_rate_limit)])
def contratos_risco():
    dados = _monitor()
    risco = sorted([r for r in dados if r.get("score", 0) >= 40],
                   key=lambda x: x["score"], reverse=True)
    return {
        "total":       len(risco),
        "alto_risco":  sum(1 for r in risco if r["score"] >= 70),
        "medio_risco": sum(1 for r in risco if 40 <= r["score"] < 70),
        "dados":       [_fmt_contrato(r) for r in risco[:50]],
    }


@router.get("/empresa/{cnpj}", dependencies=[Depends(_rate_limit)])
def empresa(cnpj: str):
    from modules.score_empresa import historico_empresa
    cnpj_limpo = re.sub(r"\D", "", cnpj)
    dados      = _monitor()
    contratos  = [
        _fmt_contrato(r) for r in dados
        if re.sub(r"\D", "", str(r.get("contrato", {}).get("cnpjContratado") or "")) == cnpj_limpo
    ]
    historico = historico_empresa(cnpj_limpo)
    if not contratos and not historico:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return {
        "cnpj":            cnpj_limpo,
        "nome":            contratos[0]["empresa"] if contratos else "",
        "contratos":       contratos,
        "historico_score": historico,
    }


@router.get("/estatisticas", dependencies=[Depends(_rate_limit)])
def estatisticas():
    dados = _monitor()
    if not dados:
        raise HTTPException(status_code=404, detail="Sem dados")
    scores  = [r.get("score", 0) for r in dados]
    valores = [float(r.get("contrato", {}).get("valorInicialCompra") or 0) for r in dados]
    return {
        "total_contratos": len(dados),
        "score_medio":     round(sum(scores) / len(scores), 1) if scores else 0,
        "score_maximo":    max(scores) if scores else 0,
        "alto_risco":      sum(1 for s in scores if s >= 70),
        "medio_risco":     sum(1 for s in scores if 40 <= s < 70),
        "valor_total":     sum(valores),
        "valor_medio":     round(sum(valores) / len(valores), 2) if valores else 0,
        "com_sancao":      sum(1 for r in dados
                               if (r.get("sancoes") or {}).get("ceis")
                               or (r.get("sancoes") or {}).get("cnep")),
        "com_conflito":    sum(1 for r in dados if r.get("conflitos")),
        "gerado_em":       datetime.now().isoformat(),
    }
