"""
Comparação de Alenquer com municípios vizinhos do Pará.
"""
import re
import time

import requests

BASE_URL = "https://api.portaldatransparencia.gov.br/api-de-dados"

MUNICIPIOS_PA = {
    "1500404": "Alenquer",
    "1505403": "Óbidos",
    "1505601": "Oriximiná",
    "1507407": "Santarém",
    "1500800": "Almeirim",
    "1502202": "Curuá",
    "1504208": "Monte Alegre",
    "1506807": "Prainha",
}


def _headers(token):
    return {"chave-api-dados": token, "accept": "application/json"}


def _buscar_contratos_municipio(ibge, token, paginas=2):
    contratos = []
    for p in range(1, paginas + 1):
        try:
            r = requests.get(
                f"{BASE_URL}/contratos",
                headers=_headers(token),
                params={"municipioContratado": ibge, "pagina": p, "tamanhoPagina": 20},
                timeout=20,
            )
            r.raise_for_status()
            dados = r.json()
            if not dados:
                break
            contratos.extend(dados if isinstance(dados, list) else [dados])
            time.sleep(0.8)
        except Exception:
            break
    return contratos


def _score_simples(contrato):
    """Score rápido sem consultar CNPJ (para comparação em massa)."""
    score = 0
    modalidade = str(contrato.get("modalidadeCompra") or "").upper()
    valor      = float(contrato.get("valorInicialCompra") or contrato.get("valor") or 0)

    if any(p in modalidade for p in ["DISPENSA", "INEXIGIB"]):
        score += 25
        if valor > 57_500:
            score += 20
    if "EMERG" in modalidade:
        score += 30

    return min(score, 100)


def comparar_municipios(token, ibges=None):
    """
    Compara múltiplos municípios e retorna ranking por score médio.
    ibges: lista de códigos IBGE; None = usar todos do dicionário padrão.
    """
    ibges = ibges or list(MUNICIPIOS_PA.keys())
    resultado = []

    for ibge in ibges:
        nome      = MUNICIPIOS_PA.get(ibge, ibge)
        contratos = _buscar_contratos_municipio(ibge, token)
        if not contratos:
            continue

        scores      = [_score_simples(c) for c in contratos]
        score_medio = sum(scores) / len(scores) if scores else 0
        alto_risco  = sum(1 for s in scores if s >= 50)
        sem_lic     = sum(
            1 for c in contratos
            if any(p in str(c.get("modalidadeCompra") or "").upper()
                   for p in ["DISPENSA", "INEXIGIB"])
        )
        total_valor = sum(
            float(c.get("valorInicialCompra") or c.get("valor") or 0)
            for c in contratos
        )

        resultado.append({
            "ibge":        ibge,
            "nome":        nome,
            "contratos":   len(contratos),
            "score_medio": round(score_medio, 1),
            "alto_risco":  alto_risco,
            "sem_licitacao": sem_lic,
            "total_valor": round(total_valor, 2),
        })

    resultado.sort(key=lambda x: x["score_medio"], reverse=True)
    return resultado
