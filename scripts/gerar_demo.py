"""Gera a demonstração estática em docs/index.html a partir do painel e de demo/demo.js."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "docs" / "index.html"
MARCA = '<meta name="viewport"'


def gerar() -> str:
    html = (RAIZ / "templates" / "index.html").read_text(encoding="utf-8")
    demo = (RAIZ / "demo" / "demo.js").read_text(encoding="utf-8")
    if MARCA not in html:
        raise ValueError("Ponto de inserção não encontrado no template")
    extra = f'<meta name="robots" content="noindex"/>\n  <script>\n{demo}  </script>\n  '
    return html.replace(MARCA, extra + MARCA, 1)


if __name__ == "__main__":
    DESTINO.write_text(gerar(), encoding="utf-8")
