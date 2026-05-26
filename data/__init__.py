"""
Data package: bundled CSVs (was_data, was_asset_class, personal_template)
plus the baked-in demo history used by the 'Try with demo data' button.

The CSVs are read by utils/data_loader.py at runtime; demo_data.py is
imported directly by app.py and tests/test_demo_data.py.
"""
from .demo_data import DEMO_HISTORY

__all__ = ["DEMO_HISTORY"]
