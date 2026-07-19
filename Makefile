# ============================================================
# HealthLens Makefile
# Usage: make [target]
# ============================================================

.PHONY: help dev test lint build up down migrate seed \
        prod-up prod-down prod-deploy logs ps clean

# Default target
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ----------------------------------------------------------
# Development
# ----------------------------------------------------------

dev: ## Start API server (local)
	python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

worker: ## Start Celery worker (local)
	celery -A app.worker.celery_app worker --loglevel=info --concurrency=2

test: ## Run all tests
	python -m pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage report
	python -m pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html

lint: ## Run linters
	ruff check app/ tests/
	ruff format --check app/ tests/

fmt: ## Auto-format code
	ruff format app/ tests/
	ruff check --fix app/ tests/

# ----------------------------------------------------------
# Docker (Development)
# ----------------------------------------------------------

build: ## Build Docker images
	docker compose build

up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

migrate: ## Run database migrations
	docker compose exec web alembic upgrade head

seed: ## Create admin user
	docker compose exec web python scripts/seed_admin.py

ps: ## Show service status
	docker compose ps

logs: ## Show all logs (Ctrl+C to exit)
	docker compose logs -f

logs-web: ## Show web service logs
	docker compose logs -f web

logs-worker: ## Show worker service logs
	docker compose logs -f worker

# ----------------------------------------------------------
# Docker (Production)
# ----------------------------------------------------------

prod-up: ## Start production stack
	docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d

prod-down: ## Stop production stack
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down

prod-deploy: ## Full production deploy (backup + build + migrate + verify)
	./scripts/deploy.sh

prod-logs: ## Show production logs
	docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f

# ----------------------------------------------------------
# Cleanup
# ----------------------------------------------------------

clean: ## Remove containers, volumes, and cached data
	docker compose down -v --remove-orphans
	rm -rf htmlcov/ .coverage .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
