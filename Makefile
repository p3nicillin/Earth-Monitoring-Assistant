.PHONY: up down logs test test-backend test-frontend lint migrate seed

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api web

test: test-backend test-frontend

test-backend:
	cd backend && python -m pytest

test-frontend:
	cd frontend && npm test && npm run build

lint:
	cd backend && ruff check app tests && ruff format --check app tests
	cd frontend && npm run typecheck

migrate:
	cd backend && alembic upgrade head

seed:
	cd backend && python -m app.seed
