"""Database helpers: engine, schema migrations and seed loading."""

import csv
import logging
from pathlib import Path

from sqlalchemy import Engine, create_engine, text

from pipeline import config

log = logging.getLogger(__name__)

# Load order matters: state_alias references dim_state.
# Each seed is upserted on its primary key, so editing a CSV row and re-running setup updates it.
SEEDS: list[tuple[str, str, tuple[str, ...]]] = [
    ("core.dim_product", "dim_product.csv", ("product_code",)),
    ("core.dim_state", "dim_state.csv", ("state_code",)),
    ("core.state_alias", "state_alias.csv", ("alias_normalised",)),
]


def get_engine(url: str | None = None) -> Engine:
    url = url or config.DATABASE_URL
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
    return create_engine(url, pool_pre_ping=True)


def migration_files(sql_dir: Path = config.SQL_DIR) -> list[Path]:
    """Top-level numbered SQL files (001_*.sql, 002_*.sql, ...) in run order. Marts are separate."""
    return sorted(sql_dir.glob("[0-9][0-9][0-9]_*.sql"))


def run_migrations(engine: Engine, sql_dir: Path = config.SQL_DIR) -> list[str]:
    """Run every migration file in order inside one transaction (Postgres DDL is transactional)."""
    files = migration_files(sql_dir)
    if not files:
        raise FileNotFoundError(f"No migration files found in {sql_dir}")
    with engine.begin() as conn:
        for path in files:
            log.info("running %s", path.name)
            conn.exec_driver_sql(path.read_text(encoding="utf-8"))
    return [p.name for p in files]


def read_seed(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"Seed file {path} is empty")
    return rows


def upsert_sql(table: str, columns: list[str], key: tuple[str, ...]) -> str:
    cols = ", ".join(columns)
    params = ", ".join(f":{c}" for c in columns)
    updates = [c for c in columns if c not in key]
    conflict = (
        f"DO UPDATE SET {', '.join(f'{c} = EXCLUDED.{c}' for c in updates)}"
        if updates
        else "DO NOTHING"
    )
    keys = ", ".join(key)
    return f"INSERT INTO {table} ({cols}) VALUES ({params}) ON CONFLICT ({keys}) {conflict}"


def load_seeds(engine: Engine, seeds_dir: Path = config.SEEDS_DIR) -> dict[str, int]:
    """Upsert every seed CSV; warn about database rows that are no longer in the CSV."""
    counts: dict[str, int] = {}
    with engine.begin() as conn:
        for table, file_name, key in SEEDS:
            rows = read_seed(seeds_dir / file_name)
            conn.execute(text(upsert_sql(table, list(rows[0]), key)), rows)
            in_db = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            if in_db != len(rows):
                log.warning("%s has %d rows but %s has %d", table, in_db, file_name, len(rows))
            counts[table] = in_db
    return counts
