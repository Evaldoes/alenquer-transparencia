"""
Detecção de copy-paste entre contratos.
Contratos com texto idêntico de empresas diferentes = forte indício de cartel
ou de direcionamento de licitação.
"""
import re
from difflib import SequenceMatcher
from itertools import combinations


def _normalizar(texto):
    texto = str(texto or "").lower()
    texto = re.sub(r"\s+", " ", texto)
    texto = re.sub(r"[^\w\s]", "", texto)
    return texto.strip()


def _similaridade(a, b):
    return SequenceMatcher(None, a, b).ratio()


def detectar_grupos_similares(contratos, limiar=0.75):
    """
    Compara todos os pares de contratos pelo campo objeto/descrição.
    Retorna grupos de contratos com texto suspeito de copy-paste.

    limiar: 0.0 a 1.0 — 0.75 = 75% de texto igual.
    """
    # Indexar objetos normalizados
    itens = []
    for c in contratos:
        obj = str(c.get("objetoCompra") or c.get("objeto") or "")
        if len(obj) < 30:
            continue
        itens.append({
            "contrato": c,
            "objeto_norm": _normalizar(obj),
            "objeto_orig": obj,
        })

    # Comparar todos os pares
    pares_suspeitos = []
    for a, b in combinations(range(len(itens)), 2):
        sim = _similaridade(itens[a]["objeto_norm"], itens[b]["objeto_norm"])
        if sim >= limiar:
            cnpj_a = str(itens[a]["contrato"].get("cnpjContratado") or "")
            cnpj_b = str(itens[b]["contrato"].get("cnpjContratado") or "")
            # Só é suspeito se forem empresas DIFERENTES
            if cnpj_a != cnpj_b:
                pares_suspeitos.append({
                    "similaridade": round(sim * 100, 1),
                    "contrato_a": itens[a]["contrato"],
                    "contrato_b": itens[b]["contrato"],
                    "objeto_a": itens[a]["objeto_orig"][:120],
                    "objeto_b": itens[b]["objeto_orig"][:120],
                })

    # Ordenar por maior similaridade
    pares_suspeitos.sort(key=lambda x: x["similaridade"], reverse=True)

    # Agrupar em clusters (empresas que aparecem juntas)
    clusters = _agrupar_clusters(pares_suspeitos)

    return pares_suspeitos, clusters


def _agrupar_clusters(pares):
    """
    Une pares em grupos conectados (grafo de componentes).
    Se A~B e B~C, então {A, B, C} formam um cluster.
    """
    grupos = []
    for par in pares:
        cnpj_a = str(par["contrato_a"].get("cnpjContratado") or "")
        cnpj_b = str(par["contrato_b"].get("cnpjContratado") or "")
        nome_a = str(par["contrato_a"].get("nomeContratado") or cnpj_a)
        nome_b = str(par["contrato_b"].get("nomeContratado") or cnpj_b)

        # Procurar grupo existente que contenha um dos CNPJs
        encaixou = False
        for g in grupos:
            if cnpj_a in g["cnpjs"] or cnpj_b in g["cnpjs"]:
                g["cnpjs"].add(cnpj_a)
                g["cnpjs"].add(cnpj_b)
                g["empresas"].add(nome_a[:40])
                g["empresas"].add(nome_b[:40])
                g["pares"].append(par)
                encaixou = True
                break
        if not encaixou:
            grupos.append({
                "cnpjs":    {cnpj_a, cnpj_b},
                "empresas": {nome_a[:40], nome_b[:40]},
                "pares":    [par],
            })

    # Converter sets para listas
    for g in grupos:
        g["cnpjs"]    = list(g["cnpjs"])
        g["empresas"] = list(g["empresas"])
        g["max_sim"]  = max(p["similaridade"] for p in g["pares"])

    return sorted(grupos, key=lambda x: x["max_sim"], reverse=True)


def score_copypaste(contrato, pares_suspeitos):
    """
    Retorna score extra e flags de copy-paste para um contrato específico.
    """
    cnpj   = str(contrato.get("cnpjContratado") or "")
    score  = 0
    flags  = []

    pares_deste = [
        p for p in pares_suspeitos
        if str(p["contrato_a"].get("cnpjContratado") or "") == cnpj
        or str(p["contrato_b"].get("cnpjContratado") or "") == cnpj
    ]

    if not pares_deste:
        return 0, []

    maior_sim = max(p["similaridade"] for p in pares_deste)
    parceiros = set()
    for p in pares_deste:
        cnpj_outro = str(p["contrato_a"].get("cnpjContratado") or "") \
            if str(p["contrato_b"].get("cnpjContratado") or "") == cnpj \
            else str(p["contrato_b"].get("cnpjContratado") or "")
        nome_outro = str(p["contrato_a"].get("nomeContratado") or "") \
            if str(p["contrato_b"].get("nomeContratado") or "") != cnpj \
            else str(p["contrato_b"].get("nomeContratado") or "")
        parceiros.add(nome_outro[:35])

    if maior_sim >= 95:
        score += 40
        flags.append(f"Texto do contrato {maior_sim:.0f}% idêntico ao de {len(parceiros)} outra(s) empresa(s)")
    elif maior_sim >= 85:
        score += 25
        flags.append(f"Texto do contrato {maior_sim:.0f}% similar ao de empresa(s) concorrente(s)")
    elif maior_sim >= 75:
        score += 15
        flags.append(f"Texto do contrato {maior_sim:.0f}% similar (possível copy-paste)")

    return min(score, 40), flags
