"""
Geração de boletim mensal em PDF — Alenquer/PA
Dependência: reportlab
"""
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

VERDE       = colors.HexColor("#1a6b3c")
VERDE_CLARO = colors.HexColor("#2d9e5f")
VERMELHO    = colors.HexColor("#c53030")
AMARELO     = colors.HexColor("#d69e2e")
CINZA       = colors.HexColor("#4a5568")
CINZA_CLARO = colors.HexColor("#edf2f7")
BRANCO      = colors.white

OUTPUT_DIR = Path(__file__).parent.parent / "dados"


def _estilos():
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("titulo", parent=base["Title"],
            fontSize=22, textColor=VERDE, spaceAfter=4, leading=26),
        "subtitulo": ParagraphStyle("subtitulo", parent=base["Normal"],
            fontSize=11, textColor=CINZA, spaceAfter=16),
        "secao": ParagraphStyle("secao", parent=base["Heading2"],
            fontSize=13, textColor=VERDE, spaceBefore=18, spaceAfter=6,
            borderPad=4),
        "corpo": ParagraphStyle("corpo", parent=base["Normal"],
            fontSize=10, textColor=colors.HexColor("#2d3748"),
            spaceAfter=6, leading=15),
        "flag": ParagraphStyle("flag", parent=base["Normal"],
            fontSize=9, textColor=VERMELHO, leftIndent=12, spaceAfter=3),
        "rodape": ParagraphStyle("rodape", parent=base["Normal"],
            fontSize=8, textColor=CINZA, alignment=1),
    }


def _fmt(v):
    return f"R$ {float(v):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _card_tabela(dados, cor_header=VERDE):
    """Cria uma tabela estilizada para os cards de resumo."""
    t = Table(dados, colWidths=[9*cm, 7*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), cor_header),
        ("TEXTCOLOR",   (0, 0), (-1, 0), BRANCO),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 10),
        ("BACKGROUND",  (0, 1), (-1, -1), CINZA_CLARO),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BRANCO, CINZA_CLARO]),
        ("FONTSIZE",    (0, 1), (-1, -1), 9),
        ("TEXTCOLOR",   (0, 1), (-1, -1), colors.HexColor("#2d3748")),
        ("GRID",        (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e0")),
        ("ROWHEIGHT",   (0, 0), (-1, -1), 18),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def gerar_pdf(dados_bf, dados_transf, dados_desp, resultados_monitor,
              municipio="Alenquer/PA", mes_ref=None):
    """
    Gera o boletim mensal em PDF e retorna o caminho do arquivo.

    Parâmetros:
        dados_bf       — lista de dicts com mesAno/beneficiarios/valor
        dados_transf   — lista de dicts de transferências
        dados_desp     — lista de dicts de despesas
        resultados_monitor — lista de dicts do monitor de risco
        municipio      — nome do município
        mes_ref        — string de referência do mês (ex: "Maio/2025")
    """
    OUTPUT_DIR.mkdir(exist_ok=True)
    agora    = datetime.now()
    mes_ref  = mes_ref or agora.strftime("%B/%Y").capitalize()
    nome_arq = OUTPUT_DIR / f"boletim_{agora.strftime('%Y%m')}.pdf"

    doc   = SimpleDocTemplate(str(nome_arq), pagesize=A4,
                               leftMargin=2*cm, rightMargin=2*cm,
                               topMargin=2*cm, bottomMargin=2*cm)
    est   = _estilos()
    story = []

    # ── Cabeçalho ──────────────────────────────────────────────────────────
    story += [
        Paragraph(f"Boletim de Transparência", est["titulo"]),
        Paragraph(f"{municipio} — {mes_ref}", est["subtitulo"]),
        HRFlowable(width="100%", thickness=2, color=VERDE_CLARO),
        Spacer(1, 0.4*cm),
        Paragraph(
            f"Dados extraídos do Portal da Transparência do Governo Federal. "
            f"Gerado automaticamente em {agora.strftime('%d/%m/%Y às %H:%M')}.",
            est["corpo"],
        ),
        Spacer(1, 0.3*cm),
    ]

    # ── Bolsa Família ──────────────────────────────────────────────────────
    story.append(Paragraph("Bolsa Família", est["secao"]))
    if dados_bf:
        ultimo = dados_bf[-1]
        tabela_bf = [["Mês", "Beneficiários", "Valor Total"]]
        for d in dados_bf[-6:]:
            tabela_bf.append([
                d.get("mesAno", ""),
                f"{int(d.get('beneficiarios', 0)):,}".replace(",", "."),
                _fmt(d.get("valor", 0)),
            ])
        t = Table(tabela_bf, colWidths=[5*cm, 5.5*cm, 5.5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0), VERDE),
            ("TEXTCOLOR",   (0, 0), (-1, 0), BRANCO),
            ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN",       (1, 0), (-1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BRANCO, CINZA_CLARO]),
            ("GRID",        (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e0")),
            ("FONTSIZE",    (0, 0), (-1, -1), 9),
            ("ROWHEIGHT",   (0, 0), (-1, -1), 18),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story += [t, Spacer(1, 0.3*cm)]

    # ── Transferências ─────────────────────────────────────────────────────
    story.append(Paragraph("Transferências Federais Recebidas", est["secao"]))
    if dados_transf:
        total_transf = sum(float(d.get("valor", 0)) for d in dados_transf)
        story.append(Paragraph(f"Total no período: <b>{_fmt(total_transf)}</b>", est["corpo"]))
        tab_t = [["Ação / Programa", "Valor"]]
        for d in dados_transf[:12]:
            tab_t.append([
                str(d.get("acao") or d.get("nomeFuncao") or "N/A")[:60],
                _fmt(d.get("valor", 0)),
            ])
        story += [_card_tabela(tab_t), Spacer(1, 0.3*cm)]

    # ── Despesas ───────────────────────────────────────────────────────────
    story.append(Paragraph("Principais Despesas Federais", est["secao"]))
    if dados_desp:
        total_desp = sum(float(d.get("valorLiquido") or d.get("valor") or 0) for d in dados_desp)
        story.append(Paragraph(f"Total no período: <b>{_fmt(total_desp)}</b>", est["corpo"]))
        tab_d = [["Favorecido", "Valor"]]
        for d in dados_desp[:12]:
            tab_d.append([
                str(d.get("nomeFavorecido") or "N/A")[:55],
                _fmt(d.get("valorLiquido") or d.get("valor") or 0),
            ])
        story += [_card_tabela(tab_d, CINZA), Spacer(1, 0.3*cm)]

    # ── Monitor de Risco ───────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Monitor de Risco — Contratos Suspeitos", est["secao"]))

    alto  = [r for r in resultados_monitor if r.get("score", 0) >= 70]
    medio = [r for r in resultados_monitor if 40 <= r.get("score", 0) < 70]

    story.append(Paragraph(
        f"Total analisado: <b>{len(resultados_monitor)}</b> contratos  |  "
        f"Alto risco: <b>{len(alto)}</b>  |  Médio risco: <b>{len(medio)}</b>",
        est["corpo"],
    ))
    story.append(Spacer(1, 0.3*cm))

    for nivel, lista, cor in [("ALTO RISCO", alto, VERMELHO), ("MÉDIO RISCO", medio, AMARELO)]:
        if not lista:
            continue
        story.append(Paragraph(f"⚠ {nivel}", ParagraphStyle(
            f"nivel_{nivel}", parent=_estilos()["secao"], textColor=cor, fontSize=11)))
        for r in sorted(lista, key=lambda x: x["score"], reverse=True)[:8]:
            c     = r.get("contrato", {})
            valor = float(c.get("valorInicialCompra") or c.get("valor") or 0)
            story += [
                Paragraph(
                    f"<b>{c.get('nomeContratado', 'N/A')}</b> — Score: {r['score']}/100",
                    est["corpo"],
                ),
                Paragraph(
                    f"Objeto: {str(c.get('objetoCompra') or '')[:80]} | "
                    f"Valor: {_fmt(valor)} | Modalidade: {c.get('modalidadeCompra', 'N/A')}",
                    est["corpo"],
                ),
                *[Paragraph(f"⚠ {f}", est["flag"]) for f in r.get("flags", [])[:4]],
                Spacer(1, 0.2*cm),
            ]

    # ── Rodapé ─────────────────────────────────────────────────────────────
    story += [
        HRFlowable(width="100%", thickness=1, color=CINZA_CLARO),
        Spacer(1, 0.2*cm),
        Paragraph(
            "Dados públicos extraídos do Portal da Transparência do Governo Federal (portaldatransparencia.gov.br). "
            "Este boletim é gerado automaticamente. Para denúncias, acesse a Ouvidoria do TCM-PA.",
            est["rodape"],
        ),
    ]

    doc.build(story)
    return str(nome_arq)
