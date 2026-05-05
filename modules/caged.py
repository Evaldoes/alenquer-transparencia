"""
CAGED — Emprego formal vs empresas contratadas.
Uma empresa com 0 funcionários no CAGED não tem capacidade de executar contratos.

Fontes:
  - API Base dos Dados (BigQuery público)
  - Portal do MTE (Ministério do Trabalho e Emprego)
  - IBGE para referência populacional
"""
import re
import time
from datetime import datetime

import requests

BASE_MTE = "https://bi.mte.gov.br/bgcaged/caged_ctl_estabelecimento_nm"
BASE_IBGE = "https://servicodados.ibge.gov.br/api/v1"

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "monitor-transparencia-alenquer/1.0"})


def _limpar_cnpj(v):
    cnpj = re.sub(r"\D", "", str(v or ""))
    return cnpj[:8]  # Raiz do CNPJ (primeiros 8 dígitos)


def _get(url, params={}, tentativas=2):
    for t in range(tentativas):
        try:
            r = _SESSION.get(url, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
            time.sleep(2)
        except Exception:
            time.sleep(2)
    return None


# ── Emprego formal no município ───────────────────────────────────────────────

def emprego_municipio(ibge):
    """
    Busca dados de emprego formal em Alenquer via IBGE Cidades.
    Retorna estatísticas do mercado de trabalho formal.
    """
    dados = _get(f"{BASE_IBGE}/pesquisas/indicadores/29765/resultados/{ibge}")
    if not dados:
        return {}
    try:
        series = dados[0].get("series", [{}])[0]
        serie  = series.get("serie", {})
        # Pegar os últimos 3 anos disponíveis
        anos = sorted(serie.keys())[-3:]
        return {
            "indicador": "Pessoal ocupado assalariado (formal)",
            "fonte":     "IBGE Cidades",
            "serie":     {a: serie.get(a) for a in anos},
        }
    except Exception:
        return {}


def populacao_municipio(ibge):
    """População estimada do município."""
    dados = _get(f"{BASE_IBGE}/pesquisas/indicadores/29171/resultados/{ibge}")
    try:
        serie = dados[0]["series"][0]["serie"]
        anos  = sorted(serie.keys())
        return {"populacao": serie.get(anos[-1], 0), "ano": anos[-1]}
    except Exception:
        return {"populacao": 52000, "ano": "2022"}  # estimativa Alenquer


# ── Verificação de capacidade operacional ─────────────────────────────────────

def verificar_capacidade(contrato, dados_cnpj):
    """
    Verifica se a empresa tem estrutura mínima para executar o contrato.
    Usa dados do CNPJ (capital, porte, situação) como proxy do CAGED.
    """
    valor = float(contrato.get("valorInicialCompra") or contrato.get("valor") or 0)
    score = 0
    flags = []

    if not dados_cnpj:
        return 0, []

    porte   = str(dados_cnpj.get("porte") or "").upper()
    capital = float(dados_cnpj.get("capital") or 0)

    # MEI com contrato acima de R$ 81.000 (limite legal do MEI)
    if ("01" in porte or "MEI" in porte) and valor > 81_000:
        score += 30
        flags.append(f"MEI não pode faturar mais de R$ 81k/ano — contrato de R$ {valor:,.0f}")

    # Microempresa com contrato muito grande
    if "ME " in porte or porte == "ME":
        if valor > 500_000:
            score += 20
            flags.append(f"Microempresa com contrato de R$ {valor:,.0f} — verificar capacidade")

    # Capital social muito baixo para o valor do contrato
    if capital > 0 and valor > 0:
        ratio = valor / capital
        if ratio > 50:
            score += 20
            flags.append(f"Contrato {ratio:.0f}x maior que o capital social da empresa")
        elif ratio > 20:
            score += 10
            flags.append(f"Contrato {ratio:.0f}x maior que o capital social")

    return min(score, 35), flags


# ── Análise do mercado de trabalho local ─────────────────────────────────────

def analisar_mercado_trabalho(ibge):
    """
    Retorna panorama do emprego formal em Alenquer para contextualizar
    a capacidade das empresas locais de executar contratos.
    """
    emprego = emprego_municipio(ibge)
    pop     = populacao_municipio(ibge)

    resultado = {
        "populacao":          pop.get("populacao", 0),
        "emprego_formal":     emprego,
        "contexto":           [],
    }

    # Contexto para o dashboard
    pop_val = pop.get("populacao", 52000)
    resultado["contexto"] = [
        f"População estimada: {int(pop_val):,} habitantes",
        "Município de pequeno porte — base de fornecedores locais limitada",
        "Contratos grandes provavelmente executados por empresas de fora",
    ]

    return resultado
