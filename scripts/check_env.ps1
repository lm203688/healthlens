# HealthLens 环境检查脚本
Write-Host "=== HealthLens Environment Check ===" -ForegroundColor Cyan

# Python 版本
$pythonVersion = python --version 2>&1
Write-Host "[Python] $pythonVersion" -ForegroundColor Green

# pip 依赖
$required = @("fastapi", "uvicorn", "sqlalchemy", "pydantic", "pydantic-settings", "python-jose", "passlib")
foreach ($pkg in $required) {
    $installed = pip show $pkg 2>$null
    if ($installed) {
        $ver = ($installed | Where-Object { $_ -match "^Version:" }).Split(":")[1].Trim()
        Write-Host "[OK] $pkg $ver" -ForegroundColor Green
    } else {
        Write-Host "[MISSING] $pkg" -ForegroundColor Red
    }
}

# Docker 检查
$dockerVersion = docker --version 2>$null
if ($dockerVersion) {
    Write-Host "[Docker] $dockerVersion" -ForegroundColor Green
} else {
    Write-Host "[Docker] Not installed" -ForegroundColor Yellow
}

$composeVersion = docker-compose --version 2>$null
if ($composeVersion) {
    Write-Host "[Docker Compose] $composeVersion" -ForegroundColor Green
} else {
    Write-Host "[Docker Compose] Not installed" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Check Complete ===" -ForegroundColor Cyan