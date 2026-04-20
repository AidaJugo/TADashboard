.PHONY: help install install-backend install-frontend lint lint-backend lint-frontend typecheck test test-backend test-frontend e2e dev build ci clean migration

help:
	@echo "Symphony TA Hiring Report Platform"
	@echo ""
	@echo "Common targets:"
	@echo "  make install          install backend and frontend deps"
	@echo "  make dev              docker-compose up (db + backend + frontend)"
	@echo "  make lint             ruff, black, eslint, prettier"
	@echo "  make typecheck        mypy + tsc --noEmit"
	@echo "  make test             backend unit + integration, frontend unit"
	@echo "  make e2e              Playwright end-to-end"
	@echo "  make ci               the full CI suite, locally"
	@echo "  make migration m=\"<msg>\"  create a new Alembic migration"

install: install-backend install-frontend

install-backend:
	cd backend && uv sync

install-frontend:
	cd frontend && npm install

lint: lint-backend lint-frontend

lint-backend:
	cd backend && uv run ruff check . && uv run black --check .

lint-frontend:
	cd frontend && npm run lint && npm run format

typecheck:
	cd backend && uv run mypy app
	cd frontend && npm run typecheck

test: test-backend test-frontend

test-backend:
	cd backend && uv run pytest -m "unit or integration"

test-frontend:
	cd frontend && npm run test

e2e:
	cd frontend && npm run e2e

dev:
	docker compose up --build

build:
	docker compose build

migration:
	@if [ -z "$(m)" ]; then echo "usage: make migration m=\"add users table\""; exit 1; fi
	cd backend && uv run alembic revision -m "$(m)"

ci: lint typecheck test
	cd backend && uv run pip-audit --strict || true
	cd frontend && npm audit --audit-level=high || true

clean:
	rm -rf backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache backend/.venv
	rm -rf frontend/node_modules frontend/dist frontend/playwright-report frontend/test-results
