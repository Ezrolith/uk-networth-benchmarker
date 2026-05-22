from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"


def load_was_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "was_data.csv")
    df = df.rename(columns={"value_nominal": "value"})
    df["with_pension"] = df["with_pension"].astype(bool)
    return df


def parse_personal_csv(uploaded_file) -> pd.DataFrame:
    """
    Parse an uploaded personal net worth CSV.

    Accepts:
    - year: integer (2024) or any date string Excel might produce ("01/05/2026") — year is extracted
    - age: integer or decimal (32.4 is fine; gives more precise chart positioning)
    - net_worth: any numeric value including negatives
    """
    df = pd.read_csv(uploaded_file)
    required = {"year", "age", "net_worth"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")
    df = df[["year", "age", "net_worth"]].dropna()

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

    return df.sort_values("age").reset_index(drop=True)
