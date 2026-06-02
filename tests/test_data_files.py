"""
Defensive test: every data file the code expects to find actually exists
on disk with the right schema.

Catches the failure mode where data/was_data.csv (or was_asset_class.csv)
gets accidentally deleted, renamed, or has its schema changed in a way
that data_loader's downstream consumers can't handle.

Different from the inference + chart smoke tests — those exercise the
LOADED data. These verify the file is THERE in the first place.
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

sys.path.insert(0, str(ROOT))


def test_was_data_csv_exists():
    f = DATA_DIR / "was_data.csv"
    assert f.exists(), f"Expected {f} but it's missing"
    assert f.stat().st_size > 0, f"{f} exists but is empty"


def test_was_asset_class_csv_exists():
    f = DATA_DIR / "was_asset_class.csv"
    assert f.exists(), f"Expected {f} but it's missing"
    assert f.stat().st_size > 0, f"{f} exists but is empty"


def test_personal_template_csv_exists():
    """User-facing template — should be downloadable from the sidebar."""
    f = DATA_DIR / "personal_template.csv"
    assert f.exists(), f"Expected {f} but it's missing"
    assert f.stat().st_size > 0, f"{f} exists but is empty"


def test_personal_template_csv_matches_parser_schema():
    """
    Template's header must match what parse_personal_csv expects, otherwise
    downloading the template and immediately re-uploading it would fail.
    """
    f = DATA_DIR / "personal_template.csv"
    df = pd.read_csv(f)
    required = {"year", "age", "net_worth"}
    assert required.issubset(set(df.columns)), (
        f"personal_template.csv columns {list(df.columns)} missing {required}"
    )


def test_personal_template_includes_component_columns_and_reparses():
    """The shipped template should demonstrate the optional component columns and
    survive a parse round-trip (download → re-upload must work)."""
    import io
    from utils.data_loader import parse_personal_csv
    f = DATA_DIR / "personal_template.csv"
    raw = f.read_text(encoding="utf-8")
    df = parse_personal_csv(io.StringIO(raw))
    for c in ("property", "pension", "financial", "physical"):
        assert c in df.columns, f"template missing component column {c!r}"
    # The component columns in the shipped template sum to net_worth per row
    comp_sum = df[["property", "pension", "financial", "physical"]].sum(axis=1)
    for total, parts in zip(df["net_worth"], comp_sum):
        assert parts == pytest.approx(total, abs=1)


def test_was_data_csv_schema_matches_loader():
    """The columns load_was_data() expects must all be in the file."""
    from utils.data_loader import load_was_data
    df = load_was_data()
    # After the rename, 'value' should be present (was 'value_nominal' on disk)
    expected = {"age_band", "band_midpoint", "percentile", "value", "with_pension"}
    assert expected.issubset(set(df.columns)), (
        f"load_was_data() returned columns {list(df.columns)}, "
        f"missing {expected - set(df.columns)}"
    )


def test_was_asset_class_csv_schema_matches_loader():
    """Same for the asset class CSV."""
    from utils.data_loader import load_asset_class_data
    df = load_asset_class_data()
    expected = {"age_band", "band_midpoint",
                "property_pct", "pension_pct", "financial_pct", "physical_pct"}
    assert expected.issubset(set(df.columns)), (
        f"load_asset_class_data() returned {list(df.columns)}, "
        f"missing {expected - set(df.columns)}"
    )


def test_was_data_csv_has_all_seven_age_bands():
    """Sanity: every age band should be represented in the data."""
    from utils.data_loader import load_was_data
    df = load_was_data()
    expected_bands = {"16-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75+"}
    actual_bands = set(df["age_band"].unique())
    assert expected_bands == actual_bands, (
        f"Expected bands {expected_bands}, found {actual_bands}"
    )


def test_was_data_csv_has_all_three_percentiles():
    from utils.data_loader import load_was_data
    df = load_was_data()
    assert set(df["percentile"].unique()) == {"p25", "p50", "p75"}


def test_was_data_csv_has_both_pension_states():
    """We need both 'with pension' and 'without pension' series."""
    from utils.data_loader import load_was_data
    df = load_was_data()
    assert set(df["with_pension"].unique()) == {True, False}


def test_was_data_csv_p25_lt_p50_lt_p75_per_band():
    """For every age band × pension state, P25 < P50 < P75 (no data entry errors)."""
    from utils.data_loader import load_was_data
    df = load_was_data()
    for band in df["age_band"].unique():
        for pension in df["with_pension"].unique():
            sub = df[(df["age_band"] == band) & (df["with_pension"] == pension)]
            p25 = sub[sub["percentile"] == "p25"]["value"].iloc[0]
            p50 = sub[sub["percentile"] == "p50"]["value"].iloc[0]
            p75 = sub[sub["percentile"] == "p75"]["value"].iloc[0]
            assert p25 < p50 < p75, (
                f"P25/P50/P75 ordering broken in {band}, with_pension={pension}: "
                f"P25={p25}, P50={p50}, P75={p75}"
            )


def test_was_asset_class_shares_sum_to_100():
    """Every row's four component percentages should sum to ~100."""
    from utils.data_loader import load_asset_class_data
    df = load_asset_class_data()
    components = ["property_pct", "pension_pct", "financial_pct", "physical_pct"]
    sums = df[components].sum(axis=1)
    for band, s in zip(df["age_band"], sums):
        assert abs(s - 100) < 1, (
            f"Asset class shares for {band} sum to {s:.2f}, not 100"
        )
