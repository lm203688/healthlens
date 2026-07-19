# HealthLens 本地开发启动脚本
# 使用方法: .\scripts\dev.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== HealthLens 本地开发环境 ===" -ForegroundColor Cyan

# 1. 检查 Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] 未找到 Python" -ForegroundColor Red
    exit 1
}

# 2. 创建虚拟环境（如不存在）
if (-not (Test-Path ".venv")) {
    Write-Host "[SETUP] 创建虚拟环境..." -ForegroundColor Yellow
    python -m venv .venv
}

# 3. 激活虚拟环境
Write-Host "[SETUP] 激活虚拟环境..." -ForegroundColor Yellow
& .venv\Scripts\Activate.ps1

# 4. 安装依赖
Write-Host "[SETUP] 安装/更新依赖..." -ForegroundColor Yellow
pip install -e ".[dev]" -q

# 5. 确保 data/uploads 目录存在
New-Item -ItemType Directory -Path "data/uploads" -Force | Out-Null

# 6. 启动 FastAPI 开发服务器
Write-Host ""
Write-Host "=== HealthLens 启动中 ===" -ForegroundColor Green
Write-Host "API: http://localhost:8000" -ForegroundColor Green
Write-Host "Docs: http://localhost:8000/docs" -ForegroundColor Green
Write-Host ""

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000