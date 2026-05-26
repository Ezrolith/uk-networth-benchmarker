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
- Gains, velocity, cumulative trio                    → charts/gains.py                  ✓
- Percentile trajectory                                → charts/percentile_trajectory.py  ✓
- What-if projection                                   → charts/whatif.py                 ✓
- Main benchmark + personal-overlay figure             → charts/main_figure.py            ✓

All chart builders are now extracted. app.py retains only UI orchestration,
data loaders, summary stats / data quality utilities, and the methodology /
PDF generation code.
"""
from ._helpers import (
    fmt, fmt_delta, clean_note, safe_cagr, hover_template, best_gain,
    TITLE_COLOUR, GRID_COLOUR, AXIS_LABEL_COLOUR, ZERO_LINE_COLOUR,
    DEFAULT_PERSON_COLOUR, DEFAULT_PARTNER_COLOUR,
    DEFAULT_BENCHMARK_MEDIAN_COLOUR, DEFAULT_BENCHMARK_BAND_COLOUR,
    NEGATIVE_COLOUR, NEUTRAL_GREY,
)
from .asset_class import build_asset_class_chart
from .heatmap import build_heatmap
from .distribution import build_distribution_chart
from .gains import build_gains_chart, build_velocity_chart, build_cumulative_chart
from .percentile_trajectory import build_percentile_chart
from .whatif import build_whatif_figure
from .main_figure import build_main_figure
from .monte_carlo import build_monte_carlo_chart

__all__ = [
    # Chart builders
    "build_main_figure",
    "build_asset_class_chart",
    "build_heatmap",
    "build_distribution_chart",
    "build_gains_chart",
    "build_velocity_chart",
    "build_cumulative_chart",
    "build_percentile_chart",
    "build_whatif_figure",
    "build_monte_carlo_chart",
    # Formatting helpers
    "fmt", "fmt_delta", "clean_note", "safe_cagr", "hover_template", "best_gain",
    # Shared style constants
    "TITLE_COLOUR", "GRID_COLOUR", "AXIS_LABEL_COLOUR", "ZERO_LINE_COLOUR",
    "DEFAULT_PERSON_COLOUR", "DEFAULT_PARTNER_COLOUR",
    "DEFAULT_BENCHMARK_MEDIAN_COLOUR", "DEFAULT_BENCHMARK_BAND_COLOUR",
    "NEGATIVE_COLOUR", "NEUTRAL_GREY",
]
