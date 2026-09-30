# Phase 3: cited answers

Implemented on 2026-09-29. **Live model validation is pending an API key.**
66 automated tests pass, including the real IFAB database with a scripted provider.
Scripted responses establish control behavior, not real-model answer accuracy.
The existing 12-question retrieval diagnostic still returns 12/12 relevant-section
hits at five with reranking. The independent 75+ question evaluation remains Phase 4.

## Setup and commands

From the project directory, retain the Phase 2 database and downloaded models:

```sh
make db-migrate
# Edit .env locally: set OPENAI_API_KEY. Never put the key in chat or version control.
.venv/bin/ref ask 'Can you be offside directly from a throw-in?'
.venv/bin/ref ask 'A player recklessly trips an opponent outside the penalty area. What happens?' --json
# Raw, fully local evidence retrieval remains available without a key:
.venv/bin/ref search 'What counts as handball?' --mode hybrid-rerank
REF_TEST_DATABASE=1 .venv/bin/python -m pytest -q
make lint
# Opt-in live diagnostic: eight fixed questions, with paid API calls.
make smoke-answers
```

`ref ask` now generates validated answers; the Phase 2 extractive command moved to
`ref search`. `make ask QUESTION='...'` and `make search QUESTION='...'` are also supported.
Without a key, `ask` reports configuration_error and exits with code 2; it never
presents canned text as a live model answer. Authentication/network/retrieval failures
also exit with code 2. Refusals, clarification and evidence abstentions are normal
structured results, identified by their `status`.

The default is the pinned `gpt-4.1-mini-2025-04-14` model, configurable with `LLM_MODEL`.
This is an initial, unevaluated choice, not a claim that it is the best model for
refereeing. The adapter uses the Responses API with strict JSON Schema, `store:false`,
no tools and no automatic retries. Keys go only to the fixed OpenAI API endpoint;
redirects are rejected. Defaults bound each call to 45 seconds and 5,000 output tokens.
A supported answer makes three calls; a question classified off-topic makes one.

Official implementation references:
- [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Model snapshot, capabilities and pricing](https://developers.openai.com/api/docs/models/gpt-4.1-mini)

## Answer pipeline

1. **Understand.** A structured classifier detects scope and competition, expands
   soccer slang, identifies scenarios and produces up to six short retrieval queries.
   Scenarios request evidence for the offence, restart and sanction; multipart questions
   get separate queries. Historical requests, unrelated questions and missing decisive
   facts receive distinct outcomes.
2. **Retrieve.** Hybrid search and reranking run for each query. Results are interleaved
   so the first subquestion cannot consume the entire context. Full parent sections are
   added to retain conditions stated above a subsection. Subsections and their parents
   fit the context budget together or are omitted together. Up to 32 whole sections and
   100,000 characters are included; sections are never cut through an exception.
3. **Generate.** The model receives only current retrieved text as rule evidence.
   A direct answer uses an Answer section. Scenarios must contain exactly Decision →
   Restart → Disciplinary sanction → Why. Each claim requires evidence IDs and exact
   supporting quotations. Referee judgments are conditional and explicitly labeled.
4. **Check citations.** Unknown IDs, non-verbatim quotations, empty/uncited claims,
   model-written citation markup and incomplete scenario formats are rejected locally.
   Links come from stored source metadata, never model-generated URLs.
5. **Audit support.** A separate model call checks every claim against its quoted text,
   full sections, user facts, exceptions and all parts of the question. Missing, duplicate
   or negative audit decisions withhold the entire draft. This uses the same model in a
   separate call; it is not an independent proof and can share the generator's mistakes.
6. **Recheck freshness and render.** All retrieval passes must share the corpus
   fingerprint. Before exposing an answer, cited evidence IDs must still exist in
   `current_chunks` and the fingerprint must still match. A concurrent replacement
   causes abstention. The renderer adds inline numbered links and quote spans.

No draft tokens are exposed before validation. Phase 6 can stream progress and then
validated content; public API/UI streaming is not part of this phase.

## Citation payload and limits

JSON results contain the outcome, formatted answer sections, Markdown, and citations.
Each citation contains its number, evidence/chunk/section IDs, heading path, edition,
official URL, page range, full source body, verbatim quote, and start/end offsets.
Offsets index Unicode code points in the body, making highlighting reproducible.
HTML amendments retain their exact web anchors and NULL PDF page fields.
The UI citation panel itself is Phase 6 work.

Competition context is detected now, but PL/UEFA/FIFA-specific answers deliberately
return `scope_unavailable` until Phase 5 ingests those regulations and implements
precedence. Generic answers state their IFAB-only scope. Optional IFAB protocols must
not be described as universally adopted. This is not yet a competition-aware product.

When retrieved evidence is insufficient, the app says it could not verify an answer;
it does not claim that the complete rulebook contains no rule. Judgment calls and
missing facts are distinct from off-topic refusals. Neither exact-quote checking nor
an LLM support audit guarantees factual correctness. Phase 4 must measure actual
correctness, citation support, omissions, and refusal accuracy before public claims.

## Telemetry

Migration 003 extends `query_runs` with outcome, pipeline version and diagnostics.
It allows NULL token counts for failed calls whose usage is unknown. One generated
answer run logs its aggregate understanding/generation/audit usage, stage times, corpus
fingerprint, trace ID, model and API cost. Retrieval subqueries do not create duplicate
paid-query rows. Raw user questions, answer drafts and provider error bodies are not
persisted in database telemetry.

The known default model's standard input/cached-input/output prices are $0.40/$0.10/
$1.60 per million tokens, checked on 2026-09-29 at the official model page above.
Costs are estimates from returned token usage at that recorded rate; hardware and
special service-tier surcharges are not included. Unknown model pricing, missing
usage or network failures produce NULL cost, never a fictional zero. Calls completed
before a later validation failure still count toward the run cost. Model load time
is included in end-to-end answer latency when the service is cold.

## Verification status

Passed: 66 tests; lint; real database retrieval/answer transport with a scripted model;
existing retrieval smoke (vector 10/12, hybrid 9/12, hybrid + rerank 12/12). Tests cover
quotation tampering, missing citations, incomplete formats, semantic-audit rejection,
refusals, unavailable competition scope, corpus changes, API errors/refusals/incomplete
outputs, secret-safe errors and cached-token cost arithmetic.

**Not run:** live Responses API generation, live semantic/refusal quality, and account
model access. `make smoke-answers` currently exits with an explicit missing-key message.
Once configured, it writes ignored `work/answer-smoke.json`; inspect the full answers,
not just status/section-hit checks. That small diagnostic is not the Phase 4 golden set.
No public deployment or UI was added. Phase 3 awaits the live check before its final gate.
