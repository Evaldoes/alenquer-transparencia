"""
SIOPS — Execução orçamentária de saúde por município.
Fonte: convênios federais de saúde para o município (Portal da Transparência).
Os endpoints /transferencias e /despesas exigem permissão especial;
usamos convênios filtrados por termos de saúde como proxy.
"""
import time
from datetime import datetime

import requests

BASE_PORTAL = "https://api.portaldatransparencia.gov.br/api-de-dados"

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "monitor-transparencia-alenquer/1.0"})

TERMOS_SAUDE = [
    "SAÚDE", "SAUDE", "SUS", "HOSPITAL", "FUNASA", "UBS", "ATENÇÃO BÁSICA",
    "ATENCAO BASICA", "VIGILÂNCIA", "VIGILANCIA", "FARMÁCIA", "FARMACIA",
    "MÉDICO", "MEDICO", "ENFERMAGEM", "AMBULÂNCIA", "AMBULANCIA",
    "ABASTECIMENTO DE AGUA", "SANEAMENTO",
]


def _get(endpoint, token, params):
    try:
        r = _SESSION.get(
            f"{BASE_PORTAL}/{endpoint}",
            headers={"chave-api-dados": token, "accept": "application/json"},
            params=params,
            timeout=15,
        )
        return r.json() if r.ok else None
    except Exception:
        return None


def _buscar_convenios_saude(token, paginas=5):
    """Convênios de Alenquer com objeto relacionado a saúde."""
    resultado = []
    for p in range(1, paginas + 1):
        dados = _get("convenios", token,
                     {"convenente": "MUNICIPIO DE ALENQUER", "pagina": p})
        if not isinstance(dados, list) or not dados:
            break
        for conv in dados:
            dim    = conv.get("dimConvenio") or {}
            objeto = str(dim.get("objeto") or "").upper()
            orgao  = str((conv.get("orgao") or {}).get("nome") or "").upper()
            if any(t in objeto or t in orgao for t in TERMOS_SAUDE):
                resultado.append(conv)
        time.sleep(0.3)
    return resultado


def _buscar_bpc(ibge, token):
    """BPC — Benefício de Prestação Continuada (dado real, endpoint público)."""
    dados = _get("bpc-por-municipio", token,
                 {"mesAno": datetime.now().strftime("%Y%m"),
                  "codigoIbge": ibge, "pagina": 1})
    if isinstance(dados, list) and dados:
        return dados[0]
    return {}


def analisar_saude(ibge, token, ano=None):
    """
    Analisa execução de saúde via convênios federais de saúde recebidos pelo município.
    """
    ano = ano or datetime.now().year

    convs = _buscar_convenios_saude(token)
    bpc   = _buscar_bpc(ibge, token)

    total_recebido = sum(
        float(c.get("valorLiberado") or c.get("valor") or 0) for c in convs
    )
    # Proxy de gasto: valor total dos convênios de saúde firmados
    total_contratado = sum(float(c.get("valor") or 0) for c in convs)
    pct_executado = (total_recebido / total_contratado * 100) if total_contratado > 0 else 0

    alertas = []
    if not convs:
        alertas.append("Nenhum convênio federal de saúde encontrado para o município")
    elif pct_executado < 50:
        alertas.append(
            f"Apenas {pct_executado:.0f}% do valor contratado em saúde foi liberado — "
            "possível inadimplência ou execução lenta"
        )
    if bpc.get("quantidadeBeneficiados", 0) > 0:
        alertas.append(
            f"BPC: {int(bpc.get('quantidadeBeneficiados', 0)):,} beneficiários "
            f"recebendo R$ {float(bpc.get('valor', 0)):,.0f}/mês"
        )

    inadimplentes = [c for c in convs if "INADIMPL" in str(c.get("situacao", "")).upper()]
    if inadimplentes:
        alertas.append(
            f"{len(inadimplentes)} convênio(s) de saúde em situação de inadimplência"
        )

    top = sorted(convs,
                 key=lambda c: float(c.get("valorLiberado") or c.get("valor") or 0),
                 reverse=True)

    return {
        "ano":             ano,
        "total_recebido":  total_recebido,
        "total_gasto":     total_recebido,   # proxy: liberado = gasto
        "pct_executado":   round(pct_executado, 1),
        "nao_executado":   max(total_contratado - total_recebido, 0),
        "alertas":         alertas,
        "bpc":             bpc,
        "n_convenios":     len(convs),
        "top_despesas": [
            {
                "nomeFavorecido": (c.get("orgao") or {}).get("nome", "N/A"),
                "valorLiquido":   float(c.get("valorLiberado") or c.get("valor") or 0),
                "objeto": str((c.get("dimConvenio") or {}).get("objeto") or "")[:60],
                "situacao": c.get("situacao", ""),
            }
            for c in top[:10]
        ],
        "transferencias": [
            {
                "acao":  (c.get("orgao") or {}).get("sigla", "N/A"),
                "valor": float(c.get("valorLiberado") or c.get("valor") or 0),
            }
            for c in top[:10]
        ],
    }


def historico_saude(ibge, token, anos=4, _analise_cache=None):
    """Histórico anual dos últimos N anos: BPC anual estimado + convênios proporcionais."""
    analise = _analise_cache or analisar_saude(ibge, token)
    total_conv  = analise["total_recebido"]
    anual_conv  = round(total_conv / max(anos, 1), 0) if total_conv > 0 else 0
    pct         = analise["pct_executado"]
    ano_atual   = datetime.now().year

    resultado = []
    for i in range(anos - 1, -1, -1):
        ano = ano_atual - i
        # BPC: usa dezembro do ano passado, mês atual para o ano corrente
        mes_ref = f"{ano}12" if ano < ano_atual else datetime.now().strftime("%Y%m")
        bpc = _get("bpc-por-municipio", token,
                   {"mesAno": mes_ref, "codigoIbge": ibge, "pagina": 1})
        bpc_mensal = float(bpc[0].get("valor", 0)) if isinstance(bpc, list) and bpc else 0.0
        bpc_anual  = round(bpc_mensal * 12, 0)
        resultado.append({
            "ano":           ano,
            "recebido":      anual_conv + bpc_anual,
            "gasto":         anual_conv + bpc_anual,
            "pct_executado": pct,
            "bpc_anual":     bpc_anual,
            "conv_anual":    anual_conv,
        })
        time.sleep(0.2)
    return resultado
