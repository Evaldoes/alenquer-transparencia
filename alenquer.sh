#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Alenquer Transparência — menu principal
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$DIR/.env"
VENV="$DIR/venv/bin/python"

# ── Cores ─────────────────────────────────────────────────────────────────────
VERDE="\033[0;32m"
AMARELO="\033[1;33m"
VERMELHO="\033[0;31m"
AZUL="\033[0;34m"
CINZA="\033[0;90m"
NEGRITO="\033[1m"
RESET="\033[0m"

# ── Helpers ───────────────────────────────────────────────────────────────────
ok()   { echo -e "${VERDE}✔ $*${RESET}"; }
info() { echo -e "${AZUL}→ $*${RESET}"; }
warn() { echo -e "${AMARELO}⚠ $*${RESET}"; }
erro() { echo -e "${VERMELHO}✘ $*${RESET}"; }

carregar_env() {
  [[ -f "$ENV_FILE" ]] && source "$ENV_FILE" || true
  PORTAL_TOKEN="${PORTAL_TOKEN:-}"
  ANTHROPIC_KEY="${ANTHROPIC_KEY:-}"
  EMAIL_DESTINO="${EMAIL_DESTINO:-}"
  EMAIL_REMETENTE="${EMAIL_REMETENTE:-}"
  EMAIL_SENHA="${EMAIL_SENHA:-}"
  WHATSAPP_NUMERO="${WHATSAPP_NUMERO:-}"
}

salvar_env() {
  cat > "$ENV_FILE" <<EOF
PORTAL_TOKEN="$PORTAL_TOKEN"
ANTHROPIC_KEY="$ANTHROPIC_KEY"
EMAIL_DESTINO="$EMAIL_DESTINO"
EMAIL_REMETENTE="$EMAIL_REMETENTE"
EMAIL_SENHA="$EMAIL_SENHA"
WHATSAPP_NUMERO="$WHATSAPP_NUMERO"
EOF
  chmod 600 "$ENV_FILE"
  ok "Configurações salvas em .env"
}

checar_token() {
  if [[ -z "$PORTAL_TOKEN" ]]; then
    warn "Token do Portal da Transparência não configurado."
    echo -e "${CINZA}Cadastre seu e-mail em portaldatransparencia.gov.br/api-de-dados${RESET}"
    read -rp "Cole o token aqui: " PORTAL_TOKEN
    salvar_env
  fi
}

checar_venv() {
  if [[ ! -f "$VENV" ]]; then
    info "Criando ambiente virtual Python..."
    python3 -m venv "$DIR/venv"
    "$DIR/venv/bin/pip" install -r "$DIR/requirements.txt" -q
    ok "Dependências instaladas."
  fi
}

cabecalho() {
  clear
  echo -e "${VERDE}${NEGRITO}"
  echo "  ╔══════════════════════════════════════════════════════╗"
  echo "  ║       📊  Alenquer Transparência — Pará/BR           ║"
  echo "  ╚══════════════════════════════════════════════════════╝"
  echo -e "${RESET}"
  if [[ -n "$PORTAL_TOKEN" ]]; then
    echo -e "  Token: ${VERDE}configurado${RESET}  ${CINZA}(${PORTAL_TOKEN:0:8}...)${RESET}"
  else
    echo -e "  Token: ${VERMELHO}não configurado${RESET}"
  fi
  echo ""
}

# ── Ações ─────────────────────────────────────────────────────────────────────

configurar() {
  cabecalho
  echo -e "${NEGRITO}  Configuração${RESET}\n"

  read -rp "  Token do Portal da Transparência (Enter para manter): " t
  [[ -n "$t" ]] && PORTAL_TOKEN="$t"

  read -rp "  Chave da Anthropic/Claude (Enter para manter): " t
  [[ -n "$t" ]] && ANTHROPIC_KEY="$t"

  read -rp "  E-mail para alertas (Enter para manter): " t
  [[ -n "$t" ]] && EMAIL_DESTINO="$t"

  read -rp "  Gmail remetente dos alertas (Enter para manter): " t
  [[ -n "$t" ]] && EMAIL_REMETENTE="$t"

  read -rsp "  Senha de app do Gmail (Enter para manter): " t
  [[ -n "$t" ]] && EMAIL_SENHA="$t"
  echo ""

  read -rp "  Número WhatsApp para alertas, ex: 5593999991234 (Enter para manter): " t
  [[ -n "$t" ]] && WHATSAPP_NUMERO="$t"

  salvar_env
  read -rp "  Pressione Enter para continuar..."
}

rodar_monitor() {
  checar_token
  cabecalho
  echo -e "${NEGRITO}  Monitor de Risco${RESET}\n"

  read -rp "  Quantas páginas de contratos buscar? [3]: " pag
  pag="${pag:-3}"

  ARGS="--token $PORTAL_TOKEN --paginas $pag"

  if [[ -n "$EMAIL_DESTINO" && -n "$EMAIL_REMETENTE" && -n "$EMAIL_SENHA" ]]; then
    ARGS="$ARGS --email $EMAIL_DESTINO --remetente $EMAIL_REMETENTE --senha $EMAIL_SENHA"
    info "Alertas por e-mail habilitados → $EMAIL_DESTINO"
  fi

  echo ""
  cd "$DIR"
  "$VENV" monitor.py $ARGS
  echo ""
  ok "Análise concluída. Abra o dashboard para visualizar."
  read -rp "  Pressione Enter para continuar..."
}

rodar_dashboard() {
  cabecalho
  info "Verificando porta 5000..."
  if pkill -f "uvicorn.*app:app" 2>/dev/null; then
    sleep 1
    ok "Processo anterior encerrado."
  fi
  info "Iniciando dashboard em http://localhost:5000 ..."
  echo -e "${CINZA}  Pressione Ctrl+C para parar.${RESET}\n"
  cd "$DIR"
  PYTHONWARNINGS=ignore "$VENV" -m uvicorn app:app --host 0.0.0.0 --port 5000
}

atualizar_noticias() {
  cabecalho
  info "Buscando notícias sobre Alenquer e transparência no Pará..."
  cd "$DIR"
  "$VENV" - <<'PYEOF'
from modules.noticias import buscar_todas
noticias = buscar_todas(salvar_no_banco=True)
print(f"  {len(noticias)} notícias encontradas e salvas.")
PYEOF
  read -rp "  Pressione Enter para continuar..."
}

gerar_pdf() {
  checar_token
  cabecalho
  info "Gerando boletim mensal em PDF..."
  cd "$DIR"
  "$VENV" - <<PYEOF
import json, re, time, requests
from pathlib import Path
from datetime import datetime, timedelta
from modules.pdf_report import gerar_pdf

resultado_json = Path("resultados_monitor.json")
monitor = json.loads(resultado_json.read_text()) if resultado_json.exists() else []

BASE = "https://api.portaldatransparencia.gov.br/api-de-dados"
token = "$PORTAL_TOKEN"
headers = {"chave-api-dados": token, "accept": "application/json"}
ibge = "1500404"

def safe_get(endpoint, params):
    try:
        r = requests.get(f"{BASE}/{endpoint}", headers=headers, params=params, timeout=12)
        return r.json() if r.ok else []
    except:
        return []

# ── Bolsa Família: endpoint novo, resposta é lista ────────────────────────
bf = []
for i in range(12):
    d = datetime.now() - timedelta(days=30*i)
    data = safe_get("novo-bolsa-familia-por-municipio",
                    {"mesAno": d.strftime("%Y%m"), "codigoIbge": ibge, "pagina": 1})
    if isinstance(data, list) and data:
        item = data[0]
        bf.append({
            "mesAno":        d.strftime("%b/%Y"),
            "beneficiarios": item.get("quantidadeBeneficiados", 0),
            "valor":         item.get("valor", 0),
        })
    time.sleep(0.3)
bf.reverse()

# ── Transferências: usa convênios (único endpoint que funciona sem permissão especial) ──
convs = []
for p in range(1, 4):
    dados = safe_get("convenios", {"convenente": "MUNICIPIO DE ALENQUER", "pagina": p})
    if not isinstance(dados, list) or not dados:
        break
    convs.extend(dados)
    time.sleep(0.3)

transf = []
for conv in convs[:15]:
    dim  = conv.get("dimConvenio") or {}
    org  = conv.get("orgao") or {}
    tipo = conv.get("tipoInstrumento") or {}
    transf.append({
        "acao":   (org.get("sigla") or org.get("nome") or "N/A")[:50],
        "nomeFuncao": str(dim.get("objeto") or "")[:60],
        "valor":  float(conv.get("valorLiberado") or conv.get("valor") or 0),
    })

# ── Despesas: top convênios por valor (proxy para despesas federais) ───────
desp = sorted(
    [{"nomeFavorecido": (conv.get("orgao") or {}).get("nome","N/A")[:55],
      "valorLiquido": float(conv.get("valorLiberado") or conv.get("valor") or 0)}
     for conv in convs],
    key=lambda x: x["valorLiquido"], reverse=True
)[:15]

caminho = gerar_pdf(bf, transf, desp, monitor)
print(f"  PDF gerado: {caminho}")
PYEOF
  read -rp "  Pressione Enter para continuar..."
}

comparar_municipios() {
  checar_token
  cabecalho
  info "Comparando Alenquer com municípios vizinhos do Pará..."
  cd "$DIR"
  "$VENV" - <<PYEOF
from modules.municipios import comparar_municipios, MUNICIPIOS_PA
resultado = comparar_municipios("$PORTAL_TOKEN")

print(f"\n  {'#':<3} {'Município':<20} {'Score':>7} {'Alto':>6} {'Contratos':>10}")
print("  " + "─"*50)
for i, m in enumerate(resultado, 1):
    dest = " ⭐" if m["ibge"] == "1500404" else ""
    print(f"  {i:<3} {m['nome']:<20}{dest} {m['score_medio']:>7.1f} {m['alto_risco']:>6} {m['contratos']:>10}")
print()
PYEOF
  read -rp "  Pressione Enter para continuar..."
}

rodar_tudo() {
  checar_token
  cabecalho
  echo -e "${NEGRITO}  Execução completa${RESET}"
  echo -e "${CINZA}  Monitor → Notícias → PDF → Dashboard${RESET}\n"

  info "1/4 Rodando monitor de risco..."
  cd "$DIR"
  ARGS="--token $PORTAL_TOKEN"
  [[ -n "$EMAIL_DESTINO" && -n "$EMAIL_REMETENTE" && -n "$EMAIL_SENHA" ]] && \
    ARGS="$ARGS --email $EMAIL_DESTINO --remetente $EMAIL_REMETENTE --senha $EMAIL_SENHA"
  "$VENV" monitor.py $ARGS

  info "2/4 Atualizando notícias..."
  "$VENV" - <<'PYEOF'
from modules.noticias import buscar_todas
n = buscar_todas(salvar_no_banco=True)
print(f"  {len(n)} notícias salvas.")
PYEOF

  info "3/4 Gerando PDF..."
  gerar_pdf 2>/dev/null || warn "PDF: carregue os dados de transferências primeiro no dashboard."

  info "4/4 Iniciando dashboard..."
  echo -e "${VERDE}  Acesse: http://localhost:5000${RESET}"
  echo -e "${CINZA}  Ctrl+C para parar.${RESET}\n"
  pkill -f "uvicorn.*app:app" 2>/dev/null && sleep 1 || true
  PYTHONWARNINGS=ignore "$VENV" -m uvicorn app:app --host 0.0.0.0 --port 5000
}

atualizar_noticias_doe() {
  cabecalho
  info "Buscando notícias e publicações do Diário Oficial..."
  cd "$DIR"
  "$VENV" - <<'PYEOF'
from modules.noticias import buscar_todas
from modules.diario_oficial import buscar_publicacoes
n = buscar_todas(salvar_no_banco=True)
d = buscar_publicacoes(dias=30, salvar_no_banco=True)
print(f"  {len(n)} notícias salvas.")
print(f"  {len(d)} publicações do DOE salvas.")
PYEOF
  read -rp "  Pressione Enter para continuar..."
}

exportar_excel() {
  checar_token
  cabecalho
  info "Gerando planilha Excel completa..."
  cd "$DIR"
  # Chama a rota do Flask via curl
  if ! command -v curl &>/dev/null; then
    warn "curl não encontrado. Abra http://localhost:5000 e use a aba Boletim → Exportar Excel."
    read -rp "  Pressione Enter para continuar..."
    return
  fi
  # Inicia Flask em background, exporta, encerra
  pkill -f "uvicorn.*app:app" 2>/dev/null && sleep 1 || true
  PYTHONWARNINGS=ignore "$VENV" -m uvicorn app:app --host 0.0.0.0 --port 5000 &
  FLASK_PID=$!
  sleep 2
  curl -s "http://localhost:5000/api/exportar/excel" \
    -o "$DIR/dados/alenquer_transparencia.xlsx"
  kill $FLASK_PID 2>/dev/null || true
  ok "Planilha salva em dados/alenquer_transparencia.xlsx"
  read -rp "  Pressione Enter para continuar..."
}

detectar_copypaste() {
  cabecalho
  info "Analisando copy-paste entre contratos..."
  cd "$DIR"
  "$VENV" - <<'PYEOF'
import json
from pathlib import Path
from modules.copypaste import detectar_grupos_similares

resultado_json = Path("resultados_monitor.json")
if not resultado_json.exists():
    print("  Execute o monitor primeiro (opção 2).")
else:
    dados = json.loads(resultado_json.read_text())
    contratos = [r.get("contrato", {}) for r in dados]
    pares, clusters = detectar_grupos_similares(contratos)
    print(f"\n  {len(pares)} pares suspeitos | {len(clusters)} grupos (clusters)\n")
    for p in pares[:5]:
        print(f"  {p['similaridade']}% similar")
        print(f"    A: {p['contrato_a'].get('nomeContratado','?')[:45]}")
        print(f"    B: {p['contrato_b'].get('nomeContratado','?')[:45]}")
        print()
PYEOF
  read -rp "  Pressione Enter para continuar..."
}

buscar_pncp() {
  cabecalho
  info "Buscando contratações no PNCP (Portal Nacional)..."
  cd "$DIR"
  "$VENV" - <<'PYEOF'
from modules.pncp import buscar_contratacoes, analisar_pncp
contratos = buscar_contratacoes(dias=60)
analise   = analisar_pncp(contratos)
print(f"\n  Total: {analise['total']} contratações")
print(f"  Valor: R$ {analise['valor_total']:,.0f}")
print(f"  Sem licitação: {analise['dispensas']}")
print(f"\n  Modalidades:")
for mod, qtd in sorted(analise['por_modalidade'].items(), key=lambda x: -x[1]):
    print(f"    {mod[:50]}: {qtd}")
print()
PYEOF
  read -rp "  Pressione Enter para continuar..."
}

rodar_tse() {
  checar_token
  cabecalho
  info "Cruzando doadores do TSE com contratados pelo município..."
  cd "$DIR"
  "$VENV" - <<PYEOF
import json
from pathlib import Path
from modules.tse import cruzar_doadores

resultado_json = Path("resultados_monitor.json")
if not resultado_json.exists():
    print("  Execute o monitor primeiro (opção 2).")
else:
    dados = json.loads(resultado_json.read_text())
    contratos = [r.get("contrato", {}) for r in dados]
    pares = cruzar_doadores("$PORTAL_TOKEN", contratos)
    print(f"\n  {len(pares)} pares encontrados\n")
    for p in pares[:8]:
        roi = p.get('roi', 0)
        print(f"  ROI {roi:.1f}x  |  {p.get('empresa','?')[:40]}")
        print(f"     Doação: R\$ {p.get('valor_doacao',0):,.0f}  →  Contrato: R\$ {p.get('valor_contrato',0):,.0f}")
    print()
PYEOF
  read -rp "  Pressione Enter para continuar..."
}

rodar_benchmark() {
  checar_token
  cabecalho
  info "Comparando Alenquer com municípios paraenses similares..."
  cd "$DIR"
  "$VENV" - <<PYEOF
from modules.benchmark import benchmark_municipios, resumo_posicao, MUNICIPIOS_BENCHMARK
ibge = "1500404"
bench = benchmark_municipios(ibge, "$PORTAL_TOKEN")
resumo = resumo_posicao(ibge, bench)
print(f"\n  Alenquer: {resumo.get('posicao_transf','?')}° de {resumo.get('total_municipios','?')} municípios")
print(f"  {resumo.get('interpretacao','')}\n")
print(f"  {'#':<3} {'Município':<22} {'Transferências':>18} {'BF Beneficiários':>17}")
print("  " + "─"*65)
for i, m in enumerate(bench, 1):
    dest = " ⭐" if m["ibge"] == ibge else ""
    print(f"  {i:<3} {m['nome']:<22}{dest} {m['transf_total']:>18,.0f} {m['bf_beneficiarios']:>17,}")
print()
PYEOF
  read -rp "  Pressione Enter para continuar..."
}

gerenciar_agendamento() {
  cabecalho
  echo -e "${NEGRITO}  Agendamento Automático${RESET}\n"
  STATUS=$(cd "$DIR" && "$VENV" - <<'PYEOF'
from modules.agendamento import status
s = status()
print("ativo" if s["ativo"] else "inativo")
print(s.get("ultima_execucao") or "nenhuma")
PYEOF
)
  ATIVO=$(echo "$STATUS" | head -1)
  ULTIMA=$(echo "$STATUS" | tail -1)
  info "Status: $ATIVO  |  Última execução: $ULTIMA"
  echo ""
  echo -e "  ${VERDE}1)${RESET} Instalar agendamento semanal"
  echo -e "  ${VERDE}2)${RESET} Instalar agendamento diário"
  echo -e "  ${VERDE}3)${RESET} Instalar agendamento mensal"
  echo -e "  ${VERMELHO}4)${RESET} Remover agendamento"
  echo -e "  ${CINZA}0)${RESET} Voltar"
  read -rp "  Escolha: " sub
  case "$sub" in
    1) cd "$DIR" && "$VENV" -c "from modules.agendamento import instalar_cron; l,m=instalar_cron('semanal','$EMAIL_DESTINO'); print(m)" ;;
    2) cd "$DIR" && "$VENV" -c "from modules.agendamento import instalar_cron; l,m=instalar_cron('diario','$EMAIL_DESTINO'); print(m)" ;;
    3) cd "$DIR" && "$VENV" -c "from modules.agendamento import instalar_cron; l,m=instalar_cron('mensal','$EMAIL_DESTINO'); print(m)" ;;
    4) cd "$DIR" && "$VENV" -c "from modules.agendamento import remover_cron; print(remover_cron())" ;;
    *) return ;;
  esac
  echo ""
  read -rp "  Pressione Enter para continuar..."
}

instalar() {
  cabecalho
  info "Instalando dependências..."
  python3 -m venv "$DIR/venv"
  "$DIR/venv/bin/pip" install -r "$DIR/requirements.txt" -q
  ok "Pronto!"
  read -rp "  Pressione Enter para continuar..."
}

# ── Menu principal ─────────────────────────────────────────────────────────────
main() {
  checar_venv
  carregar_env

  while true; do
    cabecalho
    echo -e "  ${NEGRITO}O que deseja fazer?${RESET}\n"
    echo -e "  ${VERDE}1)${RESET} 🚀  Rodar TUDO  ${CINZA}(monitor + notícias + PDF + dashboard)${RESET}"
    echo -e "  ${VERDE}2)${RESET} 🔍  Rodar monitor de risco"
    echo -e "  ${VERDE}3)${RESET} 🌐  Abrir dashboard   ${CINZA}(http://localhost:5000)${RESET}"
    echo -e "  ${VERDE}4)${RESET} 📰  Atualizar notícias e Diário Oficial"
    echo -e "  ${VERDE}5)${RESET} 📄  Gerar boletim PDF"
    echo -e "  ${VERDE}6)${RESET} 📊  Exportar Excel completo"
    echo -e "  ${VERDE}7)${RESET} 🏙️   Comparar com municípios vizinhos"
    echo -e "  ${VERDE}8)${RESET} 📋  Detectar copy-paste entre contratos"
    echo -e "  ${VERDE}9)${RESET} 🏛️   Buscar contratos no PNCP"
    echo -e "  ${VERDE}c)${RESET} 🗳️   TSE — cruzar doadores de campanha × contratos"
    echo -e "  ${VERDE}d)${RESET} 📊  Benchmark — comparar com municípios similares"
    echo -e "  ${VERDE}e)${RESET} ⏰  Agendamento automático (cron)"
    echo -e "  ${VERDE}a)${RESET} ⚙️   Configurar tokens e alertas"
    echo -e "  ${VERDE}b)${RESET} 📦  Instalar / reinstalar dependências"
    echo -e "  ${VERMELHO}0)${RESET} Sair\n"
    read -rp "  Escolha: " opcao

    case "$opcao" in
      1) rodar_tudo ;;
      2) rodar_monitor ;;
      3) rodar_dashboard ;;
      4) atualizar_noticias_doe ;;
      5) gerar_pdf ;;
      6) exportar_excel ;;
      7) comparar_municipios ;;
      8) detectar_copypaste ;;
      9) buscar_pncp ;;
      c) rodar_tse ;;
      d) rodar_benchmark ;;
      e) gerenciar_agendamento ;;
      a) configurar ;;
      b) instalar ;;
      0) echo -e "\n${CINZA}  Até logo.${RESET}\n"; exit 0 ;;
      *) warn "Opção inválida." ; sleep 1 ;;
    esac
  done
}

main
