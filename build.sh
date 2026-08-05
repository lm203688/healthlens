#!/bin/bash
# HealthLens 静态站点构建入口（Cloudflare Pages 友好）
# 将 Cloudflare Pages 的「构建命令」设为 `bash build.sh` 即可。
# 自动选择 python3 / python，避免部分构建镜像缺少 `python` 别名导致构建失败。
set -euo pipefail
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "::error:: 未找到 python3/python，无法构建"; exit 1
fi
echo "使用 Python 解释器: $PY"
"$PY" auto-pipeline/scripts/phase_6_deploy/build_site.py
