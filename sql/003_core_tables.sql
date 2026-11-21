-- core: star schema. Dimensions first, then facts.

-- ── Dimensions ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.dim_product (
    product_code text PRIMARY KEY CHECK (product_code ~ '^[A-Z]{3}$'),
    product_name text NOT NULL UNIQUE,
    unit         text NOT NULL
);

CREATE TABLE IF NOT EXISTS core.dim_state (
    state_code text PRIMARY KEY CHECK (state_code ~ '^NG-[A-Z]{2}$'),   -- ISO 3166-2
    state_name text NOT NULL UNIQUE,
    zone       text NOT NULL CHECK (zone IN ('North Central', 'North East', 'North West',
                                             'South East', 'South South', 'South West'))
);

-- Lookup used by transform to resolve raw spellings; facts never join to it.
CREATE TABLE IF NOT EXISTS core.state_alias (
    alias_normalised text PRIMARY KEY CHECK (alias_normalised ~ '^[a-z]+( [a-z]+)*$'),
    state_code       text NOT NULL REFERENCES core.dim_state (state_code)
);

-- ── Facts ───────────────────────────────────────────────────────────────────
-- Grain: one product x one state x one month x one report vintage.
CREATE TABLE IF NOT EXISTS core.fact_fuel_price_state (
    product_code   text          NOT NULL REFERENCES core.dim_product (product_code),
    state_code     text          NOT NULL REFERENCES core.dim_state (state_code),
    price_month    date          NOT NULL CHECK (price_month = date_trunc('month', price_month)),
    report_vintage date          NOT NULL CHECK (report_vintage = date_trunc('month', report_vintage)),
    avg_price_ngn  numeric(14,6) NOT NULL CHECK (avg_price_ngn > 0),
    source_file_id bigint        NOT NULL REFERENCES raw.ingestion_log (file_id),
    loaded_at      timestamptz   NOT NULL DEFAULT now(),
    PRIMARY KEY (product_code, state_code, price_month, report_vintage),
    CHECK (price_month <= report_vintage)
);

-- Grain: one product x one area (Nigeria or a zone) x one month x one report vintage.
-- Separate from states so national/zone rows can never be summed with state rows.
CREATE TABLE IF NOT EXISTS core.fact_fuel_price_aggregate (
    product_code   text          NOT NULL REFERENCES core.dim_product (product_code),
    level          text          NOT NULL CHECK (level IN ('national', 'zone')),
    area           text          NOT NULL,
    price_month    date          NOT NULL CHECK (price_month = date_trunc('month', price_month)),
    report_vintage date          NOT NULL CHECK (report_vintage = date_trunc('month', report_vintage)),
    avg_price_ngn  numeric(14,6) NOT NULL CHECK (avg_price_ngn > 0),
    source_file_id bigint        NOT NULL REFERENCES raw.ingestion_log (file_id),
    loaded_at      timestamptz   NOT NULL DEFAULT now(),
    PRIMARY KEY (product_code, level, area, price_month, report_vintage),
    CHECK (price_month <= report_vintage),
    CHECK ((level = 'national' AND area = 'Nigeria')
        OR (level = 'zone' AND area IN ('North Central', 'North East', 'North West',
                                        'South East', 'South South', 'South West')))
);

CREATE INDEX IF NOT EXISTS ix_fact_state_source_file     ON core.fact_fuel_price_state (source_file_id);
CREATE INDEX IF NOT EXISTS ix_fact_aggregate_source_file ON core.fact_fuel_price_aggregate (source_file_id);

COMMENT ON TABLE  core.fact_fuel_price_state IS 'NBS average retail price per state, month and report vintage (never overwritten by revisions).';
COMMENT ON COLUMN core.fact_fuel_price_state.price_month IS 'First day of the month the price refers to.';
COMMENT ON COLUMN core.fact_fuel_price_state.report_vintage IS 'First day of the report''s reference month (its edition).';
COMMENT ON COLUMN core.fact_fuel_price_state.avg_price_ngn IS 'Full precision as published in the xlsx; round only for display (D4).';
COMMENT ON TABLE  core.fact_fuel_price_aggregate IS 'NBS-published national and zone averages, kept for validation and lineage.';
