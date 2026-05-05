"""
Benchmark nacional — compara Alenquer com municípios de porte similar.
Usa IBGE para encontrar municípios comparáveis e Portal da Transparência para os dados.
"""
import time
from datetime import datetime

import requests

BASE_IBGE   = "https://servicodados.ibge.gov.br/api/v1"
BASE_PORTAL = "https://api.portaldatransparencia.gov.br/api-de-dados"

# Municípios do Pará de porte similar a Alenquer (30k-80k hab) — 6 para manter benchmark rápido
MUNICIPIOS_BENCHMARK = {
    "1500404": "Alenquer",
    "1504208": "Monte Alegre",
    "1500800": "Almeirim",
    "1503457": "Juruti",
    "1506500": "Porto de Moz",
    "1506807": "Prainha",
}

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "monitor-transparencia-alenquer/1.0"})


def _get_ibge(endpoint, params={}):
    try:
        r = _SESSION.get(f"{BASE_IBGE}/{endpoint}", params=params, timeout=15)
        return r.json() if r.ok else None
    except Exception:
        return None


def _get_portal(endpoint, token, params={}):
    try:
        r = _SESSION.get(f"{BASE_PORTAL}/{endpoint}",
                         headers={"chave-api-dados": token, "accept": "application/json"},
                         params=params, timeout=20)
        return r.json() if r.ok else None
    except Exception:
        return None


# ── Indicadores IBGE ──────────────────────────────────────────────────────────

def indicadores_municipio(ibge):
    """Busca indicadores socioeconômicos do IBGE para um município."""
    indicadores = {}

    # PIB per capita (indicador 47001)
    dados = _get_ibge(f"pesquisas/indicadores/47001/resultados/{ibge}")
    if dados:
        try:
            serie = dados[0]["series"][0]["serie"]
            anos  = sorted(serie.keys())
            indicadores["pib_percapita"] = {"valor": serie.get(anos[-1]), "ano": anos[-1]}
        except Exception:
            pass

    # IDHM (indicador 30255)
    dados = _get_ibge(f"pesquisas/indicadores/30255/resultados/{ibge}")
    if dados:
        try:
            serie = dados[0]["series"][0]["serie"]
            anos  = sorted(serie.keys())
            indicadores["idhm"] = {"valor": serie.get(anos[-1]), "ano": anos[-1]}
        except Exception:
            pass

    return indicadores


def benchmark_municipios(ibge_alvo, token, ibges=None):
    """
    Compara o município alvo com os municípios de referência.
    Retorna ranking com indicadores e posição relativa.
    """
    ibges = ibges or list(MUNICIPIOS_BENCHMARK.keys())
    resultado = []

    for ibge in ibges:
        nome = MUNICIPIOS_BENCHMARK.get(ibge, ibge)

        # Transferências: usa convênios recebidos pelo município (endpoint que funciona)
        convs = _get_portal("convenios", token,
                            {"convenente": f"MUNICIPIO DE {nome.upper()}", "pagina": 1})
        total_transf = sum(
            float(c.get("valorLiberado") or c.get("valor") or 0)
            for c in (convs if isinstance(convs, list) else [])
        )

        # Bolsa Família: endpoint novo retorna lista
        bf_lista = _get_portal("novo-bolsa-familia-por-municipio", token,
                               {"mesAno": datetime.now().strftime("%Y%m"),
                                "codigoIbge": ibge, "pagina": 1})
        bf = bf_lista[0] if isinstance(bf_lista, list) and bf_lista else {}
        benef    = bf.get("quantidadeBeneficiados", 0)
        valor_bf = bf.get("valor", 0)

        resultado.append({
            "ibge":           ibge,
            "nome":           nome,
            "destaque":       ibge == ibge_alvo,
            "transf_total":   total_transf,
            "bf_beneficiarios": benef,
            "bf_valor":       valor_bf,
        })
        time.sleep(0.3)

    # Calcular posições relativas
    _adicionar_rankings(resultado)
    resultado.sort(key=lambda x: x.get("rank_transf", 99))
    return resultado


def _adicionar_rankings(municipios):
    """Adiciona posição no ranking para cada indicador."""
    campos = ["transf_total", "bf_beneficiarios", "bf_valor"]
    for campo in campos:
        ordenados = sorted(municipios, key=lambda x: x.get(campo, 0), reverse=True)
        for i, m in enumerate(ordenados):
            m[f"rank_{campo.replace('_total','').replace('_','_')}"] = i + 1


def resumo_posicao(ibge_alvo, benchmark):
    """Gera resumo da posição do município no benchmark."""
    alvo = next((m for m in benchmark if m["ibge"] == ibge_alvo), None)
    if not alvo:
        return {}

    n = len(benchmark)
    return {
        "municipio":     alvo["nome"],
        "posicao_transf": alvo.get("rank_transf_total", n),
        "total_municipios": n,
        "transf_total":   alvo["transf_total"],
        "bf_beneficiarios": alvo["bf_beneficiarios"],
        "interpretacao":  _interpretar(alvo, n),
    }


def _interpretar(alvo, n):
    pos = alvo.get("rank_transf_total", n)
    pct = pos / n * 100
    if pct <= 25:
        return "Alenquer está entre os municípios que recebem MAIS transferências federais na região"
    if pct <= 50:
        return "Alenquer está acima da média regional em transferências federais"
    if pct <= 75:
        return "Alenquer está abaixo da média regional em transferências federais"
    return "Alenquer recebe MENOS transferências federais que a maioria dos municípios similares"
