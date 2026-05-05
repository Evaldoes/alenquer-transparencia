"""
TSE × Contratos — cruzamento de doadores de campanha com empresas contratadas.
Quem financiou o candidato e depois ganhou contratos = possível retorno de favor.

Fontes:
  - TSE Dados Abertos: dadosabertos.tse.jus.br
  - Receitas de campanha: CSV por estado/município/cargo
"""
import io
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path

import requests

TSE_BASE    = "https://dadosabertos.tse.jus.br/dataset"
CACHE_DIR   = Path(__file__).parent.parent / "dados" / "tse_cache"
ANOS_ELEICAO = [2024, 2022, 2020]

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "monitor-transparencia-alenquer/1.0"})


# ── Download de dados TSE ─────────────────────────────────────────────────────

def _url_receitas(ano):
    """URL do CSV de receitas de campanha do TSE para o Pará."""
    return (
        f"https://cdn.tse.jus.br/estatistica/sead/odsele/"
        f"receitas_candidatos/receitas_candidatos_{ano}_PA.zip"
    )


def _baixar_receitas(ano):
    """Baixa e faz cache do CSV de receitas do TSE."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"receitas_{ano}_PA.csv"

    if cache_path.exists():
        return cache_path.read_text(encoding="latin-1", errors="replace")

    url = _url_receitas(ano)
    try:
        r = _SESSION.get(url, timeout=60, stream=True)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for nome in z.namelist():
                if nome.endswith(".csv"):
                    texto = z.read(nome).decode("latin-1", errors="replace")
                    cache_path.write_text(texto, encoding="utf-8")
                    return texto
    except Exception as e:
        print(f"  [TSE] Erro ao baixar {ano}: {e}")
    return ""


def _limpar_cnpj(v):
    return re.sub(r"\D", "", str(v or ""))


def _limpar_cpf_cnpj(v):
    return re.sub(r"\D", "", str(v or ""))


# ── Parsing de CSV do TSE ────────────────────────────────────────────────────

def _parse_receitas(csv_text, municipio="ALENQUER"):
    """
    Extrai doações para candidatos de Alenquer.
    O CSV do TSE usa ';' como separador e encoding latin-1.
    """
    linhas   = csv_text.splitlines()
    if not linhas:
        return []

    header = [h.strip().lower() for h in linhas[0].split(";")]

    def idx(nome):
        for i, h in enumerate(header):
            if nome in h:
                return i
        return -1

    i_mun    = idx("municipio")
    i_nome   = idx("nome_doador")
    i_cpfcnpj= idx("cpf_cnpj_doador")
    i_valor  = idx("valor_receita")
    i_cand   = idx("nome_candidato")
    i_cargo  = idx("descricao_cargo")
    i_seq    = idx("sequencial_candidato")

    doacoes = []
    for linha in linhas[1:]:
        cols = linha.split(";")
        if i_mun >= 0 and i_mun < len(cols):
            if municipio.upper() not in cols[i_mun].upper():
                continue
        try:
            valor = float(str(cols[i_valor] if i_valor >= 0 else "0")
                          .replace(",", ".").strip() or 0)
        except Exception:
            valor = 0
        doacoes.append({
            "nome_doador":   cols[i_nome].strip()    if i_nome >= 0    else "",
            "cpf_cnpj":      _limpar_cpf_cnpj(cols[i_cpfcnpj] if i_cpfcnpj >= 0 else ""),
            "valor":         valor,
            "candidato":     cols[i_cand].strip()    if i_cand >= 0    else "",
            "cargo":         cols[i_cargo].strip()   if i_cargo >= 0   else "",
        })
    return doacoes


# ── Cruzamento TSE × Contratos ────────────────────────────────────────────────

def cruzar_doadores_contratos(resultados_monitor, anos=None):
    """
    Cruza doadores de campanha com empresas que receberam contratos.
    Retorna lista de coincidências ordenadas por valor doado.
    """
    anos = anos or ANOS_ELEICAO

    # Indexar empresas dos contratos por CNPJ
    empresas_contratos = {}
    for r in resultados_monitor:
        c    = r.get("contrato", {})
        cnpj = _limpar_cnpj(c.get("cnpjContratado"))
        if cnpj:
            empresas_contratos[cnpj] = {
                "nome":       c.get("nomeContratado", ""),
                "valor_contrato": float(c.get("valorInicialCompra") or c.get("valor") or 0),
                "score":      r.get("score", 0),
            }

    # Baixar e cruzar doações
    coincidencias = []
    for ano in anos:
        csv_text = _baixar_receitas(ano)
        if not csv_text:
            continue
        doacoes = _parse_receitas(csv_text)

        for d in doacoes:
            cnpj_doador = d["cpf_cnpj"]
            # CNPJ tem 14 dígitos; CPF tem 11 — só CNPJs importam
            if len(cnpj_doador) != 14:
                continue
            if cnpj_doador in empresas_contratos:
                emp = empresas_contratos[cnpj_doador]
                coincidencias.append({
                    "ano_eleicao":     ano,
                    "cnpj":           cnpj_doador,
                    "nome_empresa":    emp["nome"] or d["nome_doador"],
                    "valor_doacao":    d["valor"],
                    "candidato":       d["candidato"],
                    "cargo":           d["cargo"],
                    "valor_contrato":  emp["valor_contrato"],
                    "score_risco":     emp["score"],
                    "roi":             round(emp["valor_contrato"] / d["valor"], 1)
                                       if d["valor"] > 0 else 0,
                })

    # Ordenar por ROI (retorno sobre doação) — mais suspeito primeiro
    coincidencias.sort(key=lambda x: x["roi"], reverse=True)
    return coincidencias


def resumo_tse(coincidencias):
    if not coincidencias:
        return {"total": 0, "valor_doado": 0, "valor_contratos": 0, "roi_medio": 0}
    return {
        "total":           len(coincidencias),
        "valor_doado":     sum(c["valor_doacao"]   for c in coincidencias),
        "valor_contratos": sum(c["valor_contrato"] for c in coincidencias),
        "roi_medio":       round(sum(c["roi"] for c in coincidencias) / len(coincidencias), 1),
        "candidatos":      list({c["candidato"] for c in coincidencias}),
    }
