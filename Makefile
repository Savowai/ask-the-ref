PYTHON ?= python3
VENV := .venv/bin
.DEFAULT_GOAL := help
.PHONY: help setup db-up db-down db-check sources download test lint
help:
	@echo "setup | db-up | db-down | db-check | db-test | sources | download [SOURCE=ifab] | models | corrections | db-migrate | parse | ingest | ask | test | lint"
setup:
	$(PYTHON) -m venv .venv
	$(VENV)/python -m pip install --no-cache-dir -r requirements.lock
	$(VENV)/python -m pip install --no-deps -e .
	@test -f .env || cp .env.example .env
db-up:
	docker compose up -d --wait db
db-down:
	docker compose down
db-check:
	docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' < scripts/check_db.sql
sources:
	$(VENV)/python -m ask_the_ref.download --list
download:
	$(VENV)/python -m ask_the_ref.download $(if $(SOURCE),--source $(SOURCE),)
test:
	$(VENV)/python -m pytest -q
lint:
	$(VENV)/ruff check backend tests scripts

.PHONY: db-test
db-test:
	docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' < scripts/check_db_behavior.sql

.PHONY: models corrections parse db-migrate ingest ask
models:
	$(VENV)/python -m ask_the_ref.cli models
corrections:
	$(VENV)/python -m ask_the_ref.cli corrections
parse:
	$(VENV)/python -m ask_the_ref.cli parse
db-migrate:
	$(VENV)/python -m ask_the_ref.cli migrate
ingest:
	$(VENV)/python -m ask_the_ref.cli ingest
ask:
	$(VENV)/python -m ask_the_ref.cli ask "$$QUESTION"
