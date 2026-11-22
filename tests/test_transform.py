"""Transform: each stage on tiny hand-made tables (no xlsx, no database)."""

import datetime as dt

import pandas as pd
import pytest

from pipeline.transform import (
    BadPriceError,
    DuplicateKeyError,
    UnknownStateError,
    check_unique_states,
    clean_prices,
    map_states,
    to_long,
)

MAY_25, APR, MAY = dt.date(2025, 5, 1), dt.date(2026, 4, 1), dt.date(2026, 5, 1)


def wide_table(*rows: list) -> pd.DataFrame:
    """Same shape as RawReport.states / .national: label_raw + one column per month."""
    return pd.DataFrame(list(rows), columns=["label_raw", MAY_25, APR, MAY])


def test_to_long_gives_one_row_per_label_and_month():
    wide = wide_table(["Lagos", 1077.05, 1486.17, 1561.22], ["Abuja", 1029.8, 1553.75, 1602.64])

    long = to_long(wide)

    assert list(long.columns) == ["label_raw", "price_month", "price_raw"]
    assert len(long) == 2 * 3  # labels x months
    lagos = long[long["label_raw"] == "Lagos"].set_index("price_month")["price_raw"]
    assert lagos.to_dict() == {MAY_25: 1077.05, APR: 1486.17, MAY: 1561.22}


def test_to_long_works_on_the_national_row_too():
    long = to_long(wide_table(["AVERAGE", 1027.76, 1532.93, 1596.25]))

    assert len(long) == 3
    assert long["price_month"].tolist() == [MAY_25, APR, MAY]


def test_to_long_keeps_raw_values_untouched():
    long = to_long(wide_table(["Nassarawa ", "1,561.22", None, 1561.2165960582454]))

    assert long["label_raw"].unique().tolist() == ["Nassarawa "]  # spelling and spaces kept
    assert long["price_raw"].tolist()[0] == "1,561.22"  # text stays text: stage 2 cleans it
    assert long["price_raw"].tolist()[2] == 1561.2165960582454  # full precision


def test_clean_prices_turns_text_into_numbers():
    long = to_long(wide_table(["Lagos", "₦1,561.22 ", " 1486.17", 1077]))

    clean = clean_prices(long)

    assert list(clean.columns) == ["label_raw", "price_month", "avg_price_ngn"]
    assert clean["avg_price_ngn"].tolist() == [1561.22, 1486.17, 1077.0]
    assert clean["avg_price_ngn"].dtype == "float64"


def test_clean_prices_keeps_full_precision():
    clean = clean_prices(to_long(wide_table(["Lagos", 1561.2165960582454, 1.0, 2.0])))

    assert clean["avg_price_ngn"].tolist()[0] == 1561.2165960582454  # exact, not rounded


def test_clean_prices_reports_every_bad_cell():
    long = to_long(wide_table(["Lagos", "n/a", 1486.17, 1561.22], ["Kano", 1.0, 2.0, True]))

    with pytest.raises(BadPriceError) as err:
        clean_prices(long)

    message = str(err.value)
    assert "2 price cell(s)" in message
    assert "'Lagos' May-2025: 'n/a'" in message
    assert "'Kano' May-2026: True" in message  # True is not a price, even though 1.0 would be


@pytest.mark.parametrize("bad", ["", "   ", "1.561.22", dt.datetime(2026, 5, 1)])
def test_clean_prices_rejects_values_that_are_not_numbers(bad):
    with pytest.raises(BadPriceError):
        clean_prices(to_long(wide_table(["Lagos", bad, 1.0, 2.0])))


# A tiny alias table: transform gets a dict, so these tests need no database.
ALIASES = {"abuja": "NG-FC", "nassarawa": "NG-NA", "akwa ibom": "NG-AK", "lagos": "NG-LA"}


def clean_table(*rows: list) -> pd.DataFrame:
    """What stage 3 receives: the output of stages 1 and 2."""
    return clean_prices(to_long(wide_table(*rows)))


def test_map_states_resolves_each_spelling_to_its_code():
    clean = clean_table(
        ["Abuja", 1.0, 2.0, 3.0], ["Nassarawa ", 1.0, 2.0, 3.0], ["Akwa-Ibom State", 1.0, 2.0, 3.0]
    )

    mapped = map_states(clean, ALIASES)

    assert mapped["state_code"].unique().tolist() == ["NG-FC", "NG-NA", "NG-AK"]
    assert len(mapped) == 3 * 3  # no rows lost or added


def test_map_states_output_columns():
    mapped = map_states(clean_table(["Lagos", 1077.05, 1486.17, 1561.22]), ALIASES)

    assert list(mapped.columns) == ["label_raw", "state_code", "price_month", "avg_price_ngn"]
    assert mapped["avg_price_ngn"].tolist() == [1077.05, 1486.17, 1561.22]  # prices untouched


def test_map_states_reports_each_unknown_label_once():
    clean = clean_table(
        ["Lagos", 1.0, 2.0, 3.0], ["Atlantis", 1.0, 2.0, 3.0], ["Wakanda State", 1.0, 2.0, 3.0]
    )

    with pytest.raises(UnknownStateError) as err:
        map_states(clean, ALIASES)

    message = str(err.value)
    assert "2 state label(s)" in message
    assert message.count("'Atlantis'") == 1  # 3 rows, but reported once
    assert "'Wakanda State' (normalised: 'wakanda')" in message  # the row to add to the seed
    assert "Lagos" not in message


# Two spellings of one state, to make stage 4 clash on purpose.
CLASHING = {**ALIASES, "fct": "NG-FC"}


def test_check_unique_states_names_the_clashing_labels_once():
    mapped = map_states(
        clean_table(["Abuja", 1.0, 2.0, 3.0], ["FCT", 4.0, 5.0, 6.0], ["Lagos", 1.0, 2.0, 3.0]),
        CLASHING,
    )

    with pytest.raises(DuplicateKeyError) as err:
        check_unique_states(mapped)

    message = str(err.value)
    assert "1 state code(s)" in message
    assert "NG-FC: 'Abuja', 'FCT'" in message  # both labels, so you know what to fix
    assert message.count("NG-FC") == 1  # the clash repeats in 3 months, but it's one problem
    assert "Lagos" not in message


def test_check_unique_states_fails_even_when_prices_match():
    mapped = map_states(clean_table(["Abuja", 1.0, 2.0, 3.0], ["FCT", 1.0, 2.0, 3.0]), CLASHING)

    with pytest.raises(DuplicateKeyError):
        check_unique_states(mapped)


def test_check_unique_states_passes_distinct_states_unchanged():
    mapped = map_states(clean_table(["Abuja", 1.0, 2.0, 3.0], ["Lagos", 1.0, 2.0, 3.0]), ALIASES)

    assert check_unique_states(mapped) is mapped  # the very same table, untouched
