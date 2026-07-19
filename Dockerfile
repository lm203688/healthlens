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
       libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency spec and install to isolated prefix
COPY pyproject.toml ./
RUN pip install --no-cache-dir . --prefix=/install \
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
       libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy dependency spec (runtime may need to check versions)
COPY pyproject.toml ./

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

# Copy application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

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