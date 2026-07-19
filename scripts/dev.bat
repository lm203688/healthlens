@echo off
chcp 65001 >nul 2>&1
title HealthLens Dev Server

echo === HealthLens 本地开发环境 ===

:: 1. 检查 Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 未找到 Python
    pause
    exit /b 1
)

:: 2. 创建虚拟环境（如不存在）
if not exist ".venv" (
    echo [SETUP] 创建虚拟环境...
    python -m venv .venv
)

:: 3. 激活虚拟环境
echo [SETUP] 激活虚拟环境...
call .venv\Scripts\activate.bat

:: 4. 安装依赖
echo [SETUP] 安装/更新依赖...
pip install -e ".[dev]" -q

:: 5. 确保 data/uploads 目录存在
if not exist "data\uploads" mkdir data\uploads

:: 6. 启动 FastAPI 开发服务器
echo.
echo === HealthLens 启动中 ===
echo API: http://localhost:8000
echo Docs: http://localhost:8000/docs
echo.

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000