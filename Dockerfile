# ДЛЯ СБОРКИ НУЖНО ЛИБА!! sdk_max

FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir poetry==1.7.1

COPY pyproject.toml poetry.lock* ./

RUN --mount=type=cache,target=/root/.cache/pypoetry \
    poetry config virtualenvs.create false && \
    poetry source add pypi https://pypi.org/simple/ --priority=primary 2>/dev/null || true && \
    poetry config http-basic.max-sdk sdk_max && \
    poetry install --only main --no-interaction --no-ansi --no-root

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

RUN groupadd -r appuser && useradd -r -g appuser -s /bin/bash appuser

COPY --chown=appuser:appuser . .

RUN mkdir -p /app/data /app/logs/debug /app/logs/info && \
    touch /app/secret_key.json /app/data/database.db && \
    chmod -R 777 /app && \
    chown -R appuser:appuser /app

RUN ls -la secret_key.json && ls -la logs/

USER appuser

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

CMD ["python", "main.py"]
EXPOSE 8000