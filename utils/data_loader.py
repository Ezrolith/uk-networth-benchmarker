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
    - year: integer (2024) or any date string Excel might produce ("01/05/2026") — year is extracted
    - age: integer or decimal (32.4 is fine; gives more precise chart positioning)
    - net_worth: any numeric value including negatives
    - note: optional free-text label for a data point (shown in hover tooltip)
    """
    df = pd.read_csv(uploaded_file)
    required = {"year", "age", "net_worth"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")
    keep_cols = ["year", "age", "net_worth"]
    if "note" in df.columns:
        df["note"] = df["note"].fillna("").astype(str)
        keep_cols.append("note")
    df = df[keep_cols].dropna(subset=["year", "age", "net_worth"])

    # year: accept plain integers or date strings (e.g. "01/05/2026" from Excel)
    try:
        df["year"] = df["year"].astype(int)
    except (ValueError, TypeError):
        try:
            df["year"] = pd.to_datetime(df["year"], dayfirst=True).dt.year
        except Exception:
            raise ValueError(
                "Could not parse the 'year' column. Use a plain year (e.g. 2024) "
                "or a date like 01/05/2026."
            )

    # age: keep as float — decimal ages give more precise chart positioning
    df["age"] = df["age"].astype(float)
    df["net_worth"] = df["net_worth"].astype(float)

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

    return df
