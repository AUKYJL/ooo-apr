COMPOSE := docker compose

.PHONY: up down logs lint migrate seed bootstrap test docs docs-check

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

migrate:
	$(COMPOSE) run --rm migrate

seed:
	$(COMPOSE) run --rm seed

bootstrap: up migrate seed

lint:
	$(COMPOSE) --profile test run --build --no-deps --rm test ruff check .

test:
	$(COMPOSE) --profile test run --build --rm test

docs:
	$(COMPOSE) run --build --no-deps --rm -v "$(CURDIR):/app" api python -m app.scripts.export_openapi

docs-check:
	$(COMPOSE) run --build --no-deps --rm -v "$(CURDIR):/app" api python -m app.scripts.export_openapi --check