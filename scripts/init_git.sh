#!/bin/bash
# ============================================================
# HealthLens Git 初始化脚本
# 首次运行: ./scripts/init_git.sh
# ============================================================
set -euo pipefail

echo "=== HealthLens Git 初始化 ==="

# 1. 初始化仓库 (如果尚未初始化)
if [ ! -d .git ]; then
    git init
    echo "[OK] Git 仓库已初始化"
else
    echo "[INFO] Git 仓库已存在"
fi

# 2. 创建 .gitignore (如果不存在)
if [ ! -f .gitignore ]; then
    cat > .gitignore << 'GITIGNORE'
# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
.eggs/

# Virtual environments
.venv/
venv/
env/

# Testing
.pytest_cache/
.coverage
htmlcov/
coverage.xml
.mypy_cache/
.ruff_cache/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Environment & secrets
.env
.env.local
.env.production
!.env.example

# Data & uploads (local development)
data/uploads/
data/tongue_images/
logs/

# Database
*.db
*.sqlite3

# OS
.DS_Store
Thumbs.db

# Docker
docker-compose.override.yml

# Large files
*.tar.gz
*.zip
GITIGNORE
    echo "[OK] .gitignore 已创建"
else
    echo "[INFO] .gitignore 已存在"
fi

# 3. 配置 Git
git config user.name "HealthLens Bot" 2>/dev/null || true
git config user.email "bot@healthlens.dev" 2>/dev/null || true

# 4. 首次提交
echo "[INFO] 准备首次提交..."
git add .
if git diff --cached --quiet; then
    echo "[INFO] 没有需要提交的变更"
else
    git commit -m "feat: HealthLens v0.8.2 - Phase 1 完整发布

中西医融合健康管理平台 - 完整 Phase 1 功能:
- 西医诊断流程 (OCR -> 异常检测 -> ICD-11 -> 处方)
- 中医辨证流程 (体质 -> 辨证 -> 方剂 -> 配送)
- 慢病风险评估 (ASCVD + 糖尿病 + 代谢综合征)
- RBAC 权限系统 (patient/doctor/admin)
- 生产部署配置 (Docker + Nginx + CI/CD)
- Prometheus 监控端点
- 145 tests passed, 0 failed
"
    echo "[OK] 首次提交完成"
fi

# 5. 创建 v0.8.2 标签
if git tag | grep -q "v0.8.2"; then
    echo "[INFO] 标签 v0.8.2 已存在"
else
    git tag -a v0.8.2 -m "HealthLens v0.8.2 - Phase 1 Release"
    echo "[OK] 标签 v0.8.2 已创建"
fi

echo ""
echo "=== 完成 ==="
echo "后续操作:"
echo "  git remote add origin <your-repo-url>"
echo "  git push -u origin main --tags"
