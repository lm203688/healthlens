# HealthLens Celery Worker 启动脚本
# 使用方法: .\scripts\worker.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== HealthLens Celery Worker ===" -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] 未找到 Python" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path ".venv")) {
    Write-Host "[SETUP] 创建虚拟环境..." -ForegroundColor Yellow
    python -m venv .venv
}

& .venv\Scripts\Activate.ps1

Write-Host "[SETUP] 安装依赖..." -ForegroundColor Yellow
pip install -e ".[dev]" -q

Write-Host ""
Write-Host "=== Celery Worker 启动中 ===" -ForegroundColor Green
Write-Host "Broker: redis://localhost:6379/0" -ForegroundColor Green
Write-Host ""

celery -A app.worker.celery_app worker --loglevel=info --pool=solo
