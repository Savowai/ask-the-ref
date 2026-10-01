# Ask the Ref web

Next.js public interface for the current rules corpus. The deployed app uses deterministic
section search and exact source excerpts, so it has no model API key or per-query inference cost.
The local Python CLI adds Ollama-based synthesis when desired.

```sh
npm install
npm run dev
```

Regenerate the checked-in deployment corpus after ingestion:

```sh
python ../../scripts/export_web_corpus.py
```
