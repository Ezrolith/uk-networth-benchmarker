"""
Data-loading and personal-data helpers.

- load_was_data, load_asset_class_data: read the bundled WAS Wave 8 CSVs
  and normalise their schema (e.g. rename value_nominal → value).
- parse_personal_csv: parse a user-uploaded net worth CSV with tolerance
  for Excel date-formatted years, ISO dates, whitespace in headers, and
  extra columns. Attaches `excel_year_warning` and `birth_year_warning`
  via DataFrame.attrs when relevant.
- encode_personal_data / decode_personal_data: zlib + URL-safe base64
  round-trip for sharing personal data via the URL query param. ~100
  characters for a typical history.
"""
from pathlib import Path
import json, base64, zlib
import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"


def load_asset_class_data() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "was_asset_class.csv")


def load_was_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "was_data.csv")
    df = df.rename(columns={"value_nominal": "value"})
    df["with_pension"] = df["with_pension"].astype(bool)
    return df


# ── Shareable URL helpers ─────────────────────────────────────────────────────

def encode_personal_data(df: pd.DataFrame) -> str:
    """Compress personal data to a URL-safe base64 string for sharing."""
    records = df[["year", "age", "net_worth"]].round({"age": 4, "net_worth": 2}).to_dict("records")
    raw = json.dumps(records, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(zlib.compress(raw, level=9)).decode()


def decode_personal_data(encoded: str) -> pd.DataFrame:
    """Decode a shareable URL token back into a personal data DataFrame."""
    raw = zlib.decompress(base64.urlsafe_b64decode(encoded.encode() + b"=="))
    records = json.loads(raw.decode())
    df = pd.DataFrame(records)
    df["year"]      = df["year"].astype(int)
    df["age"]       = df["age"].astype(float)
    df["net_worth"] = df["net_worth"].astype(float)
    return df.sort_values("age").reset_index(drop=True)


def parse_personal_csv(uploaded_file) -> pd.DataFrame:
    """
    Parse an uploaded personal net worth CSV.

    Accepts:
    - year: integer (2024), Excel date ("01/05/2026"), or ISO date ("2024-01-15")
    - age: integer or decimal (32.4 is fine; gives more precise chart positioning)
    - net_worth: any numeric value including negatives
    - note: optional free-text label for a data point (shown in hover tooltip)
    - liabilities: optional total debts at that point (mortgage, loans). Context
      only — net_worth stays the benchmark input.

    Tolerant of common CSV issues:
    - Whitespace around column names (Excel often pads after the comma)
    - Extra columns (only year/age/net_worth/note are kept)
    - Mixed date formats — tries ISO first, then dayfirst (UK)
    """
    # Read with encoding fallback. Excel on Windows saves CSVs as cp1252 by
    # default, not UTF-8 — a £ symbol becomes byte 0xa3 which is invalid
    # UTF-8 and raises UnicodeDecodeError. Try utf-8 first (also covers
    # StringIO test inputs where pandas ignores the encoding kwarg), then
    # cp1252 (the typical Excel save), then latin-1 (a superset of cp1252
    # that decodes any byte without raising).
    def _try_read(enc):
        if hasattr(uploaded_file, "seek"):
            try:
                uploaded_file.seek(0)
            except Exception:
                pass
        kwargs = {} if enc is None else {"encoding": enc}
        return pd.read_csv(uploaded_file, **kwargs)

    df = None
    last_unicode_err: UnicodeDecodeError | None = None
    for enc in (None, "cp1252", "latin-1"):
        try:
            df = _try_read(enc)
            break
        except UnicodeDecodeError as e:
            last_unicode_err = e
            continue
        except pd.errors.EmptyDataError:
            raise ValueError(
                "The uploaded file is empty. Add at least a header row and one data "
                "row (year, age, net_worth), then try again."
            )
    if df is None:
        # Should be unreachable — latin-1 decodes any byte — but be explicit.
        raise ValueError(
            "Could not decode the CSV file. Try saving it as 'CSV UTF-8' from "
            f"Excel and re-uploading. (Underlying error: {last_unicode_err})"
        )
    # Strip whitespace from column names so 'year, age, net_worth' works the same
    # as 'year,age,net_worth'.
    df.columns = [str(c).strip() for c in df.columns]

    required = {"year", "age", "net_worth"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")

    # Headers-only file: clearer message than letting it propagate as an empty df
    if len(df) == 0:
        raise ValueError(
            "The CSV has column headers but no data rows. Add at least one row "
            "with year, age, and net_worth values."
        )
    keep_cols = ["year", "age", "net_worth"]
    if "note" in df.columns:
        df["note"] = df["note"].fillna("").astype(str)
        keep_cols.append("note")
    if "liabilities" in df.columns:
        keep_cols.append("liabilities")
    df = df[keep_cols].dropna(subset=["year", "age", "net_worth"])

    # year: accept plain integers, ISO dates, or UK dd/mm/yyyy dates
    try:
        df["year"] = df["year"].astype(int)
    except (ValueError, TypeError):
        # Try parsing as date. Try ISO format first to avoid the dayfirst warning
        # when an ISO date is already supplied.
        sample = str(df["year"].iloc[0])
        is_iso  = len(sample) >= 10 and sample[4] == "-" and sample[7] == "-"
        try:
            if is_iso:
                df["year"] = pd.to_datetime(df["year"]).dt.year
            else:
                df["year"] = pd.to_datetime(df["year"], dayfirst=True).dt.year
        except Exception:
            raise ValueError(
                "Could not parse the 'year' column. Use a plain year (e.g. 2024), "
                "an ISO date (2024-01-15), or a UK date (01/05/2026)."
            )

    # Detect Excel serial-date numbers that survived the .astype(int) path.
    # Excel stores dates internally as integer days since 1899-12-30 (accounting
    # for the 1900-leap-year bug). When a 'year' column actually contains dates
    # that Excel exported as raw numbers (no date format), they appear as values
    # like 42987 (= 2017-09-09) or 46174 (= 2026-06-01). Any 'year' > 10000 is
    # almost certainly an Excel serial — no real-world year column hits 10000+.
    if (df["year"] > 10_000).any():
        _serial_mask = df["year"] > 10_000
        _serials = df.loc[_serial_mask, "year"]
        _real_years = (pd.Timestamp("1899-12-30")
                       + pd.to_timedelta(_serials, unit="D")).dt.year
        df.loc[_serial_mask, "year"] = _real_years.astype(int)
        df.attrs["excel_serial_converted"] = (
            f"Converted {int(_serial_mask.sum())} Excel serial-date number(s) "
            f"in the 'year' column to real years (e.g. {int(_serials.iloc[0])} → "
            f"{int(_real_years.iloc[0])}). To avoid this in future, format the "
            f"column as plain years in Excel before exporting."
        )

    # age: keep as float — decimal ages give more precise chart positioning
    df["age"] = df["age"].astype(float)

    # Strip currency symbols and thousands separators from net_worth.
    # Excel often saves "£5,237" (or "$5,237", "€5,237") rather than 5237 —
    # the column then comes in as a string dtype and astype(float) would
    # crash. Clean it up before casting. Preserves negatives and decimals.
    #
    # Backend-agnostic check: pandas may store the column as `object`, the
    # newer `string` extension dtype, or ArrowDtype("string") depending on
    # pandas version + whether pyarrow is installed. CI hit ArrowDtype where
    # `dtype == object` was False — so we check `is_numeric_dtype` instead,
    # which is True for any int/float dtype and False for every string flavour.
    if not pd.api.types.is_numeric_dtype(df["net_worth"]):
        df["net_worth"] = (
            df["net_worth"].astype(str)
            .str.replace("£", "", regex=False)
            .str.replace("$", "", regex=False)
            .str.replace("€", "", regex=False)
            .str.replace(",", "", regex=False)
            .str.strip()
        )
    try:
        df["net_worth"] = df["net_worth"].astype(float)
    except ValueError as e:
        raise ValueError(
            "Could not parse the 'net_worth' column as numbers. Check for "
            "unexpected characters in the values (e.g. notes, units). "
            f"(Underlying error: {e})"
        )

    # Optional 'liabilities' column (total debts at that point). Same currency
    # tolerance as net_worth; coerced to a non-negative magnitude. Used only for
    # gross-assets-vs-net-worth context — net_worth stays the benchmark input.
    if "liabilities" in df.columns:
        if not pd.api.types.is_numeric_dtype(df["liabilities"]):
            df["liabilities"] = (
                df["liabilities"].astype(str)
                .str.replace("£", "", regex=False)
                .str.replace("$", "", regex=False)
                .str.replace("€", "", regex=False)
                .str.replace(",", "", regex=False)
                .str.strip()
            )
        df["liabilities"] = pd.to_numeric(df["liabilities"], errors="coerce").fillna(0.0).abs()

    df = df.sort_values("age").reset_index(drop=True)

    # Detect Excel date-artifact years (Excel serial dates misformatted as early 1900s)
    artifact_rows = df[df["year"] < 1940]
    if len(artifact_rows) > 0:
        example = int(artifact_rows["year"].iloc[0])
        df.attrs["excel_year_warning"] = (
            f"{len(artifact_rows)} row(s) have a year before 1940 (e.g. {example}). "
            "These are likely Excel date-format artefacts — your 'year' column may contain "
            "date strings that were auto-formatted by Excel. The data will still plot correctly "
            "using the 'age' column, but year labels in tooltips will be wrong."
        )

    # Birth-year consistency check — only on rows with plausible years
    plausible = df[df["year"] >= 1940]
    if len(plausible) >= 2:
        implied_birth = plausible["year"] - plausible["age"]
        span = implied_birth.max() - implied_birth.min()
        if span > 3:
            df.attrs["birth_year_warning"] = (
                f"Implied birth year varies by {span:.0f} years across your data "
                f"(min {implied_birth.min():.0f}, max {implied_birth.max():.0f}). "
                "Check that age and year values are consistent."
            )

    # Implausible-age sanity check. The benchmark covers ages 16-85; anything
    # outside [16, 100] is almost certainly a data entry error rather than a
    # real person. We don't reject the row (the user might have a legitimate
    # reason) but we flag it so they can spot typos in the manual editor.
    out_of_age = df[(df["age"] < 16) | (df["age"] > 100)]
    if len(out_of_age) > 0:
        bad_ages = sorted(set(round(float(a), 1) for a in out_of_age["age"]))
        df.attrs["implausible_age_warning"] = (
            f"{len(out_of_age)} row(s) have age outside 16-100 (values: {bad_ages}). "
            "Check for typos. The benchmark only covers 16-85, so values beyond "
            "that clamp to the nearest end of the range."
        )

    return df
