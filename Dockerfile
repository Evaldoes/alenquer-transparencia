FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py monitor.py ./
COPY modules ./modules
COPY templates ./templates

RUN useradd --create-home app && mkdir -p dados && chown app:app dados
USER app

ENV HOST=0.0.0.0 RESULTADOS_JSON=/app/dados/resultados_monitor.json
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request as u; u.urlopen('http://localhost:5000/v1/status')"
CMD ["python", "app.py"]
