# HealthLens 开发环境初始化
Write-Host "=== HealthLens Dev Setup ===" -ForegroundColor Cyan

# 创建虚拟环境
if (!(Test-Path ".venv")) {
    Write-Host "[1/4] Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
} else {
    Write-Host "[1/4] Virtual environment exists" -ForegroundColor Green
}

# 激活并安装依赖
Write-Host "[2/4] Installing dependencies..." -ForegroundColor Yellow
& .venv\Scripts\Activate.ps1
pip install -e ".[dev]" --quiet

# 创建必要目录
Write-Host "[3/4] Creating directories..." -ForegroundColor Yellow
$dirs = @("logs", "data", "app/ml/models")
foreach ($d in $dirs) {
    if (!(Test-Path $d)) { New-Item -ItemType Directory -Path $d | Out-Null }
}

# 生成 .env
Write-Host "[4/4] Checking .env..." -ForegroundColor Yellow
if (!(Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example - please update secrets!" -ForegroundColor Green
} else {
    Write-Host ".env exists" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Cyan
Write-Host "Run: docker-compose up -d   (start DB/Redis/MinIO)" -ForegroundColor White
Write-Host "Run: uvicorn app.main:app --reload   (start API server)" -ForegroundColor White