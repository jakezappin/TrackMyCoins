# ---- Build the React frontend ----
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Python app that serves the API and the built frontend ----
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist

# Database and photos live on a persistent volume mounted at /data.
ENV DATABASE_URL=sqlite:////data/coin-app.db \
    PHOTO_DIR=/data/photos \
    COOKIE_SECURE=true
EXPOSE 8080
CMD ["sh", "-c", "mkdir -p /data/photos && alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips='*'"]
