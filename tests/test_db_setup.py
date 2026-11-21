"""Schema + seeds against a real Postgres test database."""

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from pipeline.db import load_seeds, run_migrations

pytestmark = pytest.mark.db

SHA_A = "a" * 64
SHA_B = "b" * 64


def scalar(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def new_file(conn, sha=SHA_A, status="success") -> int:
    return conn.execute(
        text(
            "INSERT INTO raw.ingestion_log (file_name, sha256, status) "
            "VALUES ('test.xlsx', :sha, :status) RETURNING file_id"
        ),
        {"sha": sha, "status": status},
    ).scalar_one()


def insert_state_price(conn, file_id, **overrides):
    row = {
        "product_code": "PMS",
        "state_code": "NG-LA",
        "price_month": dt.date(2026, 5, 1),
        "report_vintage": dt.date(2026, 5, 1),
        "avg_price_ngn": 1561.2165960582454,
        "source_file_id": file_id,
    } | overrides
    conn.execute(
        text(
            "INSERT INTO core.fact_fuel_price_state (product_code, state_code, price_month, "
            "report_vintage, avg_price_ngn, source_file_id) VALUES (:product_code, :state_code, "
            ":price_month, :report_vintage, :avg_price_ngn, :source_file_id)"
        ),
        row,
    )


def test_setup_twice_is_idempotent(engine):
    before = {
        t: scalar(engine, f"SELECT count(*) FROM {t}")
        for t in ("core.dim_state", "core.dim_product", "core.state_alias")
    }
    run_migrations(engine)
    load_seeds(engine)
    after = {t: scalar(engine, f"SELECT count(*) FROM {t}") for t in before}
    assert after == before
    assert after["core.dim_state"] == 37


def test_every_state_has_a_canonical_alias(engine):
    missing = scalar(
        engine,
        "SELECT count(*) FROM core.dim_state s WHERE NOT EXISTS "
        "(SELECT 1 FROM core.state_alias a WHERE a.state_code = s.state_code)",
    )
    assert missing == 0


def test_full_precision_price_round_trips(engine):
    with engine.connect() as conn:
        trans = conn.begin()
        insert_state_price(conn, new_file(conn))
        stored = conn.execute(text("SELECT avg_price_ngn FROM core.fact_fuel_price_state")).scalar()
        rounded = conn.execute(
            text("SELECT round(CAST(980.3549999999999 AS float8)::numeric(14,6), 2)")
        ).scalar()
        trans.rollback()
    assert str(stored) == "1561.216596"
    assert str(rounded) == "980.36"  # matches NBS / Excel display (D4)


@pytest.mark.parametrize(
    "overrides",
    [
        {"avg_price_ngn": 0},
        {"price_month": dt.date(2026, 5, 15)},  # not first of month
        {"price_month": dt.date(2026, 6, 1)},  # after its report vintage
        {"state_code": "NG-XX"},  # unknown state
        {"product_code": "XYZ"},  # unknown product
    ],
    ids=["price-zero", "mid-month", "future-month", "unknown-state", "unknown-product"],
)
def test_fact_constraints_reject_bad_rows(engine, overrides):
    with pytest.raises(IntegrityError), engine.begin() as conn:
        insert_state_price(conn, new_file(conn), **overrides)


def test_duplicate_successful_load_is_rejected_but_retries_are_allowed(engine):
    with engine.connect() as conn:
        trans = conn.begin()
        conn.execute(
            text(
                "INSERT INTO raw.ingestion_log (file_name, sha256, status, error_message) "
                "VALUES ('f.xlsx', :sha, 'failed', 'boom')"
            ),
            {"sha": SHA_B},
        )
        new_file(conn, SHA_B, "skipped_duplicate")
        new_file(conn, SHA_B, "success")  # a failed + a skipped row don't block a success
        with pytest.raises(IntegrityError):
            new_file(conn, SHA_B, "success")  # but a second success does
        trans.rollback()


@pytest.mark.parametrize(
    ("sha", "status"),
    [(SHA_A, "done"), ("xyz", "success"), (SHA_A, "failed")],
    ids=["bad-status", "bad-hash", "failed-without-error-message"],
)
def test_ingestion_log_constraints(engine, sha, status):
    with pytest.raises(IntegrityError), engine.begin() as conn:
        new_file(conn, sha, status)


def test_aggregate_area_must_match_level(engine):
    with pytest.raises(IntegrityError), engine.begin() as conn:
        fid = new_file(conn)
        conn.execute(
            text(
                "INSERT INTO core.fact_fuel_price_aggregate (product_code, level, area, "
                "price_month, report_vintage, avg_price_ngn, source_file_id) VALUES "
                "('PMS', 'national', 'South West', '2026-05-01', '2026-05-01', 1596.25, :fid)"
            ),
            {"fid": fid},
        )
