"""
Agregador de notícias — Google News RSS + fontes locais.
"""
import time
import warnings
from datetime import datetime
from email.utils import parsedate_to_datetime

warnings.filterwarnings("ignore", message="urllib3.*doesn't match", category=Warning)
warnings.filterwarnings("ignore", message="chardet.*doesn't match", category=Warning)

import feedparser
import requests

TERMOS_BUSCA = [
    "Alenquer Pará",
    "Alenquer PA licitação",
    "Alenquer PA corrupção",
    "Alenquer PA prefeitura",
    "Alenquer PA contrato",
    "Pará transparência TCM",
]

FONTES_RSS = [
    "https://agenciapara.com.br/feed/",
    "https://g1.globo.com/rss/g1/pa/",
    "https://www.oliberal.com/feed",
]

_TIMEOUT = 8  # segundos por requisição


def _google_news_url(termo):
    encoded = requests.utils.quote(termo)
    return f"https://news.google.com/rss/search?q={encoded}&hl=pt-BR&gl=BR&ceid=BR:pt-419"


def _fetch_feed(url):
    """Busca o conteúdo do feed com timeout e passa para feedparser."""
    try:
        r = requests.get(url, timeout=_TIMEOUT,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; monitor-alenquer/1.0)"})
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception:
        return feedparser.FeedParserDict()


def _parse_data(entry):
    try:
        if hasattr(entry, "published"):
            return parsedate_to_datetime(entry.published).isoformat()
    except Exception:
        pass
    return datetime.now().isoformat()


def _entrada_para_dict(entry, fonte="Google News"):
    return {
        "titulo":  entry.get("title", "").strip(),
        "url":     entry.get("link", ""),
        "resumo":  entry.get("summary", "")[:300].strip(),
        "data":    _parse_data(entry),
        "fonte":   fonte,
    }


def buscar_noticias_google(max_por_termo=5):
    noticias = []
    for termo in TERMOS_BUSCA:
        try:
            feed = _fetch_feed(_google_news_url(termo))
            for entry in feed.entries[:max_por_termo]:
                n = _entrada_para_dict(entry, "Google News")
                if n["titulo"] and n["url"]:
                    noticias.append(n)
        except Exception:
            pass
    return noticias


def buscar_noticias_fontes_locais(max_por_fonte=10):
    noticias = []
    for url in FONTES_RSS:
        try:
            feed = _fetch_feed(url)
            nome = feed.feed.get("title", url)
            for entry in feed.entries[:max_por_fonte]:
                titulo = entry.get("title", "").lower()
                if any(p in titulo for p in ["alenquer", "pará", "licitação",
                                              "corrupção", "prefeitura", "contrato",
                                              "tcm", "ministério público"]):
                    n = _entrada_para_dict(entry, nome)
                    if n["titulo"] and n["url"]:
                        noticias.append(n)
        except Exception:
            pass
    return noticias


def buscar_todas(salvar_no_banco=True):
    """Agrega notícias de todas as fontes e salva no banco."""
    noticias = []
    noticias += buscar_noticias_google()
    noticias += buscar_noticias_fontes_locais()

    # Remover duplicatas por URL
    vistas = set()
    unicas = []
    for n in noticias:
        if n["url"] not in vistas:
            vistas.add(n["url"])
            unicas.append(n)

    unicas.sort(key=lambda x: x["data"], reverse=True)

    if salvar_no_banco:
        from modules.banco import salvar_noticias
        salvar_noticias(unicas)

    return unicas
