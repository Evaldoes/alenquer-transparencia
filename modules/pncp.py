"""
Integração com o PNCP — Portal Nacional de Contratações Públicas.
API gratuita, sem token. Obrigatório para todos os contratos desde 2024.
Complementa o Portal da Transparência com dados mais recentes.
"""
import time
from datetime import datetime, timedelta

import requests

BASE_URL   = "https://pncp.gov.br/api/pncp/v1"
CONSULTA   = "https://pncp.gov.br/api/consulta/v1"
IBGE_ALENQUER = "1500404"

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "monitor-transparencia-alenquer/1.0",
    "Accept": "application/json",
})


def _get(url, params={}, tentativas=3):
    for t in range(tentativas):
        try:
            r = _SESSION.get(url, params=params, timeout=20)
            if r.status_code == 429:
                time.sleep(5 * (t + 1))
                continue
            if r.status_code == 200:
                return r.json()
            return None
        except Exception:
            time.sleep(2)
    return None


def buscar_contratacoes(dias=60, paginas=3):
    """
    Busca contratações publicadas no PNCP para Alenquer nos últimos N dias.
    """
    hoje   = datetime.now()
    inicio = hoje - timedelta(days=dias)
    resultado = []

    for p in range(1, paginas + 1):
        data = _get(f"{CONSULTA}/contratacoes/publicacao", {
            "dataInicial":    inicio.strftime("%Y%m%d"),
            "dataFinal":      hoje.strftime("%Y%m%d"),
            "codigoMunicipio": IBGE_ALENQUER,
            "pagina":         p,
            "tamanhoPagina":  20,
        })
        if not data:
            break
        itens = data.get("data") or (data if isinstance(data, list) else [])
        if not itens:
            break
        resultado.extend(itens)
        time.sleep(0.5)

    return resultado


def buscar_licitacoes_abertas():
    """
    Busca licitações com prazo aberto para Alenquer.
    Útil para monitorar em tempo real.
    """
    hoje   = datetime.now()
    inicio = hoje - timedelta(days=30)
    data   = _get(f"{CONSULTA}/contratacoes/proposta", {
        "dataFinal":      hoje.strftime("%Y%m%d"),
        "dataInicial":    inicio.strftime("%Y%m%d"),
        "codigoMunicipio": IBGE_ALENQUER,
        "pagina":         1,
        "tamanhoPagina":  20,
    })
    if not data:
        return []
    return data.get("data") or (data if isinstance(data, list) else [])


def buscar_atas_registro(dias=90):
    """Atas de registro de preço — base para comparação de preços."""
    hoje   = datetime.now()
    inicio = hoje - timedelta(days=dias)
    data   = _get(f"{CONSULTA}/atas/publicacao", {
        "dataInicial":    inicio.strftime("%Y%m%d"),
        "dataFinal":      hoje.strftime("%Y%m%d"),
        "codigoMunicipio": IBGE_ALENQUER,
        "pagina":         1,
        "tamanhoPagina":  20,
    })
    if not data:
        return []
    return data.get("data") or (data if isinstance(data, list) else [])


def normalizar_contratacao(item):
    """Converte item do PNCP para o formato padrão do monitor."""
    return {
        "nomeContratado":       item.get("nomeRazaoSocialFornecedor") or item.get("nomeContratado") or "N/A",
        "cnpjContratado":       item.get("cnpjFornecedor") or item.get("cnpj") or "",
        "objetoCompra":         item.get("objetoCompra") or item.get("descricao") or "",
        "valorInicialCompra":   item.get("valorTotalHomologado") or item.get("valorEstimado") or 0,
        "modalidadeCompra":     item.get("modalidadeNome") or item.get("modalidade") or "",
        "dataAssinatura":       item.get("dataAssinatura") or item.get("dataPublicacaoPncp") or "",
        "fonte":                "PNCP",
        "_raw":                 item,
    }


def analisar_pncp(contratacoes):
    """
    Análise rápida das contratações do PNCP.
    Retorna estatísticas e lista normalizada.
    """
    normalizados = [normalizar_contratacao(c) for c in contratacoes]

    total_valor = sum(
        float(c.get("valorInicialCompra") or 0) for c in normalizados
    )
    por_modalidade = {}
    for c in normalizados:
        mod = c.get("modalidadeCompra") or "N/A"
        por_modalidade[mod] = por_modalidade.get(mod, 0) + 1

    dispensas = sum(
        1 for c in normalizados
        if any(p in str(c.get("modalidadeCompra") or "").upper()
               for p in ["DISPENSA", "INEXIG"])
    )

    return {
        "total":            len(normalizados),
        "valor_total":      total_valor,
        "dispensas":        dispensas,
        "por_modalidade":   por_modalidade,
        "contratacoes":     normalizados,
    }
