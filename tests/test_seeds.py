"""Seed CSVs are internally consistent (no database needed)."""

import re
from collections import Counter

import pytest

from pipeline import config
from pipeline.db import read_seed
from pipeline.transform import normalise_state_name

STATES = read_seed(config.SEEDS_DIR / "dim_state.csv")
ALIASES = read_seed(config.SEEDS_DIR / "state_alias.csv")
PRODUCTS = read_seed(config.SEEDS_DIR / "dim_product.csv")
CODES = {s["state_code"] for s in STATES}

# Every distinct state label seen in the 19 NBS PMS xlsx files (docs/decisions.md, Step 1).
OBSERVED_LABELS = [
    "Abia", "Abuja", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno",
    "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "Gombe", "Imo", "Jigawa", "Kaduna",
    "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa", "Nassarawa", "Niger", "Ogun",
    "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba", "Yobe", "Zamfara",
]  # fmt: skip


def test_dim_state_has_37_unique_iso_codes():
    assert len(STATES) == 37
    assert len(CODES) == 37
    assert all(re.fullmatch(r"NG-[A-Z]{2}", c) for c in CODES)
    assert len({s["state_name"] for s in STATES}) == 37


def test_zone_sizes():
    assert Counter(s["zone"] for s in STATES) == {
        "North Central": 7,  # incl. FCT
        "North East": 6,
        "North West": 7,
        "South East": 5,
        "South South": 6,
        "South West": 6,
    }


def test_aliases_are_normalised_unique_and_point_at_real_states():
    names = [a["alias_normalised"] for a in ALIASES]
    assert len(names) == len(set(names))
    assert all(normalise_state_name(n) == n for n in names)
    assert {a["state_code"] for a in ALIASES} <= CODES


def test_every_canonical_name_is_an_alias():
    lookup = {a["alias_normalised"]: a["state_code"] for a in ALIASES}
    for s in STATES:
        assert lookup[normalise_state_name(s["state_name"])] == s["state_code"]


@pytest.mark.parametrize("label", OBSERVED_LABELS)
def test_every_observed_nbs_label_resolves(label):
    lookup = {a["alias_normalised"]: a["state_code"] for a in ALIASES}
    assert normalise_state_name(label) in lookup


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Akwa-Ibom State ", "akwa ibom"),
        ("FCT, Abuja", "fct abuja"),
        ("CROSS  RIVER", "cross river"),
        ("Nassarawa", "nassarawa"),
    ],
)
def test_normalise_state_name(raw, expected):
    assert normalise_state_name(raw) == expected


def test_products():
    assert {p["product_code"] for p in PRODUCTS} == {"PMS", "AGO", "DPK", "LPG"}
