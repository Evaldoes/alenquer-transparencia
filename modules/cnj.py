"""
CNJ — processos judiciais públicos das empresas contratadas.
Usa o Datajud (API pública do CNJ) e o Escavador como fallback.
"""
import re
import time
from datetime import datetime

import requests

DATAJUD_URL = "https://api-publica.datajud.cnj.jus.br/api_publica_tjpa/_search"
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "monitor-transparencia-alenquer/1.0"})

TIPOS_RELEVANTES = [
    "improbidade", "licitação", "fraude", "corrupção",
    "peculato", "superfaturamento", "dispensa", "inexigibilidade",
    "enriquecimento ilícito", "contrato administrativo",
]


def _limpar_cnpj(v):
    return re.sub(r"\D", "", str(v or ""))


# ── Datajud (CNJ) ──────────────────────────────────────────────────────────────

def buscar_processos_cnpj(cnpj, tentativas=2):
    """
    Busca processos no TJPA via Datajud pelo CNPJ da empresa.
    API pública — sem autenticação para o endpoint básico.
    """
    cnpj_limpo = _limpar_cnpj(cnpj)
    if len(cnpj_limpo) != 14:
        return []

    # Formatar CNPJ para busca: XX.XXX.XXX/XXXX-XX
    cnpj_fmt = (f"{cnpj_limpo[:2]}.{cnpj_limpo[2:5]}.{cnpj_limpo[5:8]}/"
                f"{cnpj_limpo[8:12]}-{cnpj_limpo[12:]}")

    payload = {
        "query": {
            "multi_match": {
                "query": cnpj_fmt,
                "fields": ["partes.nome", "partes.documento"],
            }
        },
        "size": 10,
        "_source": ["numeroProcesso", "classe", "assuntos", "partes",
                    "dataAjuizamento", "tribunal"],
    }

    for t in range(tentativas):
        try:
            r = _SESSION.post(DATAJUD_URL, json=payload, timeout=15)
            if r.status_code == 200:
                hits = r.json().get("hits", {}).get("hits", [])
                return [_normalizar_processo(h["_source"]) for h in hits]
            time.sleep(2)
        except Exception:
            time.sleep(2)
    return []


def _normalizar_processo(src):
    assuntos = [a.get("nome", "") for a in (src.get("assuntos") or [])]
    partes   = [p.get("nome", "") for p in (src.get("partes")   or [])]
    return {
        "numero":      src.get("numeroProcesso", ""),
        "classe":      src.get("classe", {}).get("nome", "") if isinstance(src.get("classe"), dict) else str(src.get("classe", "")),
        "assuntos":    assuntos,
        "partes":      partes[:4],
        "data":        str(src.get("dataAjuizamento", ""))[:10],
        "tribunal":    src.get("tribunal", "TJPA"),
        "relevante":   any(t in " ".join(assuntos).lower() for t in TIPOS_RELEVANTES),
    }


# ── Busca em lote para todos os contratos ─────────────────────────────────────

def analisar_processos_monitor(resultados_monitor, max_empresas=15):
    """
    Busca processos para as empresas com maior score.
    Retorna dict cnpj → {processos, total, tem_irregularidade}.
    """
    # Priorizar empresas de maior risco
    sorted_r = sorted(resultados_monitor, key=lambda x: x.get("score", 0), reverse=True)
    resultado = {}

    for r in sorted_r[:max_empresas]:
        c    = r.get("contrato", {})
        cnpj = _limpar_cnpj(c.get("cnpjContratado") or "")
        if not cnpj or cnpj in resultado:
            continue

        processos = buscar_processos_cnpj(cnpj)
        irregulares = [p for p in processos if p["relevante"]]

        resultado[cnpj] = {
            "nome":              c.get("nomeContratado", ""),
            "score":             r.get("score", 0),
            "processos":         processos,
            "total":             len(processos),
            "tem_irregularidade": len(irregulares) > 0,
            "irregulares":       irregulares,
        }
        time.sleep(0.5)

    return resultado


def score_cnj(cnpj, processos_dict):
    """Score extra e flags baseados nos processos encontrados."""
    cnpj = _limpar_cnpj(cnpj)
    info = processos_dict.get(cnpj, {})
    score = 0
    flags = []

    irregulares = info.get("irregulares", [])
    total       = info.get("total", 0)

    if irregulares:
        score += 35
        assuntos = [a for p in irregulares for a in p.get("assuntos", [])]
        flags.append(f"Empresa com {len(irregulares)} processo(s) judicial(is) por irregularidade: "
                     f"{', '.join(set(assuntos[:3]))}")
    elif total > 5:
        score += 10
        flags.append(f"Empresa com {total} processos judiciais no TJPA")

    return min(score, 35), flags
