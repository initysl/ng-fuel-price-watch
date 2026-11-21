# Acquire (Step 3): register the raw files dropped into landing/, exactly once.

import argparse
import datetime as dt
import hashlib
import logging
import stat
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Connection, Engine, RowMapping, text

from pipeline import config
from pipeline.db import get_engine
from pipeline.extract.excel import read_report_month

log = logging.getLogger(__name__)

# D5: only the xlsx is loaded. PDFs may sit next to it for reference; they are not tracked.
IGNORED_SUFFIXES = {".pdf"}


class RawFileModifiedError(RuntimeError):
    """A file on disk no longer matches the hash logged when it was acquired (D3)."""


@dataclass(frozen=True)
class PendingFile:
    """A registered file waiting for extract → load."""

    file_id: int
    path: Path
    sha256: str
    file_name: str
    report_vintage: dt.date | None


@dataclass
class AcquireResult:
    pending: list[PendingFile] = field(default_factory=list)
    registered: int = 0  # new files logged this run
    duplicates: int = 0  # skipped_duplicate rows written this run


# ── Hashing ──────────────────────────────────────────────────────────────────


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _modified(path: Path, expected: str, actual: str) -> RawFileModifiedError:
    return RawFileModifiedError(
        f"{path} changed after it was logged (sha256 {expected[:12]}… → {actual[:12]}…). "
        "Raw files are never edited: restore or re-download the original (D3)."
    )


def verify_raw_file(path: Path, expected_sha256: str) -> None:
    """D3: call before every (re)processing of a logged file."""
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise _modified(path, expected_sha256, actual)


# ── ingestion_log ────────────────────────────────────────────────────────────

_INSERT = text(
    "INSERT INTO raw.ingestion_log (product_code, archive_name, file_name, sha256, "
    "file_size_bytes, report_vintage, status, landing_path, finished_at) VALUES (:product_code, "
    ":archive_name, :file_name, :sha256, :file_size_bytes, :report_vintage, :status, "
    ":landing_path, :finished_at)"
)


def _log_file(
    conn: Connection,
    *,
    status: str,
    product: str,
    sha: str,
    path: Path,
    landing_path: str,
    file_name: str | None = None,
    archive_name: str | None = None,
    report_vintage: dt.date | None = None,
) -> None:
    conn.execute(
        _INSERT,
        {
            "product_code": product,
            "archive_name": archive_name,
            "file_name": file_name or path.name,
            "sha256": sha,
            "file_size_bytes": path.stat().st_size,
            "report_vintage": report_vintage,
            "status": status,
            "landing_path": landing_path,
            "finished_at": dt.datetime.now(dt.UTC) if status != "running" else None,
        },
    )


def _latest_for_path(conn: Connection, landing_path: str) -> RowMapping | None:
    return (
        conn.execute(
            text(
                "SELECT * FROM raw.ingestion_log WHERE landing_path = :p "
                "ORDER BY file_id DESC LIMIT 1"
            ),
            {"p": landing_path},
        )
        .mappings()
        .first()
    )


def _content_owner(conn: Connection, sha: str) -> RowMapping | None:
    """The row that already holds this content, if any (duplicate rows never own content)."""
    return (
        conn.execute(
            text(
                "SELECT landing_path FROM raw.ingestion_log "
                "WHERE sha256 = :sha AND status <> 'skipped_duplicate' ORDER BY file_id LIMIT 1"
            ),
            {"sha": sha},
        )
        .mappings()
        .first()
    )


def pending_files(
    engine: Engine, product: str = "PMS", landing_dir: Path = config.LANDING_DIR
) -> list[PendingFile]:
    """Every acquired file not yet loaded, oldest report first."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT file_id, landing_path, sha256, file_name, report_vintage "
                "FROM raw.ingestion_log WHERE product_code = :p AND status = 'running' "
                "ORDER BY report_vintage NULLS LAST, file_id"
            ),
            {"p": product},
        ).mappings()
        return [
            PendingFile(
                r["file_id"],
                landing_dir / r["landing_path"],
                r["sha256"],
                r["file_name"],
                r["report_vintage"],
            )
            for r in rows
        ]


def latest_report_month(engine: Engine, product: str = "PMS") -> dt.date | None:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT max(report_vintage) FROM raw.ingestion_log WHERE product_code = :p"),
            {"p": product},
        ).scalar_one()


# ── Files on disk ────────────────────────────────────────────────────────────


def _make_read_only(path: Path) -> None:
    path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def _iter_raw_files(product_dir: Path) -> Iterator[Path]:
    if not product_dir.is_dir():
        return
    for path in sorted(product_dir.rglob("*")):
        if any(part.startswith(".") for part in path.relative_to(product_dir).parts):
            continue  # hidden and lock files
        if path.is_symlink():
            log.warning("ignoring symlink %s", path)
        elif not path.is_file():
            continue
        elif path.suffix.lower() == ".xlsx":
            yield path
        elif path.suffix.lower() not in IGNORED_SUFFIXES:
            log.warning("ignoring %s: only .xlsx is loaded (unzip releases first)", path.name)


def acquire(
    engine: Engine, product: str = "PMS", landing_dir: Path = config.LANDING_DIR
) -> AcquireResult:
    """Register every file under landing/raw/<product>/ that isn't logged yet.

    Already-logged files are re-hashed (D3); a failed file gets a fresh attempt row.
    """
    result = AcquireResult()
    for path in _iter_raw_files(landing_dir / product.lower()):
        rel = path.relative_to(landing_dir).as_posix()
        sha = sha256_file(path)
        common = {"product": product, "sha": sha, "path": path, "landing_path": rel}
        with engine.begin() as conn:
            latest = _latest_for_path(conn, rel)
            if latest is not None:
                if latest["sha256"] != sha:
                    raise _modified(path, latest["sha256"], sha)
                if latest["status"] == "failed":
                    log.info("retrying %s (last attempt failed)", rel)
                    _log_file(
                        conn,
                        status="running",
                        file_name=latest["file_name"],
                        archive_name=latest["archive_name"],
                        report_vintage=latest["report_vintage"],
                        **common,
                    )
                continue
            if (owner := _content_owner(conn, sha)) is not None:
                log.info("%s is a copy of %s, skipped", rel, owner["landing_path"])
                _log_file(conn, status="skipped_duplicate", **common)
                result.duplicates += 1
                continue
            vintage = read_report_month(path)
            if vintage is None:
                log.warning("%s: no report month found in the header; extract will check it", rel)
            elif path.parent.name != f"{vintage:%Y-%m}":
                log.warning("%s: its header says %s; is it in the right folder?", rel,
                            f"{vintage:%Y-%m}")  # fmt: skip
            _log_file(conn, status="running", report_vintage=vintage, **common)
            result.registered += 1
            log.info("registered %s", rel)
        _make_read_only(path)
    _warn_missing(engine, product, landing_dir)
    result.pending = pending_files(engine, product, landing_dir)
    return result


def _warn_missing(engine: Engine, product: str, landing_dir: Path) -> None:
    with engine.connect() as conn:
        paths = conn.execute(
            text(
                "SELECT DISTINCT landing_path FROM raw.ingestion_log WHERE product_code = :p "
                "AND status <> 'skipped_duplicate'"
            ),
            {"p": product},
        ).scalars()
        for rel in paths:
            if not (landing_dir / rel).is_file():
                log.warning("%s is logged but missing from landing/: restore or re-download", rel)


# ── Entry point ──────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Register xlsx files dropped into landing/.")
    parser.add_argument("--product", default="PMS")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    engine = get_engine()
    try:
        result = acquire(engine, args.product)
        latest = latest_report_month(engine, args.product)
    finally:
        engine.dispose()

    print(f"registered: {result.registered}  duplicates: {result.duplicates}")
    print(f"pending for extract: {len(result.pending)}")
    for f in result.pending:
        month = f"{f.report_vintage:%Y-%m}" if f.report_vintage else "unknown"
        print(f"  {month}  #{f.file_id}  {f.path.relative_to(config.LANDING_DIR)}")
    print(f"latest report month held: {latest:%Y-%m}" if latest else "no reports held yet")


if __name__ == "__main__":
    main()
