\set ON_ERROR_STOP on
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
    RAISE EXCEPTION 'pgvector missing';
  END IF;
  IF to_regclass('public.current_chunks') IS NULL THEN
    RAISE EXCEPTION 'current_chunks missing';
  END IF;
  IF (SELECT count(*) FROM pg_indexes WHERE indexname IN ('chunks_search_gin','chunks_embedding_hnsw')) <> 2 THEN
    RAISE EXCEPTION 'retrieval indexes missing';
  END IF;
END $$;
SELECT count(*) AS current_chunk_count FROM current_chunks;
