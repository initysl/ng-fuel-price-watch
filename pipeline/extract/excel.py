"""Excel helpers. Step 4 builds the full extractor on these; acquire only needs the report month."""

import datetime as dt
import io
import logging
import warnings
from pathlib import Path

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

log = logging.getLogger(__name__)


def find_header_row(ws: Worksheet) -> int | None:
    """D1: the header is the first row whose B:D hold three dates and whose A reads 'State'."""
    for number, row in enumerate(ws.iter_rows(max_col=4, values_only=True), start=1):
        label, *months = (*row, None, None, None, None)[:4]
        if (
            isinstance(label, str)
            and label.strip().lower() == "state"
            and all(isinstance(m, dt.datetime) for m in months)
        ):
            return number
    return None


def read_report_month(source: Path | bytes) -> dt.date | None:
    """Report month (D2): the latest of the three header dates, as a first-of-month date.

    Returns None when the file is not a readable xlsx or the header is not found. Acquire uses
    this only to file a download in the right folder; extract re-derives it strictly and fails
    loudly on layout drift.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # openpyxl warns about external links, validation
            wb = openpyxl.load_workbook(
                io.BytesIO(source) if isinstance(source, bytes) else source, data_only=True
            )
    except Exception as exc:  # not an xlsx, or a corrupt one: extract reports it properly
        log.debug("could not open workbook: %s", exc)
        return None
    try:
        visible = [ws for ws in wb.worksheets if ws.sheet_state == "visible"]
        if len(visible) != 1:
            return None
        ws = visible[0]
        header = find_header_row(ws)
        if header is None:
            return None
        latest = max(c.value for c in ws[header][1:4])
        return dt.date(latest.year, latest.month, 1)
    finally:
        wb.close()
