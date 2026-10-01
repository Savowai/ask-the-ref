# Phase 3: free local answers from the corpus

**No API key, paid model endpoint, subscription or per-query API bill is required.**
The corpus is the source of truth. Local retrieval selects its rule sections; a local
model rewrites that evidence into an answer. The paid provider has been removed.
Generation, query rewriting and the support audit all run through Ollama on this Mac.

## Run

Ollama is already installed on this development machine. Keep the existing Phase 2
Postgres service, corpus and embedding/reranking models. From the project directory:

```sh
make db-up
make db-migrate
make local-llm             # keep running in one terminal; localhost port 11436
# In a second terminal:
make local-model           # one-time ~4.7 GB model download
.venv/bin/ref ask 'Can you be offside directly from a throw-in?'
.venv/bin/ref ask 'A player recklessly trips an opponent outside the penalty area. What happens?' --json
.venv/bin/ref search 'What counts as handball?'  # raw local evidence, no generator needed
make smoke-answers
```

The native Ollama runtime uses Apple GPU acceleration when available. For an environment
where GPU access is unavailable, start `make local-llm-cpu` instead, and set `LLM_NUM_GPU=0`
in `.env`. This explicitly disables device and KV offloading as well as model offloading.
CPU-only answers are slower. Stop the foreground server with Ctrl+C when finished.

`make local-llm` stores models under ignored `work/ollama/models`, uses project-local
temporary files, binds only to localhost, and sets `OLLAMA_NO_CLOUD=1`. The application
calls only `http://127.0.0.1:11436`; redirects and environment proxies are disabled.
There is no paid/cloud fallback. Old API-key or model settings in `.env` are ignored.
No API key should be added or purchased for this project.

The selected model is Qwen2.5 7B, pinned by the downloaded manifest digest in
`local-model.lock.json`. The adapter checks that digest before inference and refuses a
changed/missing model. Internet is needed for the initial model/rulebook downloads and
future rule checks, not for question answering against an installed corpus.

References: [Ollama structured output](https://docs.ollama.com/capabilities/structured-outputs),
[local-only mode and storage](https://docs.ollama.com/faq),
[Qwen2.5 7B model](https://ollama.com/library/qwen2.5:7b).

## Accuracy controls

1. A structured local-model call detects topic, competition, slang, multipart questions
   and scenarios, producing up to six short retrieval queries.
2. Hybrid retrieval and reranking select current evidence for each query. Results are
   interleaved. A subsection and its ancestor conditions fit the context budget together
   or are omitted together. Whole sections are retained; no exception is cut off mid-text.
3. Generation uses only supplied evidence. Every claim needs exact quotations and source
   IDs. Scenarios use Decision → Restart → Disciplinary sanction → Why. Referee judgments
   are conditional and labeled. No draft text is exposed yet.
4. Local validators reject fabricated quotes, unknown citations, missing support and
   incomplete scenario formats. A separate local-model call checks semantic support,
   exceptions, assumptions and coverage of all question parts. A failed check withholds
   the entire answer. The generator and auditor share a model: this is not proof of
   correctness, and Phase 4 must measure their failures.
5. Current corpus fingerprints and evidence IDs are rechecked before rendering numbered
   inline links. Concurrent replacement causes abstention rather than stale citations.

The context includes at most 32 sections and 12,000 body characters, plus metadata and
prompts. The runtime context is explicitly 32,768 tokens; a conservative UTF-8 byte upper
bound rejects a request that might exceed it, reserving output and template overhead.
Oversized requests fail closed instead of silently dropping instructions or exceptions.
The default per-call timeout is 180 seconds and output limit is 3,000 tokens.

JSON citations carry full section text, quote offsets, official URLs, section heading
paths, editions, page ranges and IDs for the Phase 6 highlighting panel. Offsets are
Unicode code points. Official HTML amendments retain exact anchors and NULL PDF pages.
Missing evidence, unclear incidents and off-topic requests have distinct outcomes.
PL/UEFA/FIFA-specific questions remain explicitly unavailable until Phase 5 ingestion.
The website and streaming API are Phase 6 work.

## Cost and hosting

The local corpus, embeddings, reranker and answer model incur **zero paid API charges**.
Telemetry records zero API cost even when a local request fails; unknown token counts
remain NULL. Hardware, electricity, storage and internet access are not included in
that API-cost figure. Raw questions, drafts and error bodies are not stored in database
telemetry. A trace ID, model, corpus fingerprint, stage times and outcome are logged.

A public website still needs somewhere to run the database and inference. A free demo
can use already-owned hardware or suitable free hosting, subject to uptime and resource
limits. This phase does not promise unlimited public traffic at no infrastructure cost,
and no paid hosting will be provisioned without agreeing a deployment plan.

## Verification

Run `REF_TEST_DATABASE=1 .venv/bin/python -m pytest -q` and `make lint` for controls and
real-database integration. Tests verify that no credentials leave the app, requests stay
on the fixed local endpoint, context overflow and changed models fail closed, and invalid
citations/audit failures are withheld. Scripted-provider tests are not model accuracy tests.
`make smoke-answers` exercises the real local model against eight fixed questions and
writes ignored `work/answer-smoke.json`; it is a diagnostic, not the Phase 4 golden set.
