"""
Monitor de risco de corrupção — Alenquer/PA

Funcionalidades:
  1. Score de risco por dados de CNPJ
  2. Cruzamento de sócios × servidores públicos
  3. Verificação em listas de sanção (CEIS / CNEP)
  4. Comparativo de preços com a média dos contratos

Uso:
  python monitor.py --token SEU_TOKEN [--email dest@email.com \
    --remetente seu@gmail.com --senha SENHA_APP]
"""

import argparse
import json
import re
import smtplib
import time
from collections import defaultdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from statistics import mean, stdev

import requests

# ── Configuração ──────────────────────────────────────────────────────────────
IBGE_ALENQUER = "1500404"
BASE_URL       = "https://api.portaldatransparencia.gov.br/api-de-dados"
RESULTADO_JSON = Path(__file__).parent / "resultados_monitor.json"

PREPOSICOES = {"de", "da", "do", "das", "dos", "e", "a", "o", "em", "para"}

# ═════════════════════════════════════════════════════════════════════════════
# 1. CLIENTES DE API
# ═════════════════════════════════════════════════════════════════════════════

def _headers(token):
    return {"chave-api-dados": token, "accept": "application/json"}


def _get_transparencia(endpoint, token, params, tentativas=3):
    for t in range(tentativas):
        try:
            r = requests.get(
                f"{BASE_URL}/{endpoint}",
                headers=_headers(token),
                params=params,
                timeout=20,
            )
            if r.status_code == 429:
                time.sleep(10)
                continue
            r.raise_for_status()
            return r.json()
        except requests.HTTPError:
            return None
        except Exception as e:
            if t == tentativas - 1:
                print(f"    [erro] {endpoint}: {e}")
            time.sleep(2)
    return None


def _get_cnpj(cnpj_raw, tentativas=3):
    cnpj = re.sub(r"\D", "", str(cnpj_raw))
    if len(cnpj) != 14:
        return None
    for t in range(tentativas):
        try:
            r = requests.get(
                f"https://publica.cnpj.ws/cnpj/{cnpj}",
                timeout=12,
                headers={"User-Agent": "monitor-transparencia-alenquer/1.0"},
            )
            if r.status_code == 429:
                time.sleep(8)
                continue
            if r.status_code == 200:
                return r.json()
            return None
        except Exception:
            time.sleep(2)
    return None


# ═════════════════════════════════════════════════════════════════════════════
# 2. COLETA DE DADOS
# ═════════════════════════════════════════════════════════════════════════════

def _normalizar_convenio(conv):
    """
    Converte um convênio federal (Alenquer como convenente) para o formato do monitor.

    Esses convênios representam repasses federais PARA a prefeitura;
    a análise avalia a qualidade de execução dos recursos recebidos.
    O 'contratado' é o ministério/órgão federal concedente.
    """
    dim      = conv.get("dimConvenio") or {}
    orgao    = conv.get("orgao") or {}
    tipo_i   = conv.get("tipoInstrumento") or {}
    tipo_desc = tipo_i.get("descricao", "Convênio") if isinstance(tipo_i, dict) else str(tipo_i)
    cnpj_org = re.sub(r"\D", "", str(orgao.get("cnpj") or ""))
    valor    = float(conv.get("valorLiberado") or conv.get("valor") or 0)
    return {
        "nomeContratado":     orgao.get("nome", "N/A"),
        "cnpjContratado":     cnpj_org,
        "objetoCompra":       str(dim.get("objeto") or "")[:300].replace("Objeto:", "").strip(),
        "valorInicialCompra": valor,
        "valorTotal":         float(conv.get("valor") or 0),
        "valorLiberado":      float(conv.get("valorLiberado") or 0),
        "modalidadeCompra":   tipo_desc,
        "situacao":           conv.get("situacao", ""),
        "numeroConvenio":     dim.get("numero", ""),
        "dataInicio":         conv.get("dataInicioVigencia", ""),
        "dataFim":            conv.get("dataFinalVigencia", ""),
        "dataConclusao":      conv.get("dataConclusao") or "",
        "_fonte":             "convenio",
    }


CNPJ_PREFEITURA_ALENQUER = "04838793000173"

def buscar_contratos(token, paginas=5):
    """
    Busca convênios federais firmados pelo Município de Alenquer/PA.

    Parâmetro correto: convenente=MUNICIPIO+DE+ALENQUER
    (o filtro municipio=ALENQUER&uf=PA retorna entidades estaduais com
    sede em cidades diferentes — bug confirmado na API pública).
    """
    resultado = []
    for p in range(1, paginas + 1):
        dados = _get_transparencia(
            "convenios", token,
            {"convenente": "MUNICIPIO DE ALENQUER", "pagina": p},
        )
        if not dados or not isinstance(dados, list):
            break
        for conv in dados:
            normalizado = _normalizar_convenio(conv)
            resultado.append(normalizado)
        print(f"    Página {p}: {len(dados)} convênios")
        time.sleep(0.5)
    return resultado


def buscar_servidores(token, paginas=5):
    """
    Busca servidores federais em Alenquer.

    O endpoint /servidores exige codigoOrgaoExercicio (SIAPE) ou CPF;
    filtragem por município IBGE não é suportada. Retorna lista vazia.
    A funcionalidade de cruzamento sócio × servidor fica disponível
    quando se usa a fonte PNCP (contratos com empresa privada).
    """
    return []


def buscar_socios(cnpj_dados):
    """Extrai lista de sócios do retorno da API de CNPJ."""
    if not cnpj_dados:
        return []
    socios = cnpj_dados.get("socios") or []
    estab  = cnpj_dados.get("estabelecimento") or {}
    socios += estab.get("socios") or []
    return [
        {
            "nome":        str(s.get("nome") or "").upper().strip(),
            "qualificacao": str(s.get("qualificacao_socio") or {}).upper(),
        }
        for s in socios if s.get("nome")
    ]


def verificar_sancoes(cnpj_raw, token):
    """Verifica CEIS e CNEP para o CNPJ informado.

    A API retorna sempre 15 registros aleatórios independente do filtro;
    é necessário filtrar localmente pelo campo pessoa.cnpjFormatado.
    """
    cnpj = re.sub(r"\D", "", str(cnpj_raw))
    ceis_raw = _get_transparencia("ceis", token, {"cnpjCpfSancionado": cnpj, "pagina": 1}) or []
    cnep_raw = _get_transparencia("cnep", token, {"cnpjCpfSancionado": cnpj, "pagina": 1}) or []

    def _match(item):
        pessoa = item.get("pessoa") or {}
        cnpj_resp = re.sub(r"\D", "", str(pessoa.get("cnpjFormatado") or ""))
        return cnpj_resp == cnpj

    time.sleep(0.4)
    return {
        "ceis": [i for i in (ceis_raw if isinstance(ceis_raw, list) else []) if _match(i)],
        "cnep": [i for i in (cnep_raw if isinstance(cnep_raw, list) else []) if _match(i)],
    }


# ═════════════════════════════════════════════════════════════════════════════
# 3. ANÁLISES
# ═════════════════════════════════════════════════════════════════════════════

# ── 3a. Score de risco por CNPJ ───────────────────────────────────────────

def _meses_ativa(data_str):
    try:
        inicio = datetime.strptime(data_str, "%Y-%m-%d")
        return (datetime.now() - inicio).days / 30
    except Exception:
        return 999


def score_cnpj(contrato, cnpj_dados, todos_contratos):
    score = 0
    flags = []
    valor      = float(contrato.get("valorInicialCompra") or contrato.get("valor") or 0)
    modalidade = str(contrato.get("modalidadeCompra") or "").upper()
    cnpj       = re.sub(r"\D", "", str(contrato.get("cnpjContratado") or ""))

    if cnpj_dados:
        meses = _meses_ativa(cnpj_dados.get("data_inicio_atividade", ""))
        if meses < 3:
            score += 30; flags.append("Empresa com menos de 3 meses de existência")
        elif meses < 12:
            score += 15; flags.append("Empresa com menos de 1 ano de existência")

        capital = float(cnpj_dados.get("capital_social") or 0)
        if capital < 10_000:
            score += 20; flags.append(f"Capital social baixo (R$ {capital:,.0f})")

        porte = str(cnpj_dados.get("porte") or "").upper()
        if "01" in porte or "MEI" in porte:
            score += 25; flags.append("Empresa MEI (limite anual R$ 81k)")

        situacao = str(cnpj_dados.get("situacao_cadastral") or "").upper()
        if situacao not in ("02", "ATIVA", "ATIVO"):
            score += 50; flags.append(f"Empresa não ativa (situação: {situacao})")

        estab      = cnpj_dados.get("estabelecimento") or {}
        logradouro = str(estab.get("logradouro") or "").upper()
        if any(p in logradouro for p in ["TRAVESSA", "VIELA", "BECO", "SÍTIO", "CHÁCARA", "RESIDENCIAL"]):
            score += 15; flags.append("Endereço com característica residencial")

    if any(p in modalidade for p in ["DISPENSA", "INEXIGIB"]):
        score += 20; flags.append("Contratação sem licitação (dispensa/inexigibilidade)")
        if valor > 57_500:
            score += 20; flags.append(f"Valor acima do limite de dispensa (R$ {valor:,.0f})")

    if "EMERG" in modalidade:
        score += 25; flags.append("Contrato de emergência")

    # Múltiplos contratos com a mesma empresa
    if cnpj:
        repetidos = [
            c for c in todos_contratos
            if re.sub(r"\D", "", str(c.get("cnpjContratado") or "")) == cnpj
        ]
        if len(repetidos) >= 3:
            score += 15
            flags.append(f"Mesma empresa aparece em {len(repetidos)} contratos")

    return min(score, 100), flags


# ── 3a-bis. Score específico para convênios federais ─────────────────────

def score_convenio(contrato):
    """
    Avalia risco de irregularidade na EXECUÇÃO do convênio federal.
    Retorna (score, flags) adicionais para somar ao score_cnpj.
    """
    score = 0
    flags = []

    situacao = str(contrato.get("situacao") or "").upper()
    if "INADIMPL" in situacao and "SUSPENS" not in situacao:
        score += 50
        flags.append(f"Convênio em situação de INADIMPLÊNCIA ({situacao})")
    elif "INADIMPL" in situacao and "SUSPENS" in situacao:
        score += 25
        flags.append(f"Inadimplência suspensa (monitoramento necessário)")
    elif "REJEITADA" in situacao:
        score += 40
        flags.append("Prestação de contas REJEITADA pelo governo federal")
    elif "RESSALVAS" in situacao:
        score += 15
        flags.append("Prestação de contas aprovada com ressalvas")
    elif "ANULADO" in situacao or situacao in ("RESCINDIDO", "CANCELADO"):
        score += 20
        flags.append(f"Convênio cancelado/anulado ({situacao})")

    objeto = str(contrato.get("objetoCompra") or "").strip()
    if len(objeto) < 15:
        score += 20
        flags.append("Objeto do convênio não informado ou muito vago")

    valor_total    = float(contrato.get("valorTotal") or 0)
    valor_liberado = float(contrato.get("valorLiberado") or 0)
    if valor_total > 50_000 and valor_liberado > 0:
        pct = valor_liberado / valor_total
        if pct < 0.5:
            score += 15
            flags.append(
                f"Apenas {pct*100:.0f}% do valor total liberado "
                f"({_fmt_brl(valor_liberado)} de {_fmt_brl(valor_total)})"
            )

    data_fim = contrato.get("dataFim") or ""
    if data_fim:
        try:
            fim = datetime.strptime(data_fim[:10], "%Y-%m-%d")
            if fim < datetime.now() and situacao in ("EM EXECUÇÃO", "VIGENTE"):
                score += 20
                flags.append(f"Convênio com vigência expirada em {data_fim[:10]} ainda ativo")
        except Exception:
            pass

    return min(score, 60), flags   # cap parcial; somado ao score_cnpj no caller


# ── 3b. Cruzamento de sócios × servidores ────────────────────────────────

def _sobrenomes(nome_completo):
    partes = str(nome_completo).upper().split()
    return {p for p in partes if len(p) > 2 and p not in PREPOSICOES}


def cruzar_socios_servidores(socios, servidores):
    """
    Retorna lista de coincidências suspeitas entre sócios da empresa
    e servidores públicos federais em Alenquer.
    """
    hits = []
    for socio in socios:
        sobrenomes_socio = _sobrenomes(socio["nome"])
        for servidor in servidores:
            nome_srv = str(
                servidor.get("nome") or servidor.get("nomeServidor") or ""
            ).upper()
            sobrenomes_srv = _sobrenomes(nome_srv)
            comuns = sobrenomes_socio & sobrenomes_srv
            if len(comuns) >= 2:
                hits.append({
                    "socio":    socio["nome"],
                    "servidor": nome_srv,
                    "orgao":    servidor.get("orgaoNome") or servidor.get("orgaoServidorExercicio") or "N/A",
                    "comuns":   sorted(comuns),
                })
    return hits


# ── 3c. Comparativo de preços ─────────────────────────────────────────────

def _palavras_chave(texto):
    stop = {"de", "da", "do", "das", "dos", "e", "a", "o", "em", "para",
            "com", "por", "ao", "na", "no", "um", "uma", "contratação",
            "contrato", "aquisição", "serviços", "fornecimento"}
    return {
        w for w in re.sub(r"[^a-záéíóúãõâêîôûç\s]", " ", texto.lower()).split()
        if len(w) > 3 and w not in stop
    }


def comparar_precos(contratos):
    """
    Agrupa contratos por palavras-chave comuns e calcula o desvio
    de cada um em relação à média do grupo.
    """
    grupos = defaultdict(list)
    for c in contratos:
        objeto = str(c.get("objetoCompra") or c.get("objeto") or "")
        valor  = float(c.get("valorInicialCompra") or c.get("valor") or 0)
        if not objeto or valor <= 0:
            continue
        chaves = frozenset(list(_palavras_chave(objeto))[:5])
        if chaves:
            grupos[chaves].append((valor, c))

    resultado = {}
    for chaves, itens in grupos.items():
        if len(itens) < 2:
            continue
        valores = [v for v, _ in itens]
        media   = mean(valores)
        dp      = stdev(valores) if len(valores) > 1 else 0
        for valor, contrato in itens:
            cnpj = str(contrato.get("cnpjContratado") or "")
            if not cnpj:
                continue
            desvio_pct = ((valor - media) / media * 100) if media > 0 else 0
            resultado[cnpj] = resultado.get(cnpj) or []
            resultado[cnpj].append({
                "objeto":     str(contrato.get("objetoCompra") or "")[:70],
                "valor":      valor,
                "media_grupo": media,
                "desvio_pct": desvio_pct,
                "n_grupo":    len(itens),
                "suspeito":   desvio_pct > 50,
            })
    return resultado


# ═════════════════════════════════════════════════════════════════════════════
# 4. MONTAGEM DO RESULTADO FINAL
# ═════════════════════════════════════════════════════════════════════════════

def analisar_contrato(contrato, token, servidores, precos_ref, todos_contratos):
    cnpj      = str(contrato.get("cnpjContratado") or "")
    empresa   = str(contrato.get("nomeContratado") or "?")
    fonte     = contrato.get("_fonte", "")

    # Dados do CNPJ (pula para convênios — o CNPJ é o ministério federal)
    cnpj_dados = None
    if cnpj and fonte != "convenio":
        cnpj_dados = _get_cnpj(cnpj)
        time.sleep(0.4)

    # Score base
    score, flags = score_cnpj(contrato, cnpj_dados, todos_contratos)

    # Score específico para convênios federais
    if fonte == "convenio":
        s_conv, f_conv = score_convenio(contrato)
        score = min(score + s_conv, 100)
        flags.extend(f_conv)

    # Sócios × servidores (apenas para contratos com empresa privada)
    socios   = buscar_socios(cnpj_dados) if cnpj_dados else []
    conflitos = cruzar_socios_servidores(socios, servidores)
    for hit in conflitos:
        score = min(score + 35, 100)
        flags.append(
            f"Possível conflito de interesse: sócio '{hit['socio']}' × "
            f"servidor '{hit['servidor']}' ({hit['orgao']})"
        )

    # Sanções (pula para convênios — ministérios não estão no CEIS)
    sancoes = {"ceis": [], "cnep": []}
    if cnpj and fonte != "convenio":
        sancoes = verificar_sancoes(cnpj, token)
    if sancoes["ceis"]:
        score = min(score + 40, 100)
        flags.append(f"Empresa no CEIS (impedida de contratar com o governo): {len(sancoes['ceis'])} registro(s)")
    if sancoes["cnep"]:
        score = min(score + 40, 100)
        flags.append(f"Empresa no CNEP (punição ativa): {len(sancoes['cnep'])} registro(s)")

    # Desvio de preço
    cnpj_limpo = re.sub(r"\D", "", cnpj)
    for ref in (precos_ref.get(cnpj_limpo) or []):
        if ref["suspeito"]:
            score = min(score + 20, 100)
            flags.append(
                f"Preço {ref['desvio_pct']:.0f}% acima da média "
                f"({_fmt_brl(ref['valor'])} vs média {_fmt_brl(ref['media_grupo'])} "
                f"em {ref['n_grupo']} contratos similares)"
            )

    nivel, icone = _nivel(score)

    return {
        "score":       score,
        "nivel":       nivel,
        "icone":       icone,
        "flags":       flags,
        "conflitos":   conflitos,
        "sancoes":     sancoes,
        "contrato":    contrato,
        "cnpj_dados": {
            "capital":   float(cnpj_dados.get("capital_social") or 0) if cnpj_dados else None,
            "inicio":    cnpj_dados.get("data_inicio_atividade") if cnpj_dados else None,
            "porte":     str(cnpj_dados.get("porte") or "") if cnpj_dados else None,
            "situacao":  str(cnpj_dados.get("situacao_cadastral") or "") if cnpj_dados else None,
            "socios":    socios,
        },
        "analisado_em": datetime.now().isoformat(),
    }


def _nivel(score):
    if score >= 70: return "ALTO",  "🔴"
    if score >= 40: return "MÉDIO", "🟡"
    return "BAIXO", "🟢"


def _fmt_brl(v):
    return f"R$ {float(v):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ═════════════════════════════════════════════════════════════════════════════
# 5. RELATÓRIO E ALERTAS
# ═════════════════════════════════════════════════════════════════════════════

def gerar_relatorio(resultados):
    alto  = [r for r in resultados if r["score"] >= 70]
    medio = [r for r in resultados if 40 <= r["score"] < 70]

    linhas = [
        "╔══════════════════════════════════════════════════════════╗",
        "║   MONITOR DE RISCO — Alenquer / PA                      ║",
        "╚══════════════════════════════════════════════════════════╝",
        f"  Gerado em : {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        f"  Analisados: {len(resultados)} contratos",
        f"  🔴 Alto risco : {len(alto)}",
        f"  🟡 Médio risco: {medio and len(medio) or 0}",
        "",
    ]

    for titulo, lista in [("🔴 ALTO RISCO", alto), ("🟡 MÉDIO RISCO", medio)]:
        if not lista:
            continue
        linhas += ["─" * 60, titulo, "─" * 60]
        for r in sorted(lista, key=lambda x: x["score"], reverse=True):
            c     = r["contrato"]
            valor = float(c.get("valorInicialCompra") or c.get("valor") or 0)
            linhas += [
                f"\n  Score {r['score']}/100  {r['icone']}",
                f"  Empresa   : {c.get('nomeContratado', 'N/A')}",
                f"  CNPJ      : {c.get('cnpjContratado', 'N/A')}",
                f"  Objeto    : {str(c.get('objetoCompra') or '')[:65]}",
                f"  Valor     : {_fmt_brl(valor)}",
                f"  Modalidade: {c.get('modalidadeCompra', 'N/A')}",
                "  Flags:",
                *[f"    ⚠  {f}" for f in r["flags"]],
            ]
            if r.get("conflitos"):
                linhas.append("  Conflitos de interesse:")
                for hit in r["conflitos"]:
                    linhas.append(f"    👤 {hit['socio']} ↔ {hit['servidor']} ({hit['orgao']})")
            if r["sancoes"]["ceis"]:
                linhas.append(f"  🚫 CEIS: {len(r['sancoes']['ceis'])} sanção(ões) ativa(s)")
            if r["sancoes"]["cnep"]:
                linhas.append(f"  🚫 CNEP: {len(r['sancoes']['cnep'])} punição(ões) ativa(s)")

    return "\n".join(linhas)


def enviar_email(relatorio, destino, remetente, senha):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"⚠️ Monitor Transparência Alenquer — {datetime.now().strftime('%d/%m/%Y')}"
    msg["From"]    = remetente
    msg["To"]      = destino
    msg.attach(MIMEText(relatorio, "plain", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(remetente, senha)
        smtp.sendmail(remetente, destino, msg.as_string())
    print(f"  ✅ E-mail enviado para {destino}")


# ═════════════════════════════════════════════════════════════════════════════
# 6. MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Monitor de risco — Alenquer/PA")
    parser.add_argument("--token",     required=True)
    parser.add_argument("--email",     default=None)
    parser.add_argument("--remetente", default=None)
    parser.add_argument("--senha",     default=None)
    parser.add_argument("--paginas",   type=int, default=3)
    args = parser.parse_args()

    print("\n🔍 [1/4] Buscando contratos...")
    contratos = buscar_contratos(args.token, args.paginas)
    print(f"        {len(contratos)} contratos encontrados")

    print("\n👥 [2/4] Buscando servidores federais em Alenquer...")
    servidores = buscar_servidores(args.token)
    print(f"        {len(servidores)} servidores encontrados")

    print("\n💰 [3/4] Calculando referências de preço...")
    precos_ref = comparar_precos(contratos)
    print(f"        {sum(len(v) for v in precos_ref.values())} comparações geradas")

    print("\n🔎 [4/4] Analisando cada contrato...\n")
    resultados = []
    for i, contrato in enumerate(contratos, 1):
        empresa = str(contrato.get("nomeContratado") or "?")[:45]
        print(f"  [{i:02d}/{len(contratos)}] {empresa}")
        resultado = analisar_contrato(contrato, args.token, servidores, precos_ref, contratos)
        resultados.append(resultado)
        print(f"         {resultado['icone']} Score: {resultado['score']}/100"
              + (f"  — {resultado['flags'][0][:55]}" if resultado['flags'] else ""))
        time.sleep(0.3)

    # Salvar
    RESULTADO_JSON.write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\n💾 Resultados salvos em {RESULTADO_JSON.name}")

    # Relatório
    relatorio = gerar_relatorio(resultados)
    print("\n" + relatorio)

    # E-mail
    if args.email and args.remetente and args.senha:
        tem_risco = any(r["score"] >= 40 for r in resultados)
        if tem_risco:
            print(f"\n📧 Enviando alerta para {args.email}...")
            enviar_email(relatorio, args.email, args.remetente, args.senha)
        else:
            print("\n✅ Sem riscos médios/altos. E-mail não enviado.")

    alto  = sum(1 for r in resultados if r["score"] >= 70)
    medio = sum(1 for r in resultados if 40 <= r["score"] < 70)
    print(f"\n📊 Resumo: {alto} alto | {medio} médio | {len(contratos)} analisados\n")


if __name__ == "__main__":
    main()
