"""
Diário Oficial do Estado do Pará — monitoramento de publicações sobre Alenquer.
Fonte: IOEPA (Imprensa Oficial do Estado do Pará) — ioepa.com.br
       e DOE federal via imprensanacional.gov.br (DOU)
"""
import re
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

TERMOS_BUSCA = [
    "Alenquer",
    "Prefeitura Municipal de Alenquer",
]

TERMOS_INTERESSE = [
    "licitação", "contrato", "dispensa", "inexigibilidade",
    "nomeação", "exoneração", "afastamento", "cargo comissionado",
    "processo administrativo", "irregularidade", "rescisão",
    "convênio", "repasse",
]

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; monitor-alenquer/1.0)"
})


# ── IOEPA ─────────────────────────────────────────────────────────────────────

def _buscar_ioepa(termo, pagina=1):
    """Busca no portal da Imprensa Oficial do Pará."""
    try:
        r = _SESSION.get(
            "https://www.ioepa.com.br/pages/search.php",
            params={"q": termo, "pagina": pagina},
            timeout=15,
        )
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        resultados = []
        for item in soup.select(".resultado-busca, .search-result, article"):
            titulo = item.select_one("h2, h3, .titulo, a")
            data   = item.select_one(".data, .date, time")
            link   = item.select_one("a")
            texto  = item.get_text(" ", strip=True)[:300]
            if titulo:
                resultados.append({
                    "titulo":  titulo.get_text(strip=True)[:120],
                    "data":    data.get_text(strip=True) if data else "",
                    "url":     link["href"] if link and link.get("href") else "",
                    "resumo":  texto,
                    "fonte":   "IOEPA",
                })
        return resultados
    except Exception:
        return []


# ── DOU (Diário Oficial da União) via API ──────────────────────────────────────

def _buscar_dou(termo, dias=30):
    """
    Busca no DOU via API da Imprensa Nacional.
    API pública: queridodiario.ok.org.br (dados abertos do DOU/DOEs)
    """
    hoje   = datetime.now()
    inicio = hoje - timedelta(days=dias)
    try:
        r = _SESSION.get(
            "https://queridodiario.ok.org.br/api/gazettes",
            params={
                "territory_id": "1500404",
                "querystring":  termo,
                "published_since": inicio.strftime("%Y-%m-%d"),
                "published_until": hoje.strftime("%Y-%m-%d"),
                "page_size":       20,
                "excerpt_size":    400,
            },
            timeout=20,
        )
        if not r.ok:
            return []
        data = r.json()
        gazettes = data.get("gazettes") or []
        resultados = []
        for g in gazettes:
            for excerpto in g.get("excerpts") or [g.get("excerpt", "")]:
                resultados.append({
                    "titulo":  f"Diário Oficial — {g.get('date', '')}",
                    "data":    g.get("date", ""),
                    "url":     g.get("url", ""),
                    "resumo":  str(excerpto)[:400],
                    "fonte":   "Querido Diário / DOE-PA",
                    "edition": g.get("edition", ""),
                })
        return resultados
    except Exception:
        return []


# ── Classificação de relevância ───────────────────────────────────────────────

def _relevancia(publicacao):
    """Classifica a relevância da publicação para monitoramento."""
    texto = (publicacao.get("titulo", "") + " " + publicacao.get("resumo", "")).lower()
    pontos = 0
    achou  = []
    for termo in TERMOS_INTERESSE:
        if termo.lower() in texto:
            pontos += 10
            achou.append(termo)
    publicacao["relevancia"]      = pontos
    publicacao["termos_achados"]  = achou
    publicacao["alta_relevancia"] = pontos >= 20
    return publicacao


def buscar_publicacoes(dias=30, salvar_no_banco=True):
    """
    Agrega publicações do DOE-PA e DOU sobre Alenquer.
    Classifica por relevância e salva no banco.
    """
    todas = []

    # Querido Diário (cobre DOEs estaduais e municipais)
    for termo in TERMOS_BUSCA:
        resultados = _buscar_dou(termo, dias)
        todas.extend(resultados)
        time.sleep(0.5)

    # IOEPA direto
    for termo in TERMOS_BUSCA[:1]:
        resultados = _buscar_ioepa(termo)
        todas.extend(resultados)
        time.sleep(0.5)

    # Remover duplicatas por URL
    vistas = set()
    unicas = []
    for p in todas:
        url = p.get("url", "")
        if url and url not in vistas:
            vistas.add(url)
            unicas.append(_relevancia(p))
        elif not url:
            unicas.append(_relevancia(p))

    # Ordenar por relevância e data
    unicas.sort(key=lambda x: (x.get("alta_relevancia", False),
                                x.get("relevancia", 0),
                                x.get("data", "")), reverse=True)

    if salvar_no_banco and unicas:
        from modules.banco import salvar_noticias
        noticias_fmt = [{
            "titulo":  p["titulo"],
            "url":     p.get("url") or f"doe-{i}",
            "resumo":  p.get("resumo", ""),
            "data":    p.get("data") or datetime.now().isoformat(),
            "fonte":   p.get("fonte", "DOE-PA"),
        } for i, p in enumerate(unicas)]
        salvar_noticias(noticias_fmt)

    return unicas


def cruzar_com_servidores(publicacoes, servidores):
    """
    Cruza publicações do DOE com nomes de servidores —
    detecta nomeações, exonerações ou penalidades recentes.
    """
    alertas = []
    nomes_servidores = {
        str(s.get("nome") or s.get("nomeServidor") or "").upper()
        for s in servidores
        if s.get("nome") or s.get("nomeServidor")
    }

    for pub in publicacoes:
        texto = (pub.get("resumo", "") + " " + pub.get("titulo", "")).upper()
        for nome in nomes_servidores:
            partes = [p for p in nome.split() if len(p) > 3]
            if len(partes) >= 2 and all(p in texto for p in partes[:2]):
                alertas.append({
                    "servidor":   nome,
                    "publicacao": pub,
                    "tipo":       _tipo_publicacao(texto),
                })
    return alertas


def _tipo_publicacao(texto):
    texto = texto.upper()
    if "NOMEAÇÃO" in texto or "NOMEIA" in texto:     return "nomeação"
    if "EXONERAÇÃO" in texto or "EXONERA" in texto:  return "exoneração"
    if "SUSPENSÃO" in texto or "PENALIDADE" in texto: return "penalidade"
    if "LICITAÇÃO" in texto:                          return "licitação"
    if "CONTRATO" in texto:                           return "contrato"
    return "publicação"
