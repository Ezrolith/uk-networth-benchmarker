"""
Shared pytest fixtures for the test suite.

Anything that's needed by more than one test file lives here. Module-scoped
fixtures avoid the cost of rebuilding the WAS benchmark for every test.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.data_loader import load_was_data, load_asset_class_data
from utils.inference import interpolate_benchmarks, build_asset_class_series


@pytest.fixture(scope="session")
def raw_was() -> pd.DataFrame:
    """The raw WAS dataset (42 rows: 7 age bands × 3 percentiles × 2 pension states)."""
    return load_was_data()


@pytest.fixture(scope="session")
def benchmark(raw_was: pd.DataFrame) -> pd.DataFrame:
    """
    Household, with-pension, nominal-{DATA_YEAR} benchmark series across all
    single years 16–85. Used by inference tests, chart builder smoke tests,
    and anything else that needs a realistic benchmark DataFrame.
    """
    filtered = raw_was[raw_was["with_pension"] == True]
    return interpolate_benchmarks(filtered, np.arange(16, 86))


@pytest.fixture(scope="session")
def asset_series(benchmark: pd.DataFrame) -> pd.DataFrame:
    """Asset class component values × ages, anchored to the benchmark P50."""
    return build_asset_class_series(load_asset_class_data(), benchmark, np.arange(16, 86))


@pytest.fixture
def personal_history() -> pd.DataFrame:
    """A simple 4-point personal history for testing personal-overlay charts."""
    return pd.DataFrame({
        "year": [2020, 2022, 2024, 2026],
        "age":  [30.0, 32.0, 34.0, 36.0],
        "net_worth": [25_000.0, 60_000.0, 110_000.0, 175_000.0],
    })
