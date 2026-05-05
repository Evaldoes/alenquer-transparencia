"""
Rede de empresas relacionadas — detecta vínculos ocultos entre fornecedores.
Usa networkx para construir o grafo e exporta JSON para visualização no browser.
"""
import json
import re
from collections import defaultdict

import networkx as nx


def _limpar_cnpj(v):
    return re.sub(r"\D", "", str(v or ""))


def construir_grafo(resultados_monitor):
    """
    Recebe a lista de resultados do monitor e constrói um grafo onde:
      - Nós = empresas (CNPJ) e pessoas (sócios)
      - Arestas = vínculo (sócio em comum, mesmo endereço, mesma cidade)

    Retorna o grafo networkx e o JSON pronto para vis.js no browser.
    """
    G = nx.Graph()

    # Indexar sócios e endereços para encontrar sobreposições
    socios_por_empresa    = {}   # cnpj → set(nomes de sócios)
    endereco_por_empresa  = {}   # cnpj → endereço normalizado
    empresas              = {}   # cnpj → dados

    for r in resultados_monitor:
        c         = r.get("contrato", {})
        cnpj      = _limpar_cnpj(c.get("cnpjContratado"))
        nome      = str(c.get("nomeContratado") or "?")
        score     = r.get("score", 0)
        cd        = r.get("cnpj_dados") or {}
        socios    = [s["nome"] for s in (cd.get("socios") or [])]

        if not cnpj:
            continue

        empresas[cnpj] = {"nome": nome, "score": score}
        socios_por_empresa[cnpj] = set(socios)

        # Adicionar nó da empresa
        G.add_node(cnpj, tipo="empresa", nome=nome, score=score,
                   capital=cd.get("capital"), inicio=cd.get("inicio"))

        # Adicionar nós dos sócios e arestas empresa→sócio
        for socio in socios:
            if not socio:
                continue
            G.add_node(socio, tipo="pessoa", nome=socio, score=0)
            G.add_edge(cnpj, socio, tipo="socio", label="sócio")

    # Detectar sócios em comum entre empresas diferentes
    cnpjs = list(socios_por_empresa.keys())
    for i in range(len(cnpjs)):
        for j in range(i + 1, len(cnpjs)):
            a, b   = cnpjs[i], cnpjs[j]
            comuns = socios_por_empresa[a] & socios_por_empresa[b]
            for s in comuns:
                if G.has_edge(a, b):
                    G[a][b]["label"] += f" + {s[:20]}"
                else:
                    G.add_edge(a, b, tipo="socio_compartilhado",
                               label=f"sócio: {s[:25]}")

    return G, _para_visjs(G)


def _para_visjs(G):
    """Converte o grafo networkx para o formato JSON do vis.js."""
    nodes = []
    edges = []

    cor_empresa = {
        "alto":  "#fc8181",
        "medio": "#f6ad55",
        "baixo": "#68d391",
        "pessoa": "#90cdf4",
    }

    for node_id, data in G.nodes(data=True):
        tipo  = data.get("tipo", "pessoa")
        score = data.get("score", 0)
        if tipo == "empresa":
            nivel = "alto" if score >= 70 else "medio" if score >= 40 else "baixo"
            cor   = cor_empresa[nivel]
            forma = "box"
            size  = max(20, score // 3)
        else:
            cor   = cor_empresa["pessoa"]
            forma = "ellipse"
            size  = 14

        nodes.append({
            "id":    node_id,
            "label": data.get("nome", node_id)[:30],
            "color": cor,
            "shape": forma,
            "size":  size,
            "title": _tooltip(node_id, data),
        })

    for u, v, data in G.edges(data=True):
        edges.append({
            "from":  u,
            "to":    v,
            "label": data.get("label", ""),
            "color": "#4a5568" if data.get("tipo") == "socio" else "#fc8181",
            "width": 1 if data.get("tipo") == "socio" else 3,
            "dashes": data.get("tipo") == "socio",
        })

    metricas = _metricas(G)

    return {"nodes": nodes, "edges": edges, "metricas": metricas}


def _tooltip(node_id, data):
    if data.get("tipo") == "empresa":
        return (
            f"<b>{data.get('nome', node_id)}</b><br>"
            f"Score: {data.get('score', 0)}/100<br>"
            f"Capital: R$ {data.get('capital') or '?'}<br>"
            f"Abertura: {data.get('inicio') or '?'}"
        )
    return f"<b>{data.get('nome', node_id)}</b><br>Pessoa física / sócio"


def _metricas(G):
    empresas = [n for n, d in G.nodes(data=True) if d.get("tipo") == "empresa"]
    pessoas  = [n for n, d in G.nodes(data=True) if d.get("tipo") != "empresa"]

    # Centralidade: quem conecta mais empresas
    try:
        centralidade = nx.betweenness_centrality(G)
        top_central  = sorted(centralidade.items(), key=lambda x: x[1], reverse=True)[:5]
    except Exception:
        top_central  = []

    # Componentes conectados
    componentes = list(nx.connected_components(G))

    return {
        "total_nos":       G.number_of_nodes(),
        "total_arestas":   G.number_of_edges(),
        "empresas":        len(empresas),
        "pessoas":         len(pessoas),
        "grupos":          len(componentes),
        "mais_conectados": [
            {"id": n, "centralidade": round(c, 3)}
            for n, c in top_central
        ],
    }
