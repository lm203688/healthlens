# ============================================================
# HealthLens MCP Server — stdio transport (for Docker Hub / Smithery / mcp.so)
#
# Self-contained. No database, no Redis, no OCR — pure stdio MCP server.
# Data sources bundled read-only: TCM-MKG (MIT), classical_books, case_evidence_db.
#
# Build (context = repo root, so COPY can reach ../pyproject.toml etc.):
#   cd <repo-root>
#   docker build -f mcp-server/Dockerfile -t lm203688/healthlens-mcp:latest .
#
# Run locally:
#   docker pull lm203688/healthlens-mcp:latest
#   docker run --rm -i lm203688/healthlens-mcp
#
# Client config (Cursor / Claude Desktop / Cline):
#   {
#     "mcpServers": {
#       "healthlens": {
#         "command": "docker",
#         "args": ["run", "-i", "--rm", "lm203688/healthlens-mcp"]
#       }
#     }
#   }
#
# L3 tools (personalized) — require env var:
#   docker run -i --rm -e HL_MCP_EXPOSE_PRIVATE=1 lm203688/healthlens-mcp
# ============================================================

FROM python:3.12-slim AS runtime

# Security baseline
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps (curl for healthcheck, ca-certs for outbound HTTPS if needed)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       curl \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install with --no-deps: healthlens_agent.mcp_server is stdlib-only at import
# time; the MCP server never touches the web stack (FastAPI/SQLAlchemy/Celery).
# The `docker run ... --demo` smoke test below fails the build if a real
# dependency is missing, so this stays safe without paying for the full web
# dependency tree (~1.5 GB -> ~180 MB image).
COPY pyproject.toml ./
RUN pip install --no-cache-dir --no-deps . \
    && pip install --no-cache-dir "mcp>=1.0.0"

# Create non-root user
RUN groupadd -r mcpuser && useradd -r -g mcpuser -d /app -s /sbin/nologin mcpuser

# Copy application code (only what MCP needs — not the full web stack)
COPY healthlens_agent/ ./healthlens_agent/

# 八轴融合引擎（纯标准库，~24 KB）。打进镜像后 hl_fusion_engine / hl_tcm_constitution
# 在容器里是真能算的，而不是返回 unavailable。
# 【2026-09-29】healthlens_agent/__init__.py 在 import 期就经 flow.py 触发
# load_fusion_engine()，此前镜像里缺这个文件，导致 `python -m healthlens_agent.mcp_server
# --demo` 直接 FileNotFoundError、整个 GHCR 构建被 smoke test 判红。
# 【2026-10-03】_loader.load_fusion_engine() 已改为「缺失返回 None」，
# 这里再 COPY 一份让瘦镜像具备完整能力（两者不冲突，缺哪个都能启动）。
COPY app/lib/fusion_engine.py ./app/lib/fusion_engine.py

# Bundle read-only data assets (all MIT / public domain, no PII)
# - tcm_mkg: 6207 entities aligned to ICD-11 / UMLS / MeSH / DOID
# - classical_books: 701 entries
# - case_evidence_db: 120 case evidence records
# - tcm_pathway_map: pathway index
COPY data/tcm_mkg/ ./data/tcm_mkg/
COPY data/tcm_structured/ ./data/tcm_structured/
COPY data/classical_books.json ./data/classical_books.json
COPY data/case_evidence_db.json ./data/case_evidence_db.json
COPY data/tcm_pathway_map.json ./data/tcm_pathway_map.json

RUN chown -R mcpuser:mcpuser /app
USER mcpuser

# Health check: run --demo and verify tool list prints
HEALTHCHECK --interval=60s --timeout=10s --start-period=5s --retries=3 \
    CMD python -m healthlens_agent.mcp_server --demo >/dev/null 2>&1 || exit 1

# Entrypoint: stdio JSON-RPC MCP server.
# Stdio transport means:
#   - stdin  ← JSON-RPC requests from MCP client
#   - stdout → JSON-RPC responses to MCP client
#   - stderr ← logs (do NOT write to stdout)
ENTRYPOINT ["python", "-m", "healthlens_agent.mcp_server"]
