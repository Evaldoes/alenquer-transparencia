"""
OCR em PDFs de licitações e contratos.
Extrai texto de PDFs escaneados para análise no monitor de risco.

Dependências: pytesseract, pdf2image, pillow
Sistema: tesseract-ocr (apt install tesseract-ocr tesseract-ocr-por)
"""
import io
import re
import tempfile
from pathlib import Path

DADOS_DIR = Path(__file__).parent.parent / "dados" / "pdfs_ocr"


def _verificar_dependencias():
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
        from PIL import Image
        return True
    except ImportError as e:
        print(f"  [OCR] Dependência não instalada: {e}")
        print("  Execute: pip install pytesseract pdf2image pillow")
        print("  E instale o tesseract: sudo apt install tesseract-ocr tesseract-ocr-por")
        return False


def extrair_texto_pdf(pdf_bytes, idioma="por"):
    """
    Extrai texto de PDF (incluindo PDFs escaneados) via OCR.
    Retorna texto limpo.
    """
    if not _verificar_dependencias():
        return ""

    import pytesseract
    from pdf2image import convert_from_bytes
    from PIL import Image

    try:
        imagens  = convert_from_bytes(pdf_bytes, dpi=200)
        textos   = []
        for img in imagens:
            texto = pytesseract.image_to_string(img, lang=idioma, config="--psm 6")
            textos.append(texto)
        return "\n".join(textos)
    except Exception as e:
        print(f"  [OCR] Erro: {e}")
        return ""


def extrair_texto_url(url, idioma="por"):
    """
    Baixa um PDF de uma URL e extrai o texto via OCR.
    """
    import requests
    try:
        r = requests.get(url, timeout=30,
                         headers={"User-Agent": "monitor-transparencia-alenquer/1.0"})
        r.raise_for_status()
        return extrair_texto_pdf(r.content, idioma)
    except Exception as e:
        print(f"  [OCR] Erro ao baixar {url}: {e}")
        return ""


def salvar_e_extrair(pdf_bytes, nome_arquivo):
    """
    Salva o PDF em disco e extrai o texto.
    Cache: se já foi processado, retorna o texto salvo.
    """
    DADOS_DIR.mkdir(parents=True, exist_ok=True)
    caminho_pdf  = DADOS_DIR / nome_arquivo
    caminho_txt  = DADOS_DIR / (nome_arquivo + ".txt")

    if caminho_txt.exists():
        return caminho_txt.read_text(encoding="utf-8")

    caminho_pdf.write_bytes(pdf_bytes)
    texto = extrair_texto_pdf(pdf_bytes)

    if texto.strip():
        caminho_txt.write_text(texto, encoding="utf-8")

    return texto


def analisar_texto_contrato(texto):
    """
    Analisa o texto extraído de um contrato e retorna:
    - Valores mencionados
    - CNPJs/CPFs encontrados
    - Datas
    - Palavras-chave suspeitas
    - Resumo estruturado
    """
    # Extrair valores monetários
    valores = re.findall(r"R\$\s*[\d.,]+", texto)
    valores_num = []
    for v in valores:
        try:
            n = float(re.sub(r"[^\d,]", "", v).replace(",", "."))
            valores_num.append(n)
        except Exception:
            pass

    # Extrair CNPJs
    cnpjs = re.findall(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto)

    # Extrair datas
    datas = re.findall(r"\d{2}/\d{2}/\d{4}", texto)

    # Palavras suspeitas
    suspeitas = [
        "dispensa", "inexigibilidade", "emergência", "urgência",
        "inexigível", "dispensável", "caráter emergencial",
        "único fornecedor", "exclusividade", "notória especialização",
    ]
    flags_texto = [s for s in suspeitas if s.lower() in texto.lower()]

    return {
        "caracteres":       len(texto),
        "valores":          valores[:10],
        "valor_maximo":     max(valores_num) if valores_num else 0,
        "cnpjs":            list(set(cnpjs))[:5],
        "datas":            list(set(datas))[:5],
        "palavras_suspeitas": flags_texto,
        "tem_objeto_vago":  len(texto) < 500 and bool(texto.strip()),
        "preview":          texto[:500].strip(),
    }


def processar_lote_urls(urls, max_pdfs=10):
    """
    Processa uma lista de URLs de PDFs em lote.
    Retorna lista de {url, texto, analise}.
    """
    resultados = []
    for url in urls[:max_pdfs]:
        texto   = extrair_texto_url(url)
        analise = analisar_texto_contrato(texto) if texto else {}
        resultados.append({"url": url, "texto": texto[:2000], "analise": analise})
    return resultados
