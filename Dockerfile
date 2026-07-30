# syntax=docker/dockerfile:1
# H2A Migration Cockpit — single web service (React SPA + FastAPI + engine).
# Multi-stage: build the React app with Node, then serve it from the Python image.

# ── Stage 1: build the React cockpit ──────────────────────────────────────────
FROM node:20-slim AS web
WORKDIR /web
COPY h2a-web/web/package.json h2a-web/web/package-lock.json ./
RUN npm ci
COPY h2a-web/web/ ./
RUN npm run build

# ── Stage 2: Python runtime (engine + FastAPI backend) ────────────────────────
FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    H2A_PROVIDER=mock \
    H2A_HOSTED=1
WORKDIR /app

# deps first for better layer caching
COPY h2a-mvp/requirements.txt /app/h2a-mvp/requirements.txt
COPY h2a-web/backend/requirements.txt /app/h2a-web/backend/requirements.txt
RUN pip install -r /app/h2a-mvp/requirements.txt -r /app/h2a-web/backend/requirements.txt

# engine + backend + demo inputs (paths must keep the /app/{h2a-mvp,h2a-web,Testing} layout)
COPY h2a-mvp/ /app/h2a-mvp/
COPY h2a-web/ /app/h2a-web/
COPY Testing/ /app/Testing/

# built frontend from stage 1
COPY --from=web /web/dist /app/h2a-web/web/dist

WORKDIR /app/h2a-web/backend
EXPOSE 8000
# Render (and most PaaS) inject $PORT; bind 0.0.0.0 so it's reachable.
CMD ["sh", "-c", "python -m uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
