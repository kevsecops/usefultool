COMPOSE_DEV = docker compose -f docker-compose.yml -f docker-compose.dev.yml

.PHONY: up down rebuild logs ingest ps health test-backend dev dev-watch dev-logs dev-down

up:
	@test -f .env || cp .env.example .env
	docker compose up -d --build

down:
	docker compose down

rebuild:
	docker compose down
	docker compose build --no-cache
	docker compose up -d

dev:
	@test -f .env || cp .env.example .env
	$(COMPOSE_DEV) up -d --build

dev-watch:
	@test -f .env || cp .env.example .env
	$(COMPOSE_DEV) up --build --watch

dev-down:
	$(COMPOSE_DEV) down

dev-logs:
	$(COMPOSE_DEV) logs -f frontend backend

logs:
	docker compose logs -f frontend backend

ingest:
	docker compose exec backend python -m app.jobs.cli ingest

ps:
	docker compose ps

health:
	@curl -sf http://localhost:8000/health && echo
	@curl -sf -o /dev/null -w "frontend HTTP %{http_code}\n" http://localhost:3000/

test-backend:
	docker compose exec backend pytest -v
