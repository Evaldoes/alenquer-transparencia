"""
Alertas automáticos — e-mail e WhatsApp (via Evolution API ou Twilio).
"""
import json
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests


# ── E-mail ────────────────────────────────────────────────────────────────────

def enviar_email(assunto, corpo, destino, remetente, senha):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"]    = remetente
    msg["To"]      = destino
    msg.attach(MIMEText(corpo, "plain", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(remetente, senha)
        smtp.sendmail(remetente, destino, msg.as_string())


def alerta_risco_email(resultados, destino, remetente, senha):
    alto  = [r for r in resultados if r.get("score", 0) >= 70]
    medio = [r for r in resultados if 40 <= r.get("score", 0) < 70]
    if not alto and not medio:
        return

    linhas = [
        f"⚠️ Monitor de Transparência — Alenquer/PA",
        f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        f"",
        f"🔴 Alto risco: {len(alto)} contrato(s)",
        f"🟡 Médio risco: {len(medio)} contrato(s)",
        f"",
    ]
    for r in sorted(alto + medio, key=lambda x: x["score"], reverse=True)[:5]:
        c     = r.get("contrato", {})
        valor = float(c.get("valorInicialCompra") or c.get("valor") or 0)
        linhas += [
            f"Score {r['score']}/100 — {c.get('nomeContratado', 'N/A')}",
            f"  Valor: R$ {valor:,.0f}  |  {c.get('modalidadeCompra', '')}",
            f"  {'; '.join(r.get('flags', [])[:2])}",
            "",
        ]

    enviar_email(
        f"⚠️ Transparência Alenquer — {len(alto)} alto risco",
        "\n".join(linhas),
        destino, remetente, senha,
    )


# ── WhatsApp via Evolution API (self-hosted) ──────────────────────────────────

def enviar_whatsapp_evolution(mensagem, numero, evolution_url, evolution_key, instancia):
    """
    Envia mensagem via Evolution API (https://doc.evolution-api.com).
    numero: formato internacional sem + (ex: "5593999991234")
    """
    url  = f"{evolution_url}/message/sendText/{instancia}"
    body = {
        "number":  numero,
        "textMessage": {"text": mensagem},
    }
    r = requests.post(url, json=body,
                      headers={"apikey": evolution_key, "Content-Type": "application/json"},
                      timeout=15)
    r.raise_for_status()
    return r.json()


def enviar_whatsapp_twilio(mensagem, numero_destino, account_sid, auth_token, numero_twilio):
    """
    Envia mensagem via Twilio WhatsApp Sandbox.
    numero_destino: ex "whatsapp:+5593999991234"
    numero_twilio:  ex "whatsapp:+14155238886"
    """
    r = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
        data={
            "From": numero_twilio,
            "To":   numero_destino,
            "Body": mensagem,
        },
        auth=(account_sid, auth_token),
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def mensagem_alerta_whatsapp(resultados):
    alto  = [r for r in resultados if r.get("score", 0) >= 70]
    medio = [r for r in resultados if 40 <= r.get("score", 0) < 70]
    data  = datetime.now().strftime("%d/%m/%Y")

    linhas = [
        f"📊 *Monitor Transparência — Alenquer/PA*",
        f"_{data}_",
        f"",
        f"🔴 Alto risco: *{len(alto)}* contrato(s)",
        f"🟡 Médio risco: *{len(medio)}* contrato(s)",
        f"",
    ]
    for r in sorted(alto, key=lambda x: x["score"], reverse=True)[:3]:
        c = r.get("contrato", {})
        linhas += [
            f"⚠ *{c.get('nomeContratado', 'N/A')[:35]}*",
            f"  Score {r['score']}/100",
            f"  {r.get('flags', [''])[0][:60]}",
            "",
        ]
    linhas.append("Acesse o dashboard para detalhes.")
    return "\n".join(linhas)
