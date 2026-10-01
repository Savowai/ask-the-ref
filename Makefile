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

.PHONY: search smoke-answers
search:
	$(VENV)/python -m ask_the_ref.cli search "$$QUESTION"
smoke-answers:
	$(VENV)/python scripts/smoke_answers.py

.PHONY: local-llm local-model
local-llm:
	mkdir -p work/ollama/models work/tmp
	OLLAMA_HOST=127.0.0.1:11436 OLLAMA_MODELS="$(CURDIR)/work/ollama/models" OLLAMA_NO_CLOUD=1 OLLAMA_NUM_PARALLEL=1 TMPDIR="$(CURDIR)/work/tmp" ollama serve
local-model:
	OLLAMA_HOST=127.0.0.1:11436 ollama pull qwen2.5:7b

.PHONY: local-llm-cpu
local-llm-cpu:
	LLAMA_ARG_DEVICE=none LLAMA_ARG_KV_OFFLOAD=0 $(MAKE) local-llm

.PHONY: web-corpus web-install web-dev web-build
web-corpus:
	$(VENV)/python scripts/export_web_corpus.py
web-install:
	cd apps/web && npm install
web-dev:
	cd apps/web && npm run dev
web-build:
	cd apps/web && npm run build
