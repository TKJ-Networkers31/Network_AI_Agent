# ==============================================================================
# AIRA OS — Multi-stage Lightweight Production Dockerfile
# Optimized for low-resource VPS (<= 2GB RAM)
# ==============================================================================

# Stage 1: Build Frontend Assets
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY AIRA_ECOSYSTEM/app/frontend/package*.json ./
RUN npm ci --prefer-offline --no-audit

COPY AIRA_ECOSYSTEM/app/frontend/ ./
RUN npm run build

# Stage 2: Minimal Python Runtime
FROM python:3.12-slim AS runner

# System dependencies: minimal runtime requirements
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    procps \
    ca-certificates \
    traceroute \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements (without heavy YOLO/ultralytics)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Backend codebase
COPY AIRA_ECOSYSTEM/ ./AIRA_ECOSYSTEM/

# Copy built frontend distribution to static hosting path
COPY --from=frontend-builder /app/frontend/dist ./AIRA_ECOSYSTEM/app/frontend/dist

# Security: Non-root user setup
RUN groupadd -g 10001 aira && \
    useradd -u 10001 -g aira -s /bin/bash -m aira && \
    mkdir -p /app/AIRA_ECOSYSTEM/database /app/workspace /app/AIRA_ECOSYSTEM/logs && \
    chown -R aira:aira /app

USER aira

ENV PYTHONPATH=/app/AIRA_ECOSYSTEM \
    PYTHONUNBUFFERED=1 \
    AIRA_ENV=production \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
