BEGIN;
CREATE EXTENSION IF NOT EXISTS vector;

-- One row per rulebook: no editions/history table. Replacement is transactional.
CREATE TABLE rulebooks (
  id text PRIMARY KEY CHECK (id ~ '^[a-z][a-z0-9-]*$'),
  title text NOT NULL,
  authority text NOT NULL CHECK (authority ~ '^[A-Z][A-Z0-9_-]*$'),
  competition_scope text[] NOT NULL CHECK (cardinality(competition_scope) > 0),
  edition text NOT NULL,
  effective_from date NOT NULL,
  effective_until date,
  source_url text NOT NULL CHECK (source_url LIKE 'https://%'),
  discovery_url text NOT NULL CHECK (discovery_url LIKE 'https://%'),
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  last_checked_at timestamptz NOT NULL,
  ingested_at timestamptz,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','ready','blocked')),
  embedding_model text,
  UNIQUE (id, edition),
  CHECK (effective_until IS NULL OR effective_until > effective_from)
);

CREATE TABLE chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rulebook_id text NOT NULL,
  edition text NOT NULL,
  section_key text NOT NULL, -- stable key, e.g. law-12/1/direct-free-kick
  parent_section_key text,
  kind text NOT NULL CHECK (kind IN ('section','definition','protocol','guidance')),
  law_article text NOT NULL,
  section_title text NOT NULL,
  heading_path text[] NOT NULL CHECK (cardinality(heading_path) > 0),
  body text NOT NULL CHECK (length(trim(body)) > 0),
  blocks jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(blocks) = 'array'),
  -- blocks retain paragraph/list/table structure, numbering, cells and source positions.
  page_start integer NOT NULL CHECK (page_start > 0),
  page_end integer NOT NULL CHECK (page_end >= page_start),
  printed_page_labels text[] NOT NULL DEFAULT '{}', -- printed labels != PDF page indices
  source_url text NOT NULL CHECK (source_url LIKE 'https://%'),
  section_url text NOT NULL CHECK (section_url LIKE 'https://%'),
  effective_from date, -- excludes future/expired individual provisions inside a current book
  effective_until date,
  search_document tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', section_title), 'A') ||
    setweight(to_tsvector('english', body), 'B')
  ) STORED,
  embedding vector(1536),
  FOREIGN KEY (rulebook_id, edition) REFERENCES rulebooks(id, edition) ON DELETE CASCADE,
  UNIQUE (rulebook_id, section_key),
  FOREIGN KEY (rulebook_id, parent_section_key)
    REFERENCES chunks(rulebook_id, section_key) DEFERRABLE INITIALLY DEFERRED,
  CHECK (effective_from IS NULL OR effective_until IS NULL OR effective_until > effective_from)
);
CREATE INDEX chunks_search_gin ON chunks USING gin(search_document);
CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw(embedding vector_cosine_ops);
CREATE INDEX chunks_rulebook_idx ON chunks(rulebook_id, law_article);
CREATE INDEX rulebooks_scope_gin ON rulebooks USING gin(competition_scope);

CREATE TABLE chunk_links (
  from_chunk_id uuid NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  to_chunk_id uuid NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  relation text NOT NULL CHECK (relation IN ('defines','references','explicit_variation')),
  evidence text, -- mandatory authorizing provision for competition variation
  PRIMARY KEY (from_chunk_id, to_chunk_id, relation),
  CHECK (from_chunk_id <> to_chunk_id),
  CHECK (relation <> 'explicit_variation' OR length(trim(evidence)) > 0 AND evidence IS NOT NULL)
);

CREATE TABLE query_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  trace_id text,
  competition text NOT NULL,
  retrieval_config text NOT NULL,
  corpus_fingerprint text NOT NULL,
  model text NOT NULL,
  input_tokens integer NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
  output_tokens integer NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
  cost_usd numeric(14,8) CHECK (cost_usd >= 0), -- NULL means unknown, never fake zero
  latency_ms integer NOT NULL CHECK (latency_ms >= 0),
  refused boolean NOT NULL,
  step_timings_ms jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE VIEW current_chunks AS
SELECT c.*, r.title AS rulebook, r.authority, r.competition_scope,
       r.last_checked_at, r.sha256 AS source_sha256
FROM chunks c JOIN rulebooks r ON r.id = c.rulebook_id AND r.edition = c.edition
WHERE r.status = 'ready' AND r.effective_from <= CURRENT_DATE
  AND (r.effective_until IS NULL OR CURRENT_DATE < r.effective_until)
  AND (c.effective_from IS NULL OR c.effective_from <= CURRENT_DATE)
  AND (c.effective_until IS NULL OR CURRENT_DATE < c.effective_until);
COMMIT;
