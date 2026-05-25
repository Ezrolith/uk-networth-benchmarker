"""
Baked-in 11-year demo history used by the 'Try with demo data' button.

Kept here (not inlined in app.py) so test_demo_data.py can verify the exact
same data without copying it. Single source of truth.

The trajectory tracks a moderate UK saver: started age 25 with £8k from their
first real job (2016) and grew to £210k by age 35 (2026). Median for that age
band per WAS Wave 8 is ~£210k, so this persona finishes at roughly the median.
"""
from __future__ import annotations


DEMO_HISTORY: list[dict] = [
    {"year": 2016, "age": 25, "net_worth":   8_000, "note": "first real job"},
    {"year": 2017, "age": 26, "net_worth":  18_000, "note": ""},
    {"year": 2018, "age": 27, "net_worth":  29_000, "note": ""},
    {"year": 2019, "age": 28, "net_worth":  45_000, "note": "bought first flat"},
    {"year": 2020, "age": 29, "net_worth":  62_000, "note": ""},
    {"year": 2021, "age": 30, "net_worth":  88_000, "note": ""},
    {"year": 2022, "age": 31, "net_worth": 112_000, "note": ""},
    {"year": 2023, "age": 32, "net_worth": 138_000, "note": "promotion"},
    {"year": 2024, "age": 33, "net_worth": 155_000, "note": ""},
    {"year": 2025, "age": 34, "net_worth": 180_000, "note": ""},
    {"year": 2026, "age": 35, "net_worth": 210_000, "note": "married"},
]
