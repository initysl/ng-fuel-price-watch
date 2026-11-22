import re

import pandas as pd

_STATE_WORD = re.compile(r"\bstate\b")
_SEPARATORS = re.compile(r"[-,.]")


def normalise_state_name(name: str) -> str:
    """Normalise a raw state label for lookup in ``core.state_alias``.

    Lower-case, hyphens/commas/full stops to spaces, drop the word "state", collapse whitespace:
    ``"  Akwa-Ibom State "`` -> ``"akwa ibom"``.
    """
    s = _SEPARATORS.sub(" ", name.lower())
    s = _STATE_WORD.sub(" ", s)
    return " ".join(s.split())


# Stage 1: wide -> long

def to_long(wide: pd.DataFrame) -> pd.DataFrame:
    """One row per (label, month): ``label_raw | price_month | price_raw``.

    Takes a ``RawReport.states`` or ``RawReport.national`` table, whose columns are
    ``label_raw`` plus one column per month (already dates, from extract). Every month column
    becomes rows: 37 states x 3 months = 111 rows; the AVERAGE row gives 3.
    Values stay raw: names unmapped, prices unchecked.
    """
    return wide.melt(id_vars="label_raw", var_name="price_month", value_name="price_raw")


# Stage 2: clean numbers

_PRICE_JUNK = re.compile(r"[₦,\s]")  # naira sign, thousands separators, stray spaces


class BadPriceError(ValueError):
    """A price cell isn't a number. The message lists every bad cell, not just the first."""


def _strip_text(value):
    """Remove the junk characters from text; leave numbers (and everything else) alone."""
    return _PRICE_JUNK.sub("", value) if isinstance(value, str) else value


def clean_prices(long: pd.DataFrame) -> pd.DataFrame:
    """Make ``price_raw`` a numeric ``avg_price_ngn``: ``label_raw | price_month | avg_price_ngn``.

    Text like ``"₦1,561.22 "`` becomes ``1561.22``; numbers pass through at full precision (D4).
    Anything that still isn't a number (empty text, ``"n/a"``, a date, True/False) raises
    BadPriceError naming each bad cell. Whether a number is *plausible* is Step 6's job.
    """
    raw = long["price_raw"]
    prices = pd.to_numeric(raw.map(_strip_text), errors="coerce")
    bad = prices.isna() | raw.map(lambda v: isinstance(v, bool))  # to_numeric turns True into 1.0
    if bad.any():
        cells = [
            f"  {row.label_raw!r} {row.price_month:%b-%Y}: {row.price_raw!r}"
            for row in long[bad].itertuples()
        ]
        raise BadPriceError(f"{len(cells)} price cell(s) are not numbers:\n" + "\n".join(cells))
    return long.drop(columns="price_raw").assign(avg_price_ngn=prices.astype("float64"))


# Stage 3: map names

class UnknownStateError(ValueError):
    """A state label isn't in ``core.state_alias``. The message lists every unknown label once."""


def map_states(clean: pd.DataFrame, aliases: dict[str, str]) -> pd.DataFrame:
    """Swap ``label_raw`` for ``state_code``: ``state_code | price_month | avg_price_ngn``.

    ``aliases`` maps normalised names to codes, as in ``core.state_alias``
    (``"abuja" -> "NG-FC"``). It is passed in so transform never touches the database.
    An unknown label raises UnknownStateError: add its normalised name to
    ``seeds/state_alias.csv`` (only once you've confirmed which state it is) and rerun.
    """
    normalised = clean["label_raw"].map(normalise_state_name)
    codes = normalised.map(aliases)  # a missing key gives NaN, not an error
    unknown = codes.isna()
    if unknown.any():
        labels = dict.fromkeys(clean.loc[unknown, "label_raw"])  # each label once, in file order
        lines = [f"  {label!r} (normalised: {normalise_state_name(label)!r})" for label in labels]
        raise UnknownStateError(
            f"{len(labels)} state label(s) not in state_alias:\n" + "\n".join(lines)
        )
    return clean.assign(state_code=codes)[["state_code", "price_month", "avg_price_ngn"]]
