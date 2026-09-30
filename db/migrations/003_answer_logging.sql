BEGIN;
-- Unknown token counts (e.g. a timed-out paid request) must not be reported as zero.
ALTER TABLE query_runs ALTER COLUMN input_tokens DROP NOT NULL;
ALTER TABLE query_runs ALTER COLUMN output_tokens DROP NOT NULL;
ALTER TABLE query_runs ADD COLUMN IF NOT EXISTS outcome text;
ALTER TABLE query_runs ADD COLUMN IF NOT EXISTS pipeline_version text;
ALTER TABLE query_runs ADD COLUMN IF NOT EXISTS diagnostics jsonb NOT NULL DEFAULT '{}'::jsonb;
COMMIT;
