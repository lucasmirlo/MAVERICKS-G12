# syntax=docker/dockerfile:1
# Imagen única para web y worker (comandos distintos en Railway).

FROM node:24-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY config ./config
COPY evidence/input_manifest.json ./evidence/input_manifest.json
COPY inputs/supplier_training.xlsx inputs/supplier_validation.xlsx inputs/supplier_test.xlsx inputs/supplier_liveday.xlsx ./inputs/
COPY --from=web /web/dist ./static
USER app
EXPOSE 8000
# Railway inyecta PORT. Las migraciones las ejecuta solo la web como pre-deploy.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --proxy-headers --forwarded-allow-ips='*'"]
