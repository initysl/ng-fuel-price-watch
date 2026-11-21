-- Step 3 (acquire) additions to raw.ingestion_log. A new file, not an edit of 002 (D20).
-- Every statement is re-runnable.

-- Where the raw file lives, relative to landing/raw/ (e.g. 'pms/2025-08/PMS AUGUST 2025.xlsx').
ALTER TABLE raw.ingestion_log ADD COLUMN IF NOT EXISTS landing_path text;

-- Every file we track must say where it is. Only a duplicate may have no copy of its own on disk.
ALTER TABLE raw.ingestion_log DROP CONSTRAINT IF EXISTS ingestion_log_landing_path_check;
ALTER TABLE raw.ingestion_log ADD CONSTRAINT ingestion_log_landing_path_check
    CHECK (status = 'skipped_duplicate' OR landing_path IS NOT NULL);

-- One owner per file content: at most one row that is in progress or loaded.
-- Failed attempts and duplicates may repeat (D17).
CREATE UNIQUE INDEX IF NOT EXISTS ux_ingestion_log_sha256_active
    ON raw.ingestion_log (sha256) WHERE status IN ('running', 'success');

CREATE INDEX IF NOT EXISTS ix_ingestion_log_landing_path ON raw.ingestion_log (landing_path);

COMMENT ON COLUMN raw.ingestion_log.landing_path IS 'Raw file location relative to landing/raw/; NULL only for skipped duplicates.';
COMMENT ON COLUMN raw.ingestion_log.status IS 'running (acquired, not yet loaded) → success | failed; skipped_duplicate (copy of content already held).';
COMMENT ON COLUMN raw.ingestion_log.report_vintage IS 'Report month from the xlsx header (D2), set by acquire and re-checked by extract.';
