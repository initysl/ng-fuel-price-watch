"""Shared fixtures. DB tests use a throwaway database: <DATABASE_URL db>_test, or TEST_DATABASE_URL.

Without a reachable Postgres, DB tests are skipped locally; set REQUIRE_DB=1 (as CI does) to make
that a failure instead.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import OperationalError

from pipeline import config
from pipeline.db import get_engine, load_seeds, run_migrations


def _test_url() -> URL | None:
    if url := os.getenv("TEST_DATABASE_URL"):
        return make_url(url)
    if config.DATABASE_URL:
        base = make_url(config.DATABASE_URL)
        return base.set(database=f"{base.database}_test")
    return None


def _unavailable(reason: str):
    if os.getenv("REQUIRE_DB") == "1":
        pytest.fail(f"REQUIRE_DB=1 but {reason}")
    pytest.skip(reason)


@pytest.fixture(scope="session")
def db_url() -> URL:
    url = _test_url()
    if url is None:
        _unavailable("no DATABASE_URL or TEST_DATABASE_URL configured")
    if not url.database or not url.database.endswith("_test"):
        pytest.fail(f"refusing to use {url.database!r}: test database name must end with '_test'")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    except OperationalError as exc:
        _unavailable(f"Postgres not reachable: {exc.orig}")
    finally:
        admin.dispose()
    return url


@pytest.fixture(scope="session")
def engine(db_url):
    """Engine on a freshly created test database with migrations and seeds applied."""
    eng = get_engine(db_url.render_as_string(hide_password=False))
    run_migrations(eng)
    load_seeds(eng)
    yield eng
    eng.dispose()
