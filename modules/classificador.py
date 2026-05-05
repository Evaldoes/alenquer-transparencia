"""
Classificação automática de irregularidades com IA.
Categoriza cada red flag em tipo específico de irregularidade.
"""
import json
import anthropic

MODELO = "claude-haiku-4-5-20251001"

CATEGORIAS = {
    "superfaturamento":    "Preço pago muito acima do mercado",
    "direcionamento":      "Licitação moldada para beneficiar empresa específica",
    "empresa_fantasma":    "Empresa sem estrutura real para executar o contrato",
    "cartel":              "Combinação entre concorrentes para fraudar licitação",
    "nepotismo":           "Favorecimento de pessoa com vínculo familiar/pessoal",
    "lavagem":             "Contrato usado para lavar dinheiro",
    "fracionamento":       "Divisão artificial para fugir da licitação obrigatória",
    "dispensa_indevida":   "Dispensa de licitação sem amparo legal",
    "sem_irregularidade":  "Nenhuma irregularidade identificada",
}

PROMPT = """Você é especialista em controles internos e auditoria pública no Brasil.
Analise os dados abaixo e classifique a irregularidade principal em UMA das categorias:

{categorias}

Dados do contrato:
- Empresa: {empresa}
- Objeto: {objeto}
- Valor: {valor}
- Modalidade: {modalidade}
- Score de risco: {score}/100
- Flags identificadas: {flags}

Retorne APENAS um JSON válido:
{{
  "categoria": "nome_da_categoria",
  "confianca": 0-100,
  "justificativa": "uma frase explicando por que essa categoria",
  "evidencias": ["evidência 1", "evidência 2"]
}}"""


def classificar_contrato(resultado_monitor, api_key):
    """Classifica a irregularidade principal de um contrato."""
    c      = resultado_monitor.get("contrato", {})
    score  = resultado_monitor.get("score", 0)
    flags  = resultado_monitor.get("flags", [])
    valor  = float(c.get("valorInicialCompra") or c.get("valor") or 0)

    prompt = PROMPT.format(
        categorias = "\n".join(f"- {k}: {v}" for k, v in CATEGORIAS.items()),
        empresa    = c.get("nomeContratado", "N/A"),
        objeto     = str(c.get("objetoCompra") or "")[:200],
        valor      = f"R$ {valor:,.2f}",
        modalidade = c.get("modalidadeCompra", "N/A"),
        score      = score,
        flags      = "; ".join(flags[:4]) or "nenhuma",
    )

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=MODELO, max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = msg.content[0].text.strip()
    if texto.startswith("```"):
        texto = texto.split("```")[1]
        if texto.startswith("json"):
            texto = texto[4:]
    return json.loads(texto)


def classificar_lote(resultados_monitor, api_key, apenas_risco=True, max_contratos=15):
    """Classifica irregularidades em lote."""
    lista = resultados_monitor
    if apenas_risco:
        lista = [r for r in lista if r.get("score", 0) >= 40]
    lista = lista[:max_contratos]

    resultados = []
    for r in lista:
        try:
            classificacao = classificar_contrato(r, api_key)
            resultados.append({
                "empresa":        r.get("contrato", {}).get("nomeContratado", ""),
                "score":          r.get("score", 0),
                "classificacao":  classificacao,
            })
        except Exception as e:
            resultados.append({
                "empresa":       r.get("contrato", {}).get("nomeContratado", ""),
                "score":         r.get("score", 0),
                "classificacao": {"categoria": "erro", "justificativa": str(e)},
            })
    return resultados


def resumo_por_categoria(classificacoes):
    """Agrupa classificações por tipo de irregularidade."""
    contagem = {}
    for c in classificacoes:
        cat = c.get("classificacao", {}).get("categoria", "sem_irregularidade")
        contagem[cat] = contagem.get(cat, 0) + 1

    return [
        {"categoria": k, "descricao": CATEGORIAS.get(k, k), "total": v}
        for k, v in sorted(contagem.items(), key=lambda x: -x[1])
    ]
