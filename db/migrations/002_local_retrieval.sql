BEGIN;
-- Fail closed if an operator tries to mix existing 1536-dimensional vectors with this model.
DO $$ BEGIN
 IF format_type((SELECT atttypid FROM pg_attribute WHERE attrelid='chunks'::regclass AND attname='embedding'),
                (SELECT atttypmod FROM pg_attribute WHERE attrelid='chunks'::regclass AND attname='embedding')) <> 'vector(384)'
    AND EXISTS (SELECT 1 FROM chunks WHERE embedding IS NOT NULL) THEN
   RAISE EXCEPTION 'Existing vectors require an explicit full re-embedding migration';
 END IF;
END $$;
DROP VIEW current_chunks;
DROP INDEX chunks_embedding_hnsw;
ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(384);
ALTER TABLE chunks ALTER COLUMN page_start DROP NOT NULL;
ALTER TABLE chunks ALTER COLUMN page_end DROP NOT NULL;
CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw(embedding vector_cosine_ops);
ALTER TABLE rulebooks ADD COLUMN IF NOT EXISTS content_fingerprint text;
CREATE VIEW current_chunks AS
SELECT c.*, r.title AS rulebook, r.authority, r.competition_scope,
       r.last_checked_at, r.sha256 AS source_sha256
FROM chunks c JOIN rulebooks r ON r.id = c.rulebook_id AND r.edition = c.edition
WHERE r.status = 'ready' AND r.effective_from <= CURRENT_DATE
  AND (r.effective_until IS NULL OR CURRENT_DATE < r.effective_until)
  AND (c.effective_from IS NULL OR c.effective_from <= CURRENT_DATE)
  AND (c.effective_until IS NULL OR CURRENT_DATE < c.effective_until);
COMMIT;
