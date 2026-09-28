-- Synthetic fixtures only; rollback leaves the user's database unchanged.
\set ON_ERROR_STOP on
BEGIN;
INSERT INTO rulebooks(id,title,authority,competition_scope,edition,effective_from,
 source_url,discovery_url,sha256,last_checked_at,status)
VALUES ('schema-test','Synthetic test','IFAB',ARRAY['generic'],'test',CURRENT_DATE,
 'https://example.org/rules','https://example.org',repeat('a',64),now(),'ready');
INSERT INTO chunks(rulebook_id,edition,section_key,kind,law_article,section_title,
 heading_path,body,page_start,page_end,source_url,section_url)
VALUES ('schema-test','test','law-1','section','1','Synthetic test',ARRAY['Test','Law 1'],
 'synthetic test rule',1,1,'https://example.org/rules','https://example.org/rules#law-1');
DO $$
BEGIN
 IF (SELECT count(*) FROM current_chunks WHERE rulebook_id='schema-test') <> 1 THEN
   RAISE EXCEPTION 'Current corpus view did not expose valid chunk';
 END IF;
 BEGIN
  UPDATE chunks SET edition='obsolete' WHERE rulebook_id='schema-test';
  RAISE EXCEPTION 'Mixed edition unexpectedly allowed';
 EXCEPTION WHEN foreign_key_violation THEN NULL;
 END;
 UPDATE rulebooks SET effective_from=CURRENT_DATE+1 WHERE id='schema-test';
 IF EXISTS (SELECT 1 FROM current_chunks WHERE rulebook_id='schema-test') THEN
   RAISE EXCEPTION 'Future book leaked into retrieval';
 END IF;
 UPDATE rulebooks SET effective_from=CURRENT_DATE WHERE id='schema-test';
 UPDATE chunks SET effective_until=CURRENT_DATE WHERE rulebook_id='schema-test';
 IF EXISTS (SELECT 1 FROM current_chunks WHERE rulebook_id='schema-test') THEN
   RAISE EXCEPTION 'Expired provision leaked into retrieval';
 END IF;
 DELETE FROM rulebooks WHERE id='schema-test';
 IF EXISTS (SELECT 1 FROM chunks WHERE rulebook_id='schema-test') THEN
   RAISE EXCEPTION 'Rulebook deletion did not remove its chunks';
 END IF;
END $$;
ROLLBACK;
