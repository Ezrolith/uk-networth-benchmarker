"""
Chart builders and formatting helpers.

This package is being incrementally extracted from app.py. Each chart builder
takes its dependencies as explicit parameters (colours, data, labels) rather
than reaching into module-level state, so they're testable in isolation.

Migration status (May 2026):
- Helpers (fmt, hover, best_gain, etc.)             → charts/_helpers.py    ✓
- Asset class chart                                  → charts/asset_class.py ✓
- Percentile landscape heatmap                       → charts/heatmap.py     ✓
- Wealth distribution density curve                  → charts/distribution.py ✓
- (next) Main figure, percentile trajectory, gains,  → still in app.py
  velocity, cumulative, whatif
"""
from ._helpers import (
    fmt, fmt_delta, clean_note, safe_cagr, hover_template, best_gain,
)
from .asset_class import build_asset_class_chart
from .heatmap import build_heatmap
from .distribution import build_distribution_chart

__all__ = [
    "build_asset_class_chart",
    "build_heatmap",
    "build_distribution_chart",
    "fmt", "fmt_delta", "clean_note", "safe_cagr", "hover_template", "best_gain",
]
