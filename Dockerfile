# ============================================================
# HealthLens Production Dockerfile
# Multi-stage build: smaller image, better caching
# ============================================================

# Stage 1: Builder - install Python dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

# System build dependencies (gcc for C extensions, tesseract for OCR, GL for PaddleOCR)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc libpq-dev tesseract-ocr \
       libgl1 libegl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency spec and install to isolated prefix
# 用 ".[ocr]"：PaddleOCR 已移入可选 extra（体积大、仅惰性 import），
# 但生产环境需要 OCR 能力，所以显式装回，行为与旧版 `pip install .` 一致。
COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[ocr]" --prefix=/install \
    && rm -rf /install/lib/python3.11/site-packages/tests

# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libpq5 tesseract-ocr curl \
       libgl1 libegl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy dependency spec (runtime may need to check versions)
# 注意：以下 COPY 的文件/目录必须进镜像层——它们不在 docker-compose bind mount 列表里，
# 否则 `docker compose up -d --force-recreate` 重建容器后就会丢失（v0.28/v0.29 部署坑）。
COPY pyproject.toml ./

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

# Copy application code
COPY app/ ./app/
# healthlens_agent 是 app/api/agent.py 等模块的直接依赖（`from healthlens_agent.pipeline import ...`），
# 必须进镜像，不能依赖 bind mount。
COPY healthlens_agent/ ./healthlens_agent/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# 以下三项不在 bind mount 列表内——只能靠镜像层 COPY：
#   - config/           运行时读取（federated_defaults / national_standards / serializer_schema / axes）
#   - agent-card.json   /.well-known/agent-card.json 端点直接读该文件
# pyproject.toml 已在上面 COPY。
COPY config/ ./config/
COPY agent-card.json ./agent-card.json

# Create required directories and fix ownership
RUN mkdir -p /app/data /app/logs \
    && chown -R appuser:appuser /app

USER appuser

# Expose port
EXPOSE 8000

# Health check (Docker HEALTHCHECK and orchestrator probe)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Entrypoint supports both web server and celery worker modes
# Default: uvicorn web server
# Override with: docker run --entrypoint "" ... celery -A app.worker.celery_app worker ...
ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
CMD ["--workers", "4"]