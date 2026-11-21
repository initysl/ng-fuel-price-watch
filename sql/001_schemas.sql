-- Three layers: raw (lineage/audit) -> core (star schema) -> mart (views for serving).
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;

COMMENT ON SCHEMA raw  IS 'Lineage and audit of every source file the pipeline has seen.';
COMMENT ON SCHEMA core IS 'Cleaned, conformed data: dimensions and fact tables (star schema).';
COMMENT ON SCHEMA mart IS 'Read-only views for the dashboard, CSV export and insights.';
