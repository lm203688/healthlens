@echo off
cd /d "%~dp0\.."
if not exist ".venv" (
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -e ".[dev]" -q
celery -A app.worker.celery_app worker --loglevel=info --pool=solo
