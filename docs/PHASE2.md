# Phase 2: IFAB retrieval

Implemented on 2026-09-29. The local corpus has 348 section/definition chunks.
It includes all 17 Laws, VAR, notes and optional protocols, glossary entries and
practical guidelines. FIFA/UEFA/PL PDFs are downloaded but not ingested until Phase 5.

## Reproduce

```sh
make setup PYTHON=/opt/homebrew/bin/python3.13
make db-up
make db-migrate                 # existing Phase 1 DB; safe to repeat
make download SOURCE=ifab
make corrections               # two official HTML replacements with pinned content hashes
make models                    # local models; internet needed only for initial download
make parse                     # inspect ignored data/processed/ifab.json
make ingest                    # embed first, then replace IFAB in one transaction
.venv/bin/ref search 'Can you be offside directly from a throw-in?'
.venv/bin/ref search 'How long may a goalkeeper hold the ball?' --mode hybrid --json
make test
REF_TEST_DATABASE=1 .venv/bin/python -m pytest -q
.venv/bin/python scripts/smoke_retrieval.py
```

Run commands from the project root. `ref search` prints complete retrieved excerpts,
heading paths, edition and source links. It deliberately labels output as retrieved
evidence: there is no generated ruling or off-topic refusal until Phase 3.
`--mode` supports `vector`, `hybrid`, and `hybrid-rerank` (default).
Questions are limited to 128 model tokens. All model caches stay under ignored `work/`.

## Source fidelity

The PDF has no bookmarks. The parser uses an edition/hash-pinned layout profile,
text-matrix baselines (the embedded font bounding boxes are misleading), font roles,
heading numbering and page boundaries. Unknown PDF bytes fail closed. Sections are
not split at token limits; model windows cover the entire text internally and are
mean-pooled for embeddings and max-scored for reranking.

Paragraphs and numbered/bulleted items retain text, indentation and page geometry.
The continued Law 14 penalty table retains ten rows, three named columns, and both
page locations. Source metadata is joined from `rulebooks` rather than redundantly
copied into every database row. Definition chunks link to sections containing their
terms. Handball and interfering with play get definition chunks from their law text.

The Law-changes comparison pages (166–193) are excluded. The future July 2027
captain-only mandate is excluded; the currently optional guidelines remain.
Diagrams are available via the original page link; the system does not infer spatial
facts from illustrations. A new edition requires parser-profile review, including
visual/table checks. Dropping in a source config supports downloads; a different
publisher's layout still needs a parsing adapter.

**Official correction:** the main PDF hash currently omits amendments approved on
28 April 2026 to Law 3.1 and Law 7.5. `sources.yaml` records the current official web
sections and normalized content hashes. Downloaded correction receipts live in
ignored `data/raw`. Ingestion replaces those two sections outright. Their citations
point to the exact web anchors and their PDF page fields are NULL—no invented page.
A changed correction hash stops download/ingestion pending review.

Official references:
- [IFAB Law 3.1](https://www.theifab.com/laws/latest/the-players/#number-of-players)
- [IFAB Law 7.5](https://www.theifab.com/laws/latest/the-duration-of-the-match/#abandoned-match)
- [IFAB amendment notice](https://www.theifab.com/law-changes/latest/)

## Retrieval and replacement

Embedding: `sentence-transformers/all-MiniLM-L6-v2`, native 384 dimensions.
Cross-encoder: `cross-encoder/ms-marco-MiniLM-L-6-v2`.
Exact revisions are in `models.lock.json`; runtime uses cached files only and
`trust_remote_code=False`. There are no paid API calls in Phase 2.

Migration 002 changes the empty Phase 1 vector column from 1536 to 384 dimensions.
It refuses conversion if existing incompatible embeddings are present. It also
allows NULL pages for official HTML amendments and stores a corpus fingerprint.
The GIN full-text and HNSW cosine indexes remain in place. Small corpora may use an
exact sequential scan because PostgreSQL's planner can find that cheaper.

Each search gets 30 vector hits and (except vector-only mode) 30 full-text hits.
English full-text terms use OR to avoid dropping matches on conversational words.
RRF with k=60 merges ranks, then the cross-encoder scores the top 30 candidates.
Only `current_chunks` is queried. A repeatable-read snapshot keeps a query consistent
while ingestion replaces a book. Related definitions are returned separately from
ranked results. Query logs record corpus/model/config, stage timings and zero API
cost; hardware/electricity cost and cold model loading are not included.

Ingestion validates and embeds before taking a per-book advisory lock. Deletion of
the old book and insertion of every replacement chunk/link happen in one transaction.
The database integration test intentionally causes an insert failure after deletion
and verifies the previous corpus is unchanged. Re-ingestion does not grow the corpus.

## Small retrieval diagnostic

Twelve manually selected questions in `scripts/smoke_retrieval.py`; measured locally
on 2026-09-29, after loading models. “Hit” means **any** accepted target section was
in the first five results. This is not full multi-evidence recall, answer correctness,
citation faithfulness, a held-out benchmark, or the Phase 4 evaluation.

| Configuration | Hits at 5 | Mean reciprocal rank at 5 | Median latency |
|---|---:|---:|---:|
| Vector | 10/12 | 0.628 | 20 ms |
| Hybrid | 9/12 | 0.646 | 23 ms |
| Hybrid + rerank | 12/12 | 0.958 | 470 ms |

Raw results, including misses, are written to ignored `work/retrieval-smoke.json`.
The worse hybrid result is retained rather than hidden. Phase 4 will test a larger
independent golden set and measure answer/citation quality once generation exists.

Validation: 29 tests passed, including actual downloaded PDF parsing, table and
footnote preservation, correction replacement, rollback, and current-corpus checks;
lint and live database contract checks passed. Without downloaded PDFs or explicit
`REF_TEST_DATABASE=1`, the corresponding integration tests skip with a reason.
The optional Docker tools image has not been built in this phase; the tested path
is local Python plus the PostgreSQL Docker service.
