# python:3.12.14-slim-trixie
FROM python@sha256:8edbf9e42c7fb168b9c523718ed907117e6d2e60f5889c0c499bbda3a787da53

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Native libraries required by WeasyPrint for production-quality PDF exports.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libffi8 \
    libgdk-pixbuf-2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    openssl \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN addgroup --system practiceflow && adduser --system --ingroup practiceflow --home /app practiceflow

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
