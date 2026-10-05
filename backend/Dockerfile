# python:3.12-alpine3.24 (manifest resolved 2026-10-05)
FROM python@sha256:1b668429b3511ab407d8e00648891631b0b1a4d7e15e3ca70f38ab5b91ad4ab4

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Native libraries required by WeasyPrint for production-quality PDF exports.
RUN apk upgrade --no-cache && apk add --no-cache \
    cairo \
    libffi \
    gdk-pixbuf \
    pango \
    fontconfig \
    font-dejavu \
    font-noto \
    openssl \
    poppler-utils \
    shared-mime-info \
    && fc-cache -f

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -c "from weasyprint import HTML; assert HTML(string='<p>PDF rendering smoke test</p>').write_pdf().startswith(b'%PDF-')"

RUN addgroup -S practiceflow && adduser -S -G practiceflow -h /app practiceflow

COPY --chown=practiceflow:practiceflow alembic.ini docker-entrypoint.sh seed.py e2e_seed.py ./
COPY --chown=practiceflow:practiceflow scripts ./scripts
COPY --chown=practiceflow:practiceflow alembic ./alembic
COPY --chown=practiceflow:practiceflow app ./app

RUN mkdir -p /app/storage_data && chown -R practiceflow:practiceflow /app/storage_data \
    && chmod +x /app/docker-entrypoint.sh

USER practiceflow

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"]

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-access-log"]
