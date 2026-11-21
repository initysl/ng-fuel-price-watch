import datetime as dt
import io
import warnings
from dataclasses import dataclass
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.utils import get_column_letter

N_STATES = 37
ZONES = {"north central", "north east", "north west", "south east", "south south", "south west"}
MONTH_COLS = (1, 2, 3)  # B:D

Rows = list[tuple]


class LayoutChangedError(ValueError):
    """The file doesn't have the layout extract expects (D1, D2, D8, D11)."""


@dataclass(frozen=True)
class RawReport:
    """One file's tables, values exactly as written (cached values for formulas)."""

    file_name: str
    sheet_name: str
    header_row: int  # 1-based, as Excel shows it
    months: tuple[dt.date, dt.date, dt.date]  # (M-12, M-1, M), first of month
    states: pd.DataFrame  # label_raw + one column per month: the 37 state rows
    national: pd.DataFrame  # same columns, one row: the AVERAGE row
    zones: pd.DataFrame  # zone_raw, price_raw: current month only

    @property
    def report_month(self) -> dt.date:
        return self.months[-1]


# Reading the sheet

def _cell(row: tuple, col: int):
    return row[col] if col < len(row) else None


def _text(value) -> str | None:
    """Lower-case text with whitespace collapsed; None for anything that isn't text."""
    return " ".join(value.split()).lower() if isinstance(value, str) else None


def _month(value: dt.datetime) -> dt.date:
    return dt.date(value.year, value.month, 1)


def _add_months(month: dt.date, n: int) -> dt.date:
    year, m0 = divmod(month.year * 12 + month.month - 1 + n, 12)
    return dt.date(year, m0 + 1, 1)


def load_sheet(source: Path | bytes, name: str) -> tuple[str, Rows]:
    """Title and cell values of the workbook's only visible sheet (cached values, D8)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # openpyxl warns about external links, validation
            wb = openpyxl.load_workbook(
                io.BytesIO(source) if isinstance(source, bytes) else source, data_only=True
            )
    except Exception as exc:  # not an xlsx, or a corrupt one
        raise LayoutChangedError(f"{name}: not a readable xlsx ({exc})") from exc
    try:
        visible = [ws for ws in wb.worksheets if ws.sheet_state == "visible"]
        if len(visible) != 1:
            titles = [ws.title for ws in visible]
            raise LayoutChangedError(f"{name}: expected 1 visible sheet, found {titles}")
        return visible[0].title, list(visible[0].iter_rows(values_only=True))
    finally:
        wb.close()


def find_header(rows: Rows) -> int | None:
    """D1: index of the first row with 'State' in column A and three dates in B:D."""
    for i, row in enumerate(rows):
        if _text(_cell(row, 0)) == "state" and all(
            isinstance(_cell(row, c), dt.datetime) for c in MONTH_COLS
        ):
            return i
    return None


def read_report_month(source: Path | bytes) -> dt.date | None:
    """Report month (D2), or None if the file isn't recognised. Used by acquire to file it."""
    try:
        _, rows = load_sheet(source, "workbook")
    except LayoutChangedError:
        return None
    i = find_header(rows)
    return None if i is None else max(_month(rows[i][c]) for c in MONTH_COLS)


# Extracting the blocks

def _require_value(value, name: str, where: str):
    """D8: a price cell must hold a value, not be empty or an uncached formula."""
    if value is None or (isinstance(value, str) and value.startswith("=")):
        raise LayoutChangedError(f"{name}: {where} has no cached value ({value!r})")
    return value


def _price_row(row: tuple, row_no: int, name: str) -> list:
    label = _cell(row, 0)
    return [
        label,
        *(
            _require_value(_cell(row, c), name, f"{get_column_letter(c + 1)}{row_no} ({label})")
            for c in MONTH_COLS
        ),
    ]


def _zone_block(rows: Rows, name: str) -> pd.DataFrame:
    """D11: find the 'Zone' header anywhere (F:G beside the table, or column A below it)."""
    anchors = [
        (i, c) for i, row in enumerate(rows) for c, v in enumerate(row) if _text(v) == "zone"
    ]
    if len(anchors) != 1:
        raise LayoutChangedError(f"{name}: expected one 'Zone' header cell, found {len(anchors)}")
    i, c = anchors[0]
    where = f"{get_column_letter(c + 1)}{i + 1}"
    block = [(_cell(r, c), _cell(r, c + 1)) for r in rows[i + 1 : i + 1 + len(ZONES)]]
    found = {(_text(zone) or "").replace("-", " ") for zone, _ in block}
    if found != ZONES:
        labels = [zone for zone, _ in block]
        raise LayoutChangedError(f"{name}: zone block at {where} lists {labels}, not the 6 zones")
    for zone, price in block:
        _require_value(price, name, f"zone {zone!r}")
    return pd.DataFrame(block, columns=["zone_raw", "price_raw"])


def extract_report(path: Path) -> RawReport:
    """Read one NBS PMS xlsx. Raises LayoutChangedError on anything unexpected."""
    name = path.name
    sheet, rows = load_sheet(path, name)

    h = find_header(rows)
    if h is None:
        raise LayoutChangedError(f"{name}: no row with 'State' in column A and dates in B:D")
    months = tuple(_month(rows[h][c]) for c in MONTH_COLS)
    m = months[-1]
    if months != (_add_months(m, -12), _add_months(m, -1), m):  # D2
        shown = [f"{x:%b-%y}" for x in months]
        raise LayoutChangedError(f"{name}: header months {shown} are not (M-12, M-1, M)")

    # The state table runs from the header to the AVERAGE row (D1).
    avg = next((i for i in range(h + 1, len(rows)) if _text(_cell(rows[i], 0)) == "average"), None)
    if avg is None:
        raise LayoutChangedError(f"{name}: no AVERAGE row below the header (row {h + 1})")
    body = range(h + 1, avg)
    if len(body) != N_STATES:
        raise LayoutChangedError(
            f"{name}: expected {N_STATES} state rows before AVERAGE, found {len(body)}"
        )
    for i in body:
        if not _text(_cell(rows[i], 0)):
            found = _cell(rows[i], 0)
            raise LayoutChangedError(f"{name}: A{i + 1} should be a state name, found {found!r}")

    columns = ["label_raw", *months]
    return RawReport(
        file_name=name,
        sheet_name=sheet,
        header_row=h + 1,
        months=months,
        states=pd.DataFrame([_price_row(rows[i], i + 1, name) for i in body], columns=columns),
        national=pd.DataFrame([_price_row(rows[avg], avg + 1, name)], columns=columns),
        zones=_zone_block(rows, name),
    )
