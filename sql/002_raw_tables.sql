-- raw.ingestion_log: one row per source file per processing attempt.
-- Created before core because the fact tables reference it (source_file_id).
CREATE TABLE IF NOT EXISTS raw.ingestion_log (
    file_id         bigserial   PRIMARY KEY,
    product_code    text        NOT NULL DEFAULT 'PMS',
    source_url      text,                                   -- NULL for manual drop-ins
    archive_name    text,                                   -- zip the file came in, if any (D13)
    file_name       text        NOT NULL,
    sha256          text        NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    file_size_bytes bigint      CHECK (file_size_bytes >= 0),
    downloaded_at   timestamptz NOT NULL DEFAULT now(),
    report_vintage  date        CHECK (report_vintage = date_trunc('month', report_vintage)),
    status          text        NOT NULL
                                CHECK (status IN ('running', 'success', 'failed', 'skipped_duplicate')),
    rows_loaded     integer     CHECK (rows_loaded >= 0),
    error_message   text,
    finished_at     timestamptz,
    CHECK (status <> 'failed' OR error_message IS NOT NULL)
);

-- sha256 is deliberately NOT unique: a failed file must be retryable and a duplicate must be
-- loggable. Only one *successful* load per file content is allowed.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ingestion_log_sha256_success
    ON raw.ingestion_log (sha256) WHERE status = 'success';
CREATE INDEX IF NOT EXISTS ix_ingestion_log_sha256 ON raw.ingestion_log (sha256);

COMMENT ON TABLE  raw.ingestion_log IS 'Every source file seen by the pipeline and what happened to it.';
COMMENT ON COLUMN raw.ingestion_log.sha256 IS 'SHA-256 of the file as downloaded (inner file for zips); re-verified before reprocessing (D3).';
COMMENT ON COLUMN raw.ingestion_log.report_vintage IS 'Report reference month, read from the file content (D2); NULL until extracted.';
