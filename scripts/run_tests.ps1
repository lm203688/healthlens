# 运行 HealthLens 测试
Write-Host "=== Running HealthLens Tests ===" -ForegroundColor Cyan
& .venv\Scripts\Activate.ps1
pytest tests/ -v --tb=short --cov=app --cov-report=term-missing