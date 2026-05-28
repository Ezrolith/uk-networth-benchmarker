"""
Tests for utils/data_loader.py — CSV parsing, URL encode/decode, validation warnings.
"""
from __future__ import annotations
import io
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.data_loader import (  # noqa: E402
    parse_personal_csv,
    encode_personal_data,
    decode_personal_data,
    load_was_data,
    load_asset_class_data,
)


# ──────────────────────────────────────────────────────────────────────────────
# CSV parsing
# ──────────────────────────────────────────────────────────────────────────────

def test_parse_basic_csv():
    csv = "year,age,net_worth\n2020,28,12000\n2024,32,52000\n"
    df = parse_personal_csv(io.StringIO(csv))
    assert len(df) == 2
    assert list(df.columns)[:3] == ["year", "age", "net_worth"]
    assert df.iloc[0]["year"] == 2020
    assert df.iloc[1]["net_worth"] == 52000.0


def test_parse_excel_date_year_extracts_year():
    """Excel often auto-formats a year column as dd/mm/yyyy. Parser must extract the year."""
    csv = "year,age,net_worth\n01/05/2024,32,52000\n01/05/2025,33,65000\n"
    df = parse_personal_csv(io.StringIO(csv))
    assert df.iloc[0]["year"] == 2024
    assert df.iloc[1]["year"] == 2025


def test_parse_iso_date_year_extracts_year():
    """ISO date strings (yyyy-mm-dd) should also work — without raising a
    dayfirst UserWarning."""
    csv = "year,age,net_worth\n2024-01-15,32,52000\n"
    df = parse_personal_csv(io.StringIO(csv))
    assert df.iloc[0]["year"] == 2024


def test_parse_tolerates_whitespace_in_column_names():
    """CSV often has spaces after commas — 'year, age, net_worth' should work."""
    csv = "year, age, net_worth\n2024,30,50000\n"
    df = parse_personal_csv(io.StringIO(csv))
    assert len(df) == 1
    assert df.iloc[0]["age"] == 30


def test_parse_tolerates_extra_columns():
    """Extra columns beyond year/age/net_worth/note should be ignored, not crash."""
    csv = "year,age,net_worth,category,source\n2024,30,50000,test,manual\n"
    df = parse_personal_csv(io.StringIO(csv))
    assert len(df) == 1
    # The extra columns should not appear in the result
    assert "category" not in df.columns
    assert "source" not in df.columns


def test_parse_unparseable_year_raises_helpful_error():
    """Year column with nonsense data should raise a clear error."""
    csv = "year,age,net_worth\nbanana,30,50000\n"
    with pytest.raises(ValueError, match="Could not parse"):
        parse_personal_csv(io.StringIO(csv))


def test_parse_accepts_decimal_age():
    csv = "year,age,net_worth\n2024,32.5,52000\n"
    df = parse_personal_csv(io.StringIO(csv))
    assert df.iloc[0]["age"] == pytest.approx(32.5)


def test_parse_optional_note_column():
    csv = "year,age,net_worth,note\n2024,32,52000,bought flat\n2025,33,65000,\n"
    df = parse_personal_csv(io.StringIO(csv))
    assert "note" in df.columns
    assert df.iloc[0]["note"] == "bought flat"
    assert df.iloc[1]["note"] == ""


def test_parse_missing_required_column_raises():
    csv = "year,age\n2024,32\n"
    with pytest.raises(ValueError, match="missing required columns"):
        parse_personal_csv(io.StringIO(csv))


def test_parse_empty_file_raises_helpful_error():
    """A completely empty file should produce a clear message, not crash with
    pandas' EmptyDataError."""
    with pytest.raises(ValueError, match="empty"):
        parse_personal_csv(io.StringIO(""))


def test_parse_headers_only_raises_helpful_error():
    """A file with only the header row should also fail with a clear message
    (rather than silently producing an empty DataFrame)."""
    csv = "year,age,net_worth\n"
    with pytest.raises(ValueError, match="no data rows"):
        parse_personal_csv(io.StringIO(csv))


def test_birth_year_warning_when_inconsistent():
    """Implied birth year varying by >3 yrs should trigger a warning attribute."""
    csv = "year,age,net_worth\n2015,25,5000\n2020,35,50000\n2025,41,183000\n"
    df = parse_personal_csv(io.StringIO(csv))
    assert "birth_year_warning" in df.attrs


def test_no_warning_for_consistent_data():
    csv = "year,age,net_worth\n2015,28,5000\n2020,33,50000\n2025,38,183000\n"
    df = parse_personal_csv(io.StringIO(csv))
    assert "birth_year_warning" not in df.attrs


def test_parse_excel_serial_dates_as_year_converted():
    """
    Excel sometimes exports a date column as raw integer serial numbers
    (days since 1899-12-30). E.g., 46174 → 2026-06-01. The parser must
    detect these (any year > 10,000) and convert them to real years.
    Without this, the years would be interpreted literally as 'year 46174'
    and break every downstream calculation.
    """
    csv = "year,age,net_worth\n42987,32.4,5000\n46174,41.1,183871\n"
    df = parse_personal_csv(io.StringIO(csv))
    # 42987 is 2017-09-09; 46174 is 2026-06-01
    assert df.iloc[0]["year"] == 2017
    assert df.iloc[1]["year"] == 2026
    # User-facing info about the conversion
    assert "excel_serial_converted" in df.attrs


def test_parse_excel_serial_partial_only_converts_serials():
    """A mixed CSV (some real years, some Excel serials) should convert only
    the serials and leave real years alone."""
    csv = "year,age,net_worth\n2020,30,10000\n42987,32,15000\n2024,34,30000\n"
    df = parse_personal_csv(io.StringIO(csv))
    # Sorted by age, so order matches
    assert df.iloc[0]["year"] == 2020
    assert df.iloc[1]["year"] == 2017  # converted from 42987
    assert df.iloc[2]["year"] == 2024


def test_implausible_age_warning_under_16():
    """A row with age below 16 (e.g. typo) should trigger the implausible-age warning."""
    csv = "year,age,net_worth\n2024,5,1000\n2025,30,50000\n"
    df = parse_personal_csv(io.StringIO(csv))
    assert "implausible_age_warning" in df.attrs
    assert "5" in df.attrs["implausible_age_warning"]


def test_implausible_age_warning_over_100():
    """A row with age above 100 (e.g. typo) should trigger the implausible-age warning."""
    csv = "year,age,net_worth\n2024,30,50000\n2025,150,500000\n"
    df = parse_personal_csv(io.StringIO(csv))
    assert "implausible_age_warning" in df.attrs
    assert "150" in df.attrs["implausible_age_warning"]


def test_no_implausible_age_warning_for_valid_range():
    """16-100 inclusive should not trigger the warning."""
    csv = "year,age,net_worth\n2024,16,5000\n2025,100,500000\n"
    df = parse_personal_csv(io.StringIO(csv))
    assert "implausible_age_warning" not in df.attrs


def test_excel_year_artifact_warning():
    """Years before 1940 are flagged as likely Excel date-format artefacts."""
    csv = "year,age,net_worth\n1905,32,5000\n2024,32,5000\n"
    df = parse_personal_csv(io.StringIO(csv))
    assert "excel_year_warning" in df.attrs


def test_parse_cp1252_encoded_file_with_pound_signs():
    """
    Excel on Windows saves CSVs as cp1252 by default. A user-uploaded file
    with £ in the net_worth values used to crash with:
      'utf-8' codec can't decode byte 0xa3 in position N: invalid start byte
    The parser should fall back to cp1252 and strip the currency symbol.
    """
    # The exact byte pattern the user uploaded — £ symbol encoded as cp1252 0xa3
    csv_bytes = (
        b"year,age,net_worth\n"
        b"2017,32,\xa30\n"
        b"2018,34,\"\xa35,237\"\n"
        b"2019,35,\"\xa318,302\"\n"
        b"2020,36,\"\xa338,268\"\n"
    )
    df = parse_personal_csv(io.BytesIO(csv_bytes))
    assert len(df) == 4
    assert df.iloc[0]["net_worth"] == 0.0
    assert df.iloc[1]["net_worth"] == 5237.0
    assert df.iloc[3]["net_worth"] == 38268.0


def test_parse_utf8_file_with_pound_signs_in_values():
    """UTF-8-encoded file with proper £ encoding should also work (and the
    £ should be stripped from numeric values)."""
    csv = (
        "year,age,net_worth\n"
        "2024,30,\"£50,000\"\n"
        "2025,31,\"£75,500\"\n"
    )
    df = parse_personal_csv(io.BytesIO(csv.encode("utf-8")))
    assert df.iloc[0]["net_worth"] == 50_000.0
    assert df.iloc[1]["net_worth"] == 75_500.0


def test_parse_dollar_and_euro_currency_symbols_stripped():
    """Non-UK users may export with $ or €. Strip those too."""
    csv = "year,age,net_worth\n2024,30,\"$50,000\"\n2025,31,\"€75,500\"\n"
    df = parse_personal_csv(io.BytesIO(csv.encode("utf-8")))
    assert df.iloc[0]["net_worth"] == 50_000.0
    assert df.iloc[1]["net_worth"] == 75_500.0


def test_parse_negative_net_worth_with_currency_symbol():
    """Negative net worth (early career, debt > assets) with £ prefix must
    still come through as a negative float."""
    csv = "year,age,net_worth\n2024,25,\"-£5,000\"\n2025,26,\"£10,000\"\n"
    df = parse_personal_csv(io.BytesIO(csv.encode("utf-8")))
    assert df.iloc[0]["net_worth"] == -5_000.0
    assert df.iloc[1]["net_worth"] == 10_000.0


def test_parse_thousands_separator_without_currency_symbol():
    """A bare '5,237' (no £) should also be accepted — some users export
    plain numbers but Excel still applies the thousands separator."""
    csv = "year,age,net_worth\n2024,30,\"50,000\"\n2025,31,\"75,500\"\n"
    df = parse_personal_csv(io.BytesIO(csv.encode("utf-8")))
    assert df.iloc[0]["net_worth"] == 50_000.0
    assert df.iloc[1]["net_worth"] == 75_500.0


# ──────────────────────────────────────────────────────────────────────────────
# URL encoding round-trip
# ──────────────────────────────────────────────────────────────────────────────

def test_encode_decode_roundtrip():
    original = pd.DataFrame({
        "year":      [2020, 2023, 2026],
        "age":       [31.0, 34.0, 37.5],
        "net_worth": [18500.0, 90000.0, 183871.5],
    })
    token = encode_personal_data(original)
    assert isinstance(token, str)
    assert len(token) < 500  # compression should keep tokens small
    restored = decode_personal_data(token)
    pd.testing.assert_frame_equal(
        restored[["year", "age", "net_worth"]].reset_index(drop=True),
        original.reset_index(drop=True),
        check_dtype=False,
    )


def test_encoded_token_is_url_safe():
    df = pd.DataFrame({"year": [2024], "age": [30.0], "net_worth": [50000.0]})
    token = encode_personal_data(df)
    # URL-safe base64 uses '-' and '_' instead of '+' and '/'
    assert "+" not in token
    assert "/" not in token


# ──────────────────────────────────────────────────────────────────────────────
# Static data loaders
# ──────────────────────────────────────────────────────────────────────────────

def test_load_was_data_schema():
    df = load_was_data()
    assert {"age_band", "band_midpoint", "percentile", "value", "with_pension"}.issubset(df.columns)
    assert set(df["percentile"].unique()) == {"p25", "p50", "p75"}
    assert df["with_pension"].dtype == bool


def test_load_asset_class_data_schema():
    df = load_asset_class_data()
    needed = {"age_band", "band_midpoint", "property_pct", "pension_pct",
              "financial_pct", "physical_pct"}
    assert needed.issubset(df.columns)
    # Component shares should sum to 100 per row (within rounding)
    pct_sum = df[["property_pct", "pension_pct", "financial_pct", "physical_pct"]].sum(axis=1)
    for v in pct_sum:
        assert v == pytest.approx(100, abs=1)
