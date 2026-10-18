#!/usr/bin/env bash
# HealthLens MCP Server — 安装与验证脚本
#
# 用法:
#   bash mcp-server/test_install.sh          # 从 git 安装
#   bash mcp-server/test_install.sh --pypi   # 从 PyPI 安装

set -euo pipefail

MODE="git"
if [ "${1:-}" = "--pypi" ]; then
  MODE="pypi"
fi

REPO_URL="${HL_REPO_URL:-https://github.com/lm203688/healthlens}"

echo "=== HealthLens MCP Server — Install Test ==="
echo "Mode: ${MODE}"
echo ""

# Step 1: Install
if [ "$MODE" = "pypi" ]; then
  echo "[1/3] pip install healthlens-mcp-server"
  pip install --user healthlens-mcp-server
else
  echo "[1/3] Clone and install from git"
  TMP_DIR=$(mktemp -d)
  git clone --depth 1 "$REPO_URL" "$TMP_DIR/healthlens"
  (cd "$TMP_DIR/healthlens" && pip install --user .)
fi

# Step 2: Verify tool list
echo ""
echo "[2/3] Verify tool list (--demo)"
python -m healthlens_agent mcp --demo

# Step 3: Test JSON-RPC stdio round-trip
echo ""
echo "[3/3] Test JSON-RPC initialize + tools/list"
RESPONSE=$(printf '{"jsonrpc":"2.0","id":1,"method":"initialize"}\n{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n' \
  | python -m healthlens_agent mcp --jsonrpc 2>&1)
echo "$RESPONSE" | head -5

echo ""
echo "=== Install test complete ==="
