# Ask the Ref

Public, evidence-first Q&A about the football rules in force today.
**Status: Phase 3 uses a free local model and the IFAB corpus. No API key required.**
The public Next.js interface uses deterministic corpus search with exact excerpts, so its
Vercel deployment also has no model key or per-query inference cost.

See [Phase 3 setup, citation checks and verification status](docs/PHASE3.md).

See [Phase 2 setup, source corrections and measured retrieval checks](docs/PHASE2.md).

## Local setup

Requirements: Python 3.12+ (3.13 tested), Docker Engine/Desktop with Compose v2,
and Git. No API key is needed. `ref ask` uses local Ollama; `ref search` returns local corpus excerpts.

```sh
make setup                         # creates .venv and .env if absent
make sources                       # validate/list the manifest offline
make download                      # all five official PDFs; never committed
make db-up                         # PostgreSQL 17 + pgvector; wait for health
make db-check                      # extension, tables and retrieval indexes
make test
make lint
```

On this development machine, Python 3.13 is `/opt/homebrew/bin/python3.13`:
`make setup PYTHON=/opt/homebrew/bin/python3.13`.

To fetch one rulebook: `make download SOURCE=ifab`.
Docker-only downloads: `docker compose --profile tools run --rm tools python -m ask_the_ref.download`.
`make db-down` stops containers without deleting `data/postgres`.
The database is bound to loopback only. The example password is for local development.

Run the public web interface:

```sh
cd apps/web
npm install
npm run dev
```

The web app ships the derived current IFAB section corpus, not the source PDF. Regenerate it
after ingestion with `python scripts/export_web_corpus.py`. Local Ollama synthesis stays in the
Python CLI because the pinned 4.7 GB model cannot run inside a Vercel function.

The initial migration runs automatically on an **empty** Postgres data directory.
Editing it does not migrate an existing database. Subsequent phases must add numbered
migrations and run them explicitly; never delete a user's database to apply changes.

## Folder structure

```text
apps/web/                    Next.js public corpus search and citations
backend/src/ask_the_ref/      sources, parser, retrieval, answering and citation checks
  config.py
  download.py
db/migrations/001_initial.sql
scripts/check_db.sql         database readiness and index assertions
scripts/smoke_answers.py     local-model answer diagnostic (no API key)
scripts/check_db_behavior.sql transactional schema integration checks
tests/test_sources.py        source validity and download safety tests
evals/                       golden set and comparisons (Phase 4)
docs/                        source research and schema contracts
data/raw/                    ignored PDFs and download receipts
data/processed/              ignored derived content (Phase 2)
data/postgres/               ignored local database (created by Docker)
sources.yaml                 editions, applicability, official URLs, SHA-256
requirements.lock            pinned Python dependencies
models.lock.json             exact embedding/reranker revisions
compose.yaml
Dockerfile
Makefile
.env.example
```

## Database contract

`rulebooks`: one active edition per id, authority, competition scopes, applicability
interval, official/discovery URLs, hash, last check, ingestion status, embedding model.

`chunks`: composite foreign key to the book's edition, stable section key and parent
section key, full heading path, law/article, title, structured JSON blocks (paragraphs,
numbered lists and tables), text, PDF page range and printed page labels, source and
exact-section URLs, provision validity dates, English tsvector, vector(384).
Official HTML corrections have NULL PDF page fields.
`current_chunks` joins authority/scope metadata and excludes non-ready, future and
expired books/provisions. Retrieval must use this view.

`chunk_links`: definitions, cross-references and explicit competition variations.
Variation links require supporting evidence; this is storage, not implemented precedence logic.
`query_runs`: trace/config/corpus/model identifiers, token counts, latency, step timings,
refusal flag and cost. Local API cost is zero; unknown token usage is NULL; no raw user questions are stored by default.
Migration 003 adds generation outcome, pipeline version and diagnostics.

Full-text GIN and cosine HNSW indexes support hybrid retrieval. Migration 002
selects native 384-dimensional MiniLM embeddings. Changing model/dimensions requires
a migration and re-embedding the complete corpus.

Implemented replacement contract: validate and embed the replacement first;
then in one transaction lock the rulebook, delete its chunks (links cascade), update
its metadata and insert all new chunks. Mark ready only after validation. Roll back
on any error. Never archive obsolete text or serve a partly replaced book. Old files
use the same `data/raw/<id>.pdf` path and are overwritten after download validation.

## Sources and currentness

See `sources.yaml` and `docs/SOURCES.md`. Research checked on **2026-09-28**.
The downloader checks effective dates, official host allowlists on every redirect,
PDF signature/readability, page count, size limit and pinned SHA-256. It writes each
file atomically and records an ignored JSON receipt. A hash change fails closed until
reviewed; a successful download is **not** an ingestion or freshness certification.

Discovery URLs and direct PDF URLs are separate: repeatedly hashing an old PDF URL
cannot discover a new edition. Automated discovery, replacement ingestion and the
weekly PR workflow are scheduled for Phase 6. `make update-rules` is intentionally
not a misleading alias for downloads. Until that phase, currentness is manually verified.
FIFA tournament regulations are scoped additions in Phase 5; FIFA RSTP is not a
universal match regulation. UEFA UCL and UEL remain distinct competition scopes.

A new book using the shared downloader requires only a manifest entry. Arbitrary
uppercase authorities (e.g. MLS) and competition ids are supported. Structure-aware
parser profiles and discovery resolvers will be added in their respective phases.

## Environment and accounts

| Variable | When needed | Purpose |
|---|---|---|
| POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB / POSTGRES_PORT | Phase 1 | Local Compose database |
| DATABASE_URL | Phase 2 onward | Backend connection; keep aligned with Postgres settings |
| LLM_NUM_GPU | Phase 3 | -1 automatic, or 0 with make local-llm-cpu |
| LLM_TIMEOUT_SECONDS / LLM_MAX_OUTPUT_TOKENS | Phase 3 | 180 seconds / 3000 output tokens per local call |
| EMBEDDING_DIMENSIONS | Phase 2 | 384 after migration 002; models pinned in models.lock.json |
| OTEL_EXPORTER_OTLP_ENDPOINT / OTEL_SERVICE_NAME | Phase 6 | Optional tracing exporter |
| NEXT_PUBLIC_API_URL | Phase 6 | Public backend URL; never put secrets in NEXT_PUBLIC variables |

Later deployment needs a Vercel account, a Python backend host and persistent
Postgres with pgvector. Vercel will host the frontend. Provider credentials and
GitHub weekly-workflow permissions will be configured in Phase 6; do not paste keys
into chat or commit them. No external accounts or paid services were created.

## Validation and phase gates

Phase 1: source/download unit tests, lint, live PDF download checks and SQL syntax
validation. Docker Desktop is installed and the Postgres + pgvector container is
healthy. `make db-check` and `make db-test` both passed, including edition consistency,
future/expired rule filtering and cascade deletion. The optional tools image build
has not been tested. To repeat the database checks, run:

```sh
make db-up
make db-check
make db-test
```

Phase 2: IFAB structure-aware parsing, section chunking, hybrid search, cross-encoder,
CLI Q&A. Phase 3: cited answer generation, scenario format and refusals. Phase 4:
75+ golden questions, ablations, retrieval/answer/citation metrics, latency and cost.
Phase 5: other rulebooks and precedence. Phase 6: API/UI/deployment and freshness.
Phase 7: final architecture diagram, real eval table, demo GIF and CI smoke eval.
The limited 12-question Phase 2 diagnostic is in docs/PHASE2.md; comprehensive
answer/citation evaluation remains Phase 4.
