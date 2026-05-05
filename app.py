import json
import os
import re
import warnings
warnings.filterwarnings("ignore", message="urllib3.*doesn't match", category=Warning)
warnings.filterwarnings("ignore", message="chardet.*doesn't match", category=Warning)
import requests
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Header, Query, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List

from modules import banco
from modules.grafo import construir_grafo
from modules.noticias import buscar_todas as buscar_noticias
from modules.municipios import comparar_municipios
from modules.copypaste import detectar_grupos_similares
from modules.pncp import buscar_contratacoes, analisar_pncp, normalizar_contratacao
from modules.score_empresa import registrar_scores, ranking_empresas, empresas_em_alta, resumo_empresas
from modules.exportar import exportar_csv, exportar_excel
from modules.tse import cruzar_doadores_contratos, resumo_tse
from modules.cnj import analisar_processos_monitor
from modules.siops import analisar_saude, historico_saude
from modules.caged import analisar_mercado_trabalho
from modules.embeddings import detectar_similares_semanticos
from modules.benchmark import benchmark_municipios, resumo_posicao
from modules.agendamento import instalar_cron, remover_cron, listar_crons, status as status_cron
from modules.api_publica import router as api_publica_router

IBGE_ALENQUER = "1500404"
BASE_URL       = "https://api.portaldatransparencia.gov.br/api-de-dados"
RESULTADO_JSON = Path(__file__).parent / "resultados_monitor.json"
DADOS_DIR      = Path(__file__).parent / "dados"

app = FastAPI(title="Alenquer Transparência", docs_url=None, redoc_url=None)
app.include_router(api_publica_router)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _headers(token: str) -> dict:
    return {"chave-api-dados": token, "accept": "application/json"}


def _api(endpoint: str, token: str, params: dict = {}):
    r = requests.get(f"{BASE_URL}/{endpoint}", headers=_headers(token),
                     params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def _monitor_dados() -> list:
    if not RESULTADO_JSON.exists():
        return []
    return json.loads(RESULTADO_JSON.read_text(encoding="utf-8"))


def _convenios_alenquer(token: str, paginas: int = 3) -> list:
    resultado = []
    for p in range(1, paginas + 1):
        try:
            data = _api("convenios", token,
                        {"convenente": "MUNICIPIO DE ALENQUER", "pagina": p})
            if not isinstance(data, list) or not data:
                break
            resultado.extend(data)
        except Exception:
            break
    return resultado


def _historico_mensal(endpoint: str, token: str, ibge: str, meses: int = 12,
                      campo_valor: str = "valor",
                      campo_benef: str = "quantidadeBeneficiados") -> list:
    resultado = []
    hoje = datetime.now()
    for i in range(meses):
        d = hoje - timedelta(days=30 * i)
        mes_ano = d.strftime("%Y%m")
        try:
            data = _api(endpoint, token, {"mesAno": mes_ano, "codigoIbge": ibge, "pagina": 1})
            if isinstance(data, list) and data:
                item = data[0]
                resultado.append({
                    "mesAno":        d.strftime("%b/%Y"),
                    "mesAnoNum":     mes_ano,
                    "valor":         float(item.get(campo_valor, 0) or 0),
                    "beneficiarios": int(item.get(campo_benef, 0) or 0),
                })
            else:
                resultado.append({"mesAno": d.strftime("%b/%Y"), "mesAnoNum": mes_ano,
                                   "valor": 0, "beneficiarios": 0})
        except Exception:
            resultado.append({"mesAno": d.strftime("%b/%Y"), "mesAnoNum": mes_ano,
                               "valor": 0, "beneficiarios": 0})
    resultado.reverse()
    return resultado


# ── Página principal ──────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


# ── Token ─────────────────────────────────────────────────────────────────────

@app.get("/api/token")
def get_token():
    env_file = Path(__file__).parent / ".env"
    tk = ""
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("PORTAL_TOKEN="):
                tk = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not tk:
        tk = os.environ.get("PORTAL_TOKEN", "")
    return {"token": tk}


# ── Bolsa Família ─────────────────────────────────────────────────────────────

@app.get("/api/bolsa-familia")
def bolsa_familia(x_api_token: str = Header(default="", alias="x-api-token")):
    meses = []
    hoje  = datetime.now()
    for i in range(12):
        d = hoje - timedelta(days=30 * i)
        mes_ano = d.strftime("%Y%m")
        try:
            data = _api("novo-bolsa-familia-por-municipio", x_api_token,
                        {"mesAno": mes_ano, "codigoIbge": IBGE_ALENQUER, "pagina": 1})
            if isinstance(data, list) and data:
                item = data[0]
                meses.append({
                    "mesAno":        d.strftime("%b/%Y"),
                    "beneficiarios": item.get("quantidadeBeneficiados", 0),
                    "valor":         item.get("valor", 0),
                })
            else:
                meses.append({"mesAno": d.strftime("%b/%Y"), "beneficiarios": 0, "valor": 0})
        except Exception:
            meses.append({"mesAno": d.strftime("%b/%Y"), "beneficiarios": 0, "valor": 0})
    meses.reverse()
    return meses


@app.get("/api/transferencias")
def transferencias(x_api_token: str = Header(default="", alias="x-api-token")):
    try:
        hoje = datetime.now()
        result = []
        for i in range(12):
            d = hoje - timedelta(days=30 * i)
            mes_ano = d.strftime("%Y%m")
            try:
                data = _api("novo-bolsa-familia-por-municipio", x_api_token,
                            {"mesAno": mes_ano, "codigoIbge": IBGE_ALENQUER, "pagina": 1})
                if isinstance(data, list) and data:
                    item = data[0]
                    result.append({
                        "acao":          "Bolsa Família",
                        "mesAno":        d.strftime("%b/%Y"),
                        "valor":         item.get("valor", 0),
                        "beneficiarios": item.get("quantidadeBeneficiados", 0),
                    })
            except Exception:
                pass
        result.reverse()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bpc")
def bpc_historico(x_api_token: str = Header(default="", alias="x-api-token")):
    try:
        return _historico_mensal("bpc-por-municipio", x_api_token, IBGE_ALENQUER)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/seguro-defeso")
def seguro_defeso(x_api_token: str = Header(default="", alias="x-api-token")):
    try:
        return _historico_mensal("seguro-defeso-por-municipio", x_api_token, IBGE_ALENQUER)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/beneficios/resumo")
def beneficios_resumo(x_api_token: str = Header(default="", alias="x-api-token")):
    try:
        mes_ano = datetime.now().strftime("%Y%m")
        def _fetch(ep):
            try:
                d = _api(ep, x_api_token,
                         {"mesAno": mes_ano, "codigoIbge": IBGE_ALENQUER, "pagina": 1})
                return d[0] if isinstance(d, list) and d else {}
            except Exception:
                return {}
        bf  = _fetch("novo-bolsa-familia-por-municipio")
        bpc = _fetch("bpc-por-municipio")
        sd  = _fetch("seguro-defeso-por-municipio")
        return {
            "bf":  {"beneficiarios": int(bf.get("quantidadeBeneficiados", 0) or 0),
                    "valor": float(bf.get("valor", 0) or 0)},
            "bpc": {"beneficiarios": int(bpc.get("quantidadeBeneficiados", 0) or 0),
                    "valor": float(bpc.get("valor", 0) or 0)},
            "seguro_defeso": {"beneficiarios": int(sd.get("quantidadeBeneficiados", 0) or 0),
                              "valor": float(sd.get("valor", 0) or 0)},
            "total_beneficiarios": (int(bf.get("quantidadeBeneficiados", 0) or 0)
                                    + int(bpc.get("quantidadeBeneficiados", 0) or 0)
                                    + int(sd.get("quantidadeBeneficiados", 0) or 0)),
            "total_valor": (float(bf.get("valor", 0) or 0)
                            + float(bpc.get("valor", 0) or 0)
                            + float(sd.get("valor", 0) or 0)),
            "mes": datetime.now().strftime("%b/%Y"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/convenios/analise")
def convenios_analise(x_api_token: str = Header(default="", alias="x-api-token")):
    try:
        convs = _convenios_alenquer(x_api_token, paginas=6)
        total_valor    = sum(float(c.get("valor") or 0) for c in convs)
        total_liberado = sum(float(c.get("valorLiberado") or 0) for c in convs)
        pct_exec       = round(total_liberado / total_valor * 100, 1) if total_valor else 0

        por_min = {}
        for c in convs:
            org  = (c.get("orgao") or {}).get("orgaoMaximo") or c.get("orgao") or {}
            nome = (org.get("nome") or org.get("sigla") or "N/A")[:50]
            por_min.setdefault(nome, {"valor": 0, "liberado": 0, "qtd": 0})
            por_min[nome]["valor"]    += float(c.get("valor") or 0)
            por_min[nome]["liberado"] += float(c.get("valorLiberado") or 0)
            por_min[nome]["qtd"]      += 1
        por_min_lista = sorted(por_min.items(), key=lambda x: x[1]["valor"], reverse=True)[:10]

        por_sit = {}
        for c in convs:
            sit = (c.get("situacao") or "N/A").upper()
            por_sit.setdefault(sit, {"qtd": 0, "valor": 0})
            por_sit[sit]["qtd"]   += 1
            por_sit[sit]["valor"] += float(c.get("valor") or 0)

        por_ano = {}
        for c in convs:
            ano = (c.get("dataInicioVigencia") or "")[:4]
            if ano.isdigit():
                por_ano.setdefault(ano, {"qtd": 0, "valor": 0})
                por_ano[ano]["qtd"]   += 1
                por_ano[ano]["valor"] += float(c.get("valor") or 0)

        top = sorted(convs,
                     key=lambda c: float(c.get("valorLiberado") or c.get("valor") or 0),
                     reverse=True)
        return {
            "total_convenios": len(convs),
            "total_valor":     total_valor,
            "total_liberado":  total_liberado,
            "pct_executado":   pct_exec,
            "por_ministerio": [{"nome": k, "valor": v["valor"],
                                 "liberado": v["liberado"], "qtd": v["qtd"]}
                                for k, v in por_min_lista],
            "por_situacao":   [{"situacao": k, "qtd": v["qtd"], "valor": v["valor"]}
                                for k, v in sorted(por_sit.items(),
                                                   key=lambda x: x[1]["qtd"], reverse=True)],
            "por_ano":        [{"ano": k, "qtd": v["qtd"], "valor": v["valor"]}
                                for k, v in sorted(por_ano.items())],
            "top_convenios":  [{
                "objeto":     str((c.get("dimConvenio") or {}).get("objeto") or "")[:80],
                "ministerio": ((c.get("orgao") or {}).get("orgaoMaximo")
                               or c.get("orgao") or {}).get("sigla", "N/A"),
                "valor":      float(c.get("valor") or 0),
                "liberado":   float(c.get("valorLiberado") or 0),
                "situacao":   c.get("situacao") or "",
                "inicio":     (c.get("dataInicioVigencia") or "")[:10],
                "fim":        (c.get("dataFinalVigencia") or "")[:10],
            } for c in top[:20]],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/despesas")
def despesas(x_api_token: str = Header(default="", alias="x-api-token")):
    try:
        convs = _convenios_alenquer(x_api_token)
        resultado = sorted([
            {
                "nomeFavorecido": (c.get("orgao") or {}).get("nome", "N/A"),
                "nomeFuncao":     (c.get("tipoInstrumento") or {}).get("descricao", "Convênio")
                                  if isinstance(c.get("tipoInstrumento"), dict)
                                  else str(c.get("tipoInstrumento") or "Convênio"),
                "valor":          float(c.get("valor") or 0),
                "valorLiquido":   float(c.get("valorLiberado") or c.get("valor") or 0),
                "objeto":         str((c.get("dimConvenio") or {}).get("objeto") or "")[:80],
                "situacao":       c.get("situacao", ""),
            }
            for c in convs
        ], key=lambda x: x["valorLiquido"], reverse=True)
        return resultado[:20]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/contratos")
def contratos(x_api_token: str = Header(default="", alias="x-api-token")):
    try:
        convs = _convenios_alenquer(x_api_token)
        return [{
            "nomeContratado":     (c.get("orgao") or {}).get("nome", "N/A"),
            "cnpjContratado":     re.sub(r"\D", "", str((c.get("orgao") or {}).get("cnpj") or "")),
            "objetoCompra":       str((c.get("dimConvenio") or {}).get("objeto") or "")[:150],
            "valorInicialCompra": float(c.get("valor") or 0),
            "valorLiberado":      float(c.get("valorLiberado") or 0),
            "modalidadeCompra":   (c.get("tipoInstrumento") or {}).get("descricao", "Convênio")
                                  if isinstance(c.get("tipoInstrumento"), dict)
                                  else str(c.get("tipoInstrumento") or "Convênio"),
            "situacao":           c.get("situacao", ""),
            "dataInicio":         c.get("dataInicioVigencia", ""),
            "dataFim":            c.get("dataFinalVigencia", ""),
        } for c in convs[:20]]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Monitor de risco ──────────────────────────────────────────────────────────

@app.get("/api/monitor")
def monitor_resultados():
    if not RESULTADO_JSON.exists():
        raise HTTPException(status_code=404,
                            detail="Execute: python monitor.py --token SEU_TOKEN")
    return _monitor_dados()


@app.get("/api/historico")
def historico():
    return banco.historico_analises(IBGE_ALENQUER)


# ── Grafo ─────────────────────────────────────────────────────────────────────

@app.get("/api/grafo")
def grafo():
    dados = _monitor_dados()
    if not dados:
        raise HTTPException(status_code=404, detail="Sem dados do monitor")
    _, grafo_json = construir_grafo(dados)
    return grafo_json


# ── IA ────────────────────────────────────────────────────────────────────────

class IaRequest(BaseModel):
    anthropic_key: str

@app.post("/api/ia/analisar")
def ia_analisar(body: IaRequest):
    try:
        from modules.ia_analise import analisar_lote, resumo_geral_ia
        dados     = _monitor_dados()
        hist      = banco.historico_analises(IBGE_ALENQUER, limite=3)
        analises  = analisar_lote(dados, body.anthropic_key, apenas_risco=True, max_contratos=8)
        resumo    = resumo_geral_ia(dados, hist, body.anthropic_key)
        return {"resumo": resumo, "analises": analises}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Notícias ──────────────────────────────────────────────────────────────────

@app.get("/api/noticias")
def noticias_cached():
    return banco.listar_noticias(30)


@app.post("/api/noticias/atualizar")
def noticias_atualizar():
    try:
        novas = buscar_noticias(salvar_no_banco=True)
        return {"novas": len(novas)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Municípios ────────────────────────────────────────────────────────────────

class MunicipiosRequest(BaseModel):
    ibges: Optional[List[str]] = None

@app.post("/api/municipios/comparar")
def municipios_comparar(body: MunicipiosRequest,
                        x_api_token: str = Header(default="", alias="x-api-token")):
    try:
        resultado = comparar_municipios(x_api_token, body.ibges)
        for r in resultado:
            banco.salvar_comparacao(r["ibge"], r["nome"],
                                    [{"score": r["score_medio"]}] * r["contratos"])
        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/municipios/historico")
def municipios_historico():
    return banco.comparacao_municipios()


# ── Denúncias ─────────────────────────────────────────────────────────────────

class DenunciaRequest(BaseModel):
    descricao: str = ""
    local:     str = ""
    lat:       Optional[float] = None
    lon:       Optional[float] = None

@app.post("/api/denuncia")
def registrar_denuncia(body: DenunciaRequest):
    try:
        id_ = banco.salvar_denuncia(
            descricao=body.descricao,
            local=body.local,
            lat=body.lat,
            lon=body.lon,
        )
        return {"id": id_, "status": "registrada"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/denuncias")
def listar_denuncias():
    return banco.listar_denuncias()


# ── PDF ───────────────────────────────────────────────────────────────────────

class PdfRequest(BaseModel):
    bolsa_familia:  list = []
    transferencias: list = []
    despesas:       list = []

@app.post("/api/pdf/gerar")
def gerar_pdf(body: PdfRequest):
    try:
        from modules.pdf_report import gerar_pdf as _gerar
        caminho = _gerar(
            dados_bf           = body.bolsa_familia,
            dados_transf       = body.transferencias,
            dados_desp         = body.despesas,
            resultados_monitor = _monitor_dados(),
        )
        return {"arquivo": Path(caminho).name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pdf/download/{nome}")
def download_pdf(nome: str):
    caminho = DADOS_DIR / nome
    if not caminho.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    return FileResponse(str(caminho), filename=nome)


# ── Copy-paste ────────────────────────────────────────────────────────────────

@app.get("/api/copypaste")
def copypaste():
    dados = _monitor_dados()
    if not dados:
        raise HTTPException(status_code=404, detail="Sem dados do monitor")
    contratos = [r.get("contrato", {}) for r in dados]
    pares, clusters = detectar_grupos_similares(contratos, limiar=0.75)
    return {"pares": pares[:30], "clusters": clusters[:15]}


# ── PNCP ──────────────────────────────────────────────────────────────────────

@app.get("/api/pncp")
def pncp_dados(dias: int = Query(default=60)):
    try:
        contratacoes = buscar_contratacoes(dias=dias)
        return analisar_pncp(contratacoes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Score histórico de empresas ───────────────────────────────────────────────

@app.get("/api/empresas/ranking")
def empresas_ranking():
    return ranking_empresas()


@app.get("/api/empresas/em-alta")
def empresas_em_alta_route():
    return empresas_em_alta()


@app.get("/api/empresas/resumo")
def empresas_resumo():
    return resumo_empresas()


# ── Diário Oficial ────────────────────────────────────────────────────────────

@app.get("/api/diario-oficial")
def diario_oficial():
    noticias = banco.listar_noticias(30)
    return [n for n in noticias
            if "DOE" in n.get("fonte", "") or "Diário" in n.get("fonte", "")]


@app.post("/api/diario-oficial/atualizar")
def doe_atualizar():
    try:
        from modules.diario_oficial import buscar_publicacoes
        pubs = buscar_publicacoes(dias=30, salvar_no_banco=True)
        return {"publicacoes": len(pubs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Obras ─────────────────────────────────────────────────────────────────────

@app.get("/api/obras")
def obras(x_api_token: str = Header(default="", alias="x-api-token")):
    try:
        r = requests.get(f"{BASE_URL}/obras", headers=_headers(x_api_token),
                         params={"municipio": IBGE_ALENQUER, "pagina": 1, "tamanhoPagina": 30},
                         timeout=20)
        if r.status_code == 403:
            raise HTTPException(status_code=403,
                                detail="Endpoint /obras requer token premium do Portal da Transparência")
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except HTTPException:
        raise
    except Exception as e:
        if "403" in str(e):
            raise HTTPException(status_code=403, detail="Acesso negado ao endpoint /obras")
        raise HTTPException(status_code=500, detail=str(e))


# ── Exportação ────────────────────────────────────────────────────────────────

@app.get("/api/exportar/csv")
def exportar_csv_route():
    dados = _monitor_dados()
    if not dados:
        raise HTTPException(status_code=404, detail="Sem dados")
    csv_bytes = exportar_csv(dados)
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=alenquer_contratos.csv"},
    )


@app.get("/api/exportar/excel")
def exportar_excel_route():
    dados = _monitor_dados()
    if not dados:
        raise HTTPException(status_code=404, detail="Sem dados")
    contratos = [r.get("contrato", {}) for r in dados]
    pares, _  = detectar_grupos_similares(contratos)
    pncp_raw  = buscar_contratacoes(dias=60)
    pncp_norm = [normalizar_contratacao(c) for c in pncp_raw]
    xls_bytes = exportar_excel(dados, pares, pncp_norm)
    return Response(
        content=xls_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=alenquer_transparencia.xlsx"},
    )


# ── TSE ───────────────────────────────────────────────────────────────────────

@app.get("/api/tse")
def tse_cruzamento(x_api_token: str = Header(default="", alias="x-api-token")):
    dados = _monitor_dados()
    if not dados:
        raise HTTPException(status_code=404, detail="Sem dados do monitor")
    coincidencias = cruzar_doadores_contratos(dados)
    return {"resumo": resumo_tse(coincidencias), "dados": coincidencias[:30]}


# ── CNJ ───────────────────────────────────────────────────────────────────────

@app.get("/api/cnj")
def cnj_processos():
    dados = _monitor_dados()
    if not dados:
        raise HTTPException(status_code=404, detail="Sem dados do monitor")
    return analisar_processos_monitor(dados, max_empresas=10)


# ── Saúde ─────────────────────────────────────────────────────────────────────

@app.get("/api/saude")
def saude(x_api_token: str = Header(default="", alias="x-api-token")):
    try:
        analise = analisar_saude(IBGE_ALENQUER, x_api_token)
        hist    = historico_saude(IBGE_ALENQUER, x_api_token, anos=4, _analise_cache=analise)
        return {"analise": analise, "historico": hist}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Mercado de trabalho ───────────────────────────────────────────────────────

@app.get("/api/mercado-trabalho")
def mercado_trabalho():
    return analisar_mercado_trabalho(IBGE_ALENQUER)


# ── Semântico ─────────────────────────────────────────────────────────────────

@app.get("/api/semantico")
def semantico():
    dados     = _monitor_dados()
    contratos = [r.get("contrato", {}) for r in dados]
    pares     = detectar_similares_semanticos(contratos, limiar=0.82)
    return {"pares": pares[:20], "total": len(pares)}


# ── OCR ───────────────────────────────────────────────────────────────────────

class OcrUrlRequest(BaseModel):
    url: Optional[str] = None

@app.post("/api/ocr")
async def ocr_pdf(request: Request):
    try:
        from modules.ocr import extrair_texto_pdf, analisar_texto_contrato
        body = await request.body()
        if body:
            texto = extrair_texto_pdf(body)
        else:
            payload = await request.json()
            url = payload.get("url") if payload else None
            if url:
                from modules.ocr import extrair_texto_url
                texto = extrair_texto_url(url)
            else:
                raise HTTPException(status_code=400,
                                    detail="Envie um PDF no body ou uma URL em JSON")
        analise = analisar_texto_contrato(texto)
        return {"texto_preview": texto[:1000], "analise": analise}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Classificador ─────────────────────────────────────────────────────────────

class ClassificarRequest(BaseModel):
    anthropic_key: str

@app.post("/api/classificar")
def classificar(body: ClassificarRequest):
    try:
        from modules.classificador import classificar_lote, resumo_por_categoria
        dados          = _monitor_dados()
        classificacoes = classificar_lote(dados, body.anthropic_key, max_contratos=12)
        resumo         = resumo_por_categoria(classificacoes)
        return {"classificacoes": classificacoes, "resumo": resumo}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Benchmark ─────────────────────────────────────────────────────────────────

@app.get("/api/benchmark")
def benchmark(x_api_token: str = Header(default="", alias="x-api-token")):
    try:
        dados  = benchmark_municipios(IBGE_ALENQUER, x_api_token)
        resumo = resumo_posicao(IBGE_ALENQUER, dados)
        return {"municipios": dados, "resumo": resumo}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Agendamento ───────────────────────────────────────────────────────────────

@app.get("/api/agendamento/status")
def agendamento_status():
    return status_cron()


class AgendamentoRequest(BaseModel):
    frequencia: str = "semanal"
    email:      Optional[str] = None

@app.post("/api/agendamento/instalar")
def agendamento_instalar(body: AgendamentoRequest):
    linha, msg = instalar_cron(body.frequencia, body.email)
    return {"linha": linha, "mensagem": msg, "sucesso": linha is not None}


@app.post("/api/agendamento/remover")
def agendamento_remover():
    return {"mensagem": remover_cron()}


# ── Inicialização ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=False)
