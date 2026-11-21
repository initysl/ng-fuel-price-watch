"""Acquire: registering files dropped into landing/, and reading their report month."""

import datetime as dt
import io
import stat
from pathlib import Path

import openpyxl
import pytest
from sqlalchemy import text

from pipeline import acquire as acq
from pipeline import config
from pipeline.extract.excel import read_report_month

AUG, SEP, MAY = dt.date(2025, 8, 1), dt.date(2025, 9, 1), dt.date(2026, 5, 1)


def make_xlsx(month: dt.date, header_row: int = 1) -> bytes:
    """A tiny NBS-shaped workbook: 'State' + (M-12, M-1, M) date headers + one state row."""
    prev = (month - dt.timedelta(days=1)).replace(day=1)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(header_row, 1, "State")
    for col, m in enumerate([month.replace(year=month.year - 1), prev, month], start=2):
        ws.cell(header_row, col, dt.datetime(m.year, m.month, 1))
    ws.append(["Abia", 1000.0, 1100.0, 1200.0 + header_row])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def put(landing: Path, rel: str, data: bytes) -> Path:
    path = landing / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def log_rows(engine):
    with engine.connect() as conn:
        sql = text("SELECT * FROM raw.ingestion_log ORDER BY file_id")
        return conn.execute(sql).mappings().all()


@pytest.fixture
def landing(tmp_path) -> Path:
    root = tmp_path / "landing"
    (root / "pms").mkdir(parents=True)
    return root


@pytest.fixture
def db(engine):
    """The session test database with an empty ingestion log."""
    with engine.begin() as conn:  # DELETE, not TRUNCATE: instant on tiny tables
        for table in ("core.fact_fuel_price_state", "core.fact_fuel_price_aggregate"):
            conn.execute(text(f"DELETE FROM {table}"))
        conn.execute(text("DELETE FROM raw.ingestion_log"))
    return engine


# ── registering files ────────────────────────────────────────────────────────


@pytest.mark.db
def test_files_are_registered_once(db, landing):
    """Blueprint 'done when', for drop-ins: running twice registers once."""
    xlsx = put(landing, "pms/2025-08/PMS AUGUST 2025.xlsx", make_xlsx(AUG, header_row=15))

    first = acq.acquire(db, landing_dir=landing)
    assert (first.registered, first.duplicates) == (1, 0)
    assert [(p.path, p.report_vintage) for p in first.pending] == [(xlsx, AUG)]
    assert [r["status"] for r in log_rows(db)] == ["running"]
    assert not xlsx.stat().st_mode & stat.S_IWUSR  # raw files are made read-only

    second = acq.acquire(db, landing_dir=landing)
    assert (second.registered, second.duplicates) == (0, 0)
    assert second.pending == first.pending
    assert len(log_rows(db)) == 1


@pytest.mark.db
def test_only_xlsx_files_are_tracked(db, landing, caplog):
    pdf = put(landing, "pms/2025-08/PMS Report AUGUST 2025.pdf", b"%PDF-1.7 aug")
    put(landing, "pms/2025-08/.~lock.PMS AUGUST 2025.xlsx#", b"lock file")  # hidden
    put(landing, "pms/2025-09/PMS_Report_SEP_2025.zip", b"PK zip")

    result = acq.acquire(db, landing_dir=landing)
    assert (result.registered, result.pending, log_rows(db)) == (0, [], [])
    assert pdf.stat().st_mode & stat.S_IWUSR  # untracked files are left alone
    assert ".pdf" not in caplog.text  # PDFs are expected next to the xlsx (D5): no noise
    assert "ignoring PMS_Report_SEP_2025.zip" in caplog.text  # a zip is a mistake: say so


@pytest.mark.db
def test_a_copy_of_a_known_file_is_logged_once_as_duplicate(db, landing):
    data = make_xlsx(AUG)
    put(landing, "pms/2025-08/a.xlsx", data)
    acq.acquire(db, landing_dir=landing)
    put(landing, "pms/2025-08/a (1).xlsx", data)  # e.g. downloaded twice

    again = acq.acquire(db, landing_dir=landing)
    assert (again.registered, again.duplicates, len(again.pending)) == (0, 1, 1)
    assert acq.acquire(db, landing_dir=landing).duplicates == 0  # the copy is now known


@pytest.mark.db
def test_an_edited_raw_file_is_refused(db, landing):
    path = put(landing, "pms/2025-08/a.xlsx", make_xlsx(AUG))
    acq.acquire(db, landing_dir=landing)
    path.chmod(0o644)
    path.write_bytes(make_xlsx(SEP))

    with pytest.raises(acq.RawFileModifiedError, match="a.xlsx"):
        acq.acquire(db, landing_dir=landing)
    with pytest.raises(acq.RawFileModifiedError):
        acq.verify_raw_file(path, log_rows(db)[0]["sha256"])


@pytest.mark.db
def test_a_failed_file_gets_a_new_attempt(db, landing):
    put(landing, "pms/2025-08/a.xlsx", make_xlsx(AUG))
    acq.acquire(db, landing_dir=landing)
    with db.begin() as conn:
        conn.execute(text("UPDATE raw.ingestion_log SET status = 'failed', error_message = 'boom'"))

    retry = acq.acquire(db, landing_dir=landing)
    rows = log_rows(db)
    assert [r["status"] for r in rows] == ["failed", "running"]
    assert [p.file_id for p in retry.pending] == [rows[1]["file_id"]]


@pytest.mark.db
def test_a_file_in_the_wrong_month_folder_is_flagged(db, landing, caplog):
    put(landing, "pms/2025-09/PMS AUGUST 2025.xlsx", make_xlsx(AUG))
    result = acq.acquire(db, landing_dir=landing)
    assert result.pending[0].report_vintage == AUG  # the content wins, not the folder (D2)
    assert "is it in the right folder?" in caplog.text


# ── report month ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("header_row", [1, 2, 3, 15])  # every position seen in Step 1
def test_read_report_month_finds_the_header_anywhere(header_row):
    assert read_report_month(make_xlsx(MAY, header_row)) == MAY


def test_read_report_month_returns_none_for_unrecognised_files():
    assert read_report_month(b"%PDF-1.7 not a workbook") is None
    wb = openpyxl.Workbook()
    wb.active.append(["Region", dt.datetime(2026, 4, 1), dt.datetime(2026, 5, 1), "x"])
    buf = io.BytesIO()
    wb.save(buf)
    assert read_report_month(buf.getvalue()) is None


REAL_PMS = config.LANDING_DIR / "pms"


@pytest.mark.skipif(not REAL_PMS.is_dir(), reason="landing/ is gitignored; real files are local")
def test_real_nbs_files_report_month_matches_their_folder():
    files = sorted(REAL_PMS.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]/*.xlsx"))
    assert len(files) >= 19
    for f in files:
        month = read_report_month(f)
        assert month is not None and f"{month:%Y-%m}" == f.parent.name, f.name
