"""
Análise de contratos com IA (Claude API).
Detecta linguagem vaga, padrões suspeitos e gera parecer em português.
"""
import json
import anthropic

MODELO = "claude-haiku-4-5-20251001"

_client = None


def _get_client(api_key):
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


PROMPT_SISTEMA = """Você é um especialista em transparência pública e combate à corrupção no Brasil.
Analisa contratos públicos municipais em busca de irregularidades e red flags.
Responde sempre em JSON válido, sem texto fora do JSON."""

PROMPT_CONTRATO = """Analise este contrato público do município de Alenquer/PA e retorne um JSON com:

{
  "parecer": "texto de 2-3 frases resumindo a situação",
  "objeto_vago": true/false,
  "justificativa_ausente": true/false,
  "valor_compativel": true/false,
  "linguagem_suspeita": ["lista de trechos suspeitos encontrados"],
  "recomendacao": "o que deve ser investigado",
  "score_ia": 0-100
}

Contrato:
- Empresa: {empresa}
- CNPJ: {cnpj}
- Objeto: {objeto}
- Valor: R$ {valor}
- Modalidade: {modalidade}
- Capital da empresa: R$ {capital}
- Empresa aberta em: {inicio}
- Flags já detectadas: {flags}

Critérios de score_ia:
- Objeto genérico demais (ex: "serviços diversos", "material de consumo"): +30
- Valor muito alto para o porte da empresa: +25
- Modalidade dispensa/emergência sem justificativa clara: +20
- Empresa nova com contrato grande: +15
- Linguagem copia-e-cola idêntica a outros contratos: +10"""


def analisar_contrato_ia(resultado_monitor, api_key):
    """
    Recebe um resultado do monitor e retorna análise da IA.
    """
    c         = resultado_monitor.get("contrato", {})
    cd        = resultado_monitor.get("cnpj_dados", {}) or {}
    flags     = resultado_monitor.get("flags", [])

    prompt = PROMPT_CONTRATO.format(
        empresa   = c.get("nomeContratado", "N/A"),
        cnpj      = c.get("cnpjContratado", "N/A"),
        objeto    = str(c.get("objetoCompra") or c.get("objeto") or "N/A")[:300],
        valor     = f"{float(c.get('valorInicialCompra') or c.get('valor') or 0):,.2f}",
        modalidade= c.get("modalidadeCompra", "N/A"),
        capital   = f"{float(cd.get('capital') or 0):,.0f}" if cd.get("capital") else "?",
        inicio    = cd.get("inicio", "?"),
        flags     = "; ".join(flags[:5]) if flags else "nenhuma",
    )

    client = _get_client(api_key)
    msg = client.messages.create(
        model=MODELO,
        max_tokens=600,
        system=PROMPT_SISTEMA,
        messages=[{"role": "user", "content": prompt}],
    )

    texto = msg.content[0].text.strip()
    # Remover markdown code block se presente
    if texto.startswith("```"):
        texto = texto.split("```")[1]
        if texto.startswith("json"):
            texto = texto[4:]
    return json.loads(texto)


def analisar_lote(resultados_monitor, api_key, apenas_risco=True, max_contratos=10):
    """
    Analisa uma lista de contratos com IA.
    apenas_risco=True analisa só os de score >= 40.
    Retorna lista de {contrato_idx, empresa, analise_ia}.
    """
    lista = resultados_monitor
    if apenas_risco:
        lista = [r for r in lista if r.get("score", 0) >= 40]
    lista = lista[:max_contratos]

    analises = []
    for r in lista:
        empresa = r.get("contrato", {}).get("nomeContratado", "?")
        try:
            analise = analisar_contrato_ia(r, api_key)
            analises.append({
                "empresa":   empresa,
                "score":     r.get("score", 0),
                "analise":   analise,
            })
        except Exception as e:
            analises.append({
                "empresa": empresa,
                "score":   r.get("score", 0),
                "analise": {"parecer": f"Erro na análise: {e}", "score_ia": 0},
            })

    return analises


def resumo_geral_ia(resultados_monitor, historico, api_key):
    """
    Gera um resumo executivo da situação do município para o boletim mensal.
    """
    alto  = sum(1 for r in resultados_monitor if r.get("score", 0) >= 70)
    medio = sum(1 for r in resultados_monitor if 40 <= r.get("score", 0) < 70)

    prompt = f"""Gere um resumo executivo em português (máximo 150 palavras) sobre a situação
de transparência do município de Alenquer/PA com base nesses dados:

- Contratos analisados: {len(resultados_monitor)}
- Alto risco: {alto}
- Médio risco: {medio}
- Histórico dos últimos meses: {json.dumps(historico[-3:], default=str)}

Escreva como um jornalista de dados explicaria para um morador da cidade.
Seja objetivo e aponte se houve melhora ou piora em relação ao mês anterior.
Retorne apenas o texto, sem JSON."""

    client = _get_client(api_key)
    msg = client.messages.create(
        model=MODELO,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()
