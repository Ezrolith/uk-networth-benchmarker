from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"


def load_was_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "was_data.csv")
    df = df.rename(columns={"value_nominal": "value"})
    df["with_pension"] = df["with_pension"].astype(bool)
    return df


def parse_personal_csv(uploaded_file) -> pd.DataFrame:
    """Parse an uploaded personal net worth CSV, raising ValueError on bad schema."""
    df = pd.read_csv(uploaded_file)
    required = {"year", "age", "net_worth"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")
    df = df[["year", "age", "net_worth"]].dropna()
    df["year"] = df["year"].astype(int)
    df["age"] = df["age"].astype(int)
    df["net_worth"] = df["net_worth"].astype(float)
    return df.sort_values("age").reset_index(drop=True)
