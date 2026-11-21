"""Extract: NBS-shaped workbooks come out as raw tables; anything else is LayoutChangedError."""

import datetime as dt
from pathlib import Path

import openpyxl
import pytest

from pipeline import config
from pipeline.db import read_seed
from pipeline.extract.excel import LayoutChangedError, extract_report

MAY, APR, MAY_25 = dt.date(2026, 5, 1), dt.date(2026, 4, 1), dt.date(2025, 5, 1)
STATES = sorted(s["state_name"].replace("Federal Capital Territory", "Abuja")
                for s in read_seed(config.SEEDS_DIR / "dim_state.csv"))  # fmt: skip
PRECISE = 0.123456789  # NBS prices carry many decimals; extract must not round them
ZONES = ["South East", "North Central", "North East", "South South", "South West", "North West"]


def nbs_workbook(header_row: int = 2, zones: str = "right") -> openpyxl.Workbook:
    """Same blocks as a real release: title, header, 37 states, AVERAGE, YoY/MoM, zone block."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Fuel MAY 2026"
    ws.cell(1, 1, "PREMIUM MOTOR SPIRIT AVERAGE PRICE PER LITRE MAY 2026 REPORT")
    ws.cell(header_row, 1, "State ")  # real files have the trailing space
    for col, m in enumerate([MAY_25, APR, MAY], start=2):
        ws.cell(header_row, col, dt.datetime(m.year, m.month, 1))
    for k, state in enumerate(STATES, start=1):
        ws.append([state, 1000.0 + k, 1500.0 + k, 1600.0 + k * PRECISE])
    last = ws.max_row
    ws.append(["AVERAGE", 1019.0, 1519.0, 1602.345679])
    ws.append(["Year on Year", None, None, 55.31])
    ws.append(["Month on Month", None, None, 4.13])
    if zones == "right":  # F:G beside the table (most releases)
        anchor_row, anchor_col = header_row, 6
    else:  # column A below the table (Jan 2026)
        anchor_row, anchor_col = ws.max_row + 1, 1
    ws.cell(anchor_row, anchor_col, "Zone")
    ws.cell(anchor_row, anchor_col + 1, "Average Price")
    for k, zone in enumerate(ZONES, start=1):
        ws.cell(anchor_row + k, anchor_col, zone)
        ws.cell(anchor_row + k, anchor_col + 1, 1590.0 + k)
    ws.cell(last, 6, "STATES WITH THE HIGHEST AVERAGE PRICES")  # top/bottom-3: ignored
    return wb


def save(wb: openpyxl.Workbook, tmp_path: Path, name: str = "Fuel_MAY_2026.xlsx") -> Path:
    path = tmp_path / name
    wb.save(path)
    return path


@pytest.mark.parametrize("zones", ["right", "below"])
@pytest.mark.parametrize("header_row", [1, 2, 3, 15])  # every position seen in Step 1
def test_extracts_an_nbs_file_exactly_as_written(tmp_path, header_row, zones):
    wb = nbs_workbook(header_row, zones)
    wb.create_sheet("helper").sheet_state = "hidden"  # hidden sheets are ignored
    report = extract_report(save(wb, tmp_path))

    assert (report.file_name, report.sheet_name) == ("Fuel_MAY_2026.xlsx", "Fuel MAY 2026")
    assert (report.header_row, report.months, report.report_month) == (
        header_row,
        (MAY_25, APR, MAY),
        MAY,
    )
    assert list(report.states.columns) == ["label_raw", MAY_25, APR, MAY]
    assert report.states["label_raw"].tolist() == STATES  # raw labels, not mapped
    assert report.states.iloc[0, 3] == 1600.0 + PRECISE  # full precision, no rounding
    assert report.national.values.tolist() == [["AVERAGE", 1019.0, 1519.0, 1602.345679]]
    assert report.zones["zone_raw"].tolist() == ZONES
    assert report.zones["price_raw"].tolist() == [1591.0, 1592.0, 1593.0, 1594.0, 1595.0, 1596.0]


def _ws(wb):
    return wb["Fuel MAY 2026"]


def no_state_label(wb):
    _ws(wb)["A2"] = "Region"


def months_out_of_order(wb):
    _ws(wb)["B2"] = dt.datetime(2026, 3, 1)


def state_missing(wb):
    _ws(wb).delete_rows(10)


def no_average_row(wb):
    _ws(wb)["A40"] = "Mean"


def blank_state_label(wb):
    _ws(wb)["A5"] = None


def formula_without_cached_value(wb):
    _ws(wb)["D7"] = "=C7*1.05"  # openpyxl saves no cached value, like an unrecalculated file


def second_visible_sheet(wb):
    wb.create_sheet("Sheet2")


def no_zone_block(wb):
    _ws(wb)["F2"] = "Region"


def wrong_zone(wb):
    _ws(wb)["F5"] = "Lagos"


@pytest.mark.parametrize(
    ("breakage", "message"),
    [
        (no_state_label, "no row with 'State'"),
        (months_out_of_order, r"\['Mar-26', 'Apr-26', 'May-26'\] are not \(M-12, M-1, M\)"),
        (state_missing, "expected 37 state rows before AVERAGE, found 36"),
        (no_average_row, "no AVERAGE row"),
        (blank_state_label, "A5 should be a state name"),
        (formula_without_cached_value, r"D7 \(Anambra\) has no cached value"),
        (second_visible_sheet, "expected 1 visible sheet"),
        (no_zone_block, "expected one 'Zone' header cell, found 0"),
        (wrong_zone, "not the 6 zones"),
    ],
    ids=lambda v: v.__name__ if callable(v) else None,
)
def test_a_broken_file_raises_layout_changed(tmp_path, breakage, message):
    wb = nbs_workbook()
    breakage(wb)
    with pytest.raises(LayoutChangedError, match=message) as err:
        extract_report(save(wb, tmp_path))
    assert "Fuel_MAY_2026.xlsx" in str(err.value)  # the error names the file


def test_a_file_that_is_not_an_xlsx_raises_layout_changed(tmp_path):
    path = tmp_path / "PMS_Report_MAY_2026.xlsx"
    path.write_bytes(b"%PDF-1.7 saved with the wrong extension")
    with pytest.raises(LayoutChangedError, match="not a readable xlsx"):
        extract_report(path)


REAL_PMS = config.LANDING_DIR / "pms"


@pytest.mark.skipif(not REAL_PMS.is_dir(), reason="landing/ is gitignored; real files are local")
def test_every_real_nbs_file_extracts_and_its_average_is_the_mean_of_its_states():
    """Blueprint 'done when'. The mean check proves the right 37 rows were read (Step 1: 57/57)."""
    files = sorted(REAL_PMS.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]/*.xlsx"))
    assert len(files) >= 19
    for f in files:
        report = extract_report(f)
        assert f"{report.report_month:%Y-%m}" == f.parent.name, f.name
        for month in report.months:
            mean = report.states[month].astype(float).mean()
            assert abs(mean - float(report.national[month].iloc[0])) < 1e-9, (f.name, month)
