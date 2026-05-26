"""
Streamlit AppTest integration tests — actually run app.py end-to-end.

These catch the class of bugs that have repeatedly slipped past the unit
test suite and only surfaced on the live deployment:
- Duplicate widget keys (`StreamlitDuplicateElementKey`)
- Session-state writes to widget keys after the widget rendered
- NameErrors from cross-file renames in the chart helpers
- Streamlit API misuse that compiles fine but fails at runtime

Each AppTest run loads app.py into a synthetic Streamlit runtime, executes
the script top-to-bottom, and captures any exceptions plus the resulting
widget tree. Tests are deliberately small in number because each AppTest
run takes ~1-3 seconds — but they're catching a bug class pytest can't
otherwise see.

If a test is slow to debug locally, you can run just this file with:
    pytest tests/test_app_runtime.py -v
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _make_app_test(timeout: int = 30):
    """Construct an AppTest for app.py, working from the project root."""
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "app.py"),
        default_timeout=timeout,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Cold-start smoke test
# ──────────────────────────────────────────────────────────────────────────────

def test_app_loads_without_exception():
    """
    The most basic check: app.py runs from a cold session with no personal
    data and produces zero exceptions. Catches:
    - Import errors (a freshly-broken import)
    - NameErrors from cross-file renames (e.g. the _CAGR_MIN_START regression)
    - Duplicate widget keys (e.g. the mc_monthly regression)
    - Any Streamlit API misuse on the empty-state path
    """
    at = _make_app_test()
    at.run()
    # ElementList must be empty — non-empty means the app raised something
    assert len(at.exception) == 0, (
        f"App raised {len(at.exception)} exception(s) on cold start: "
        f"{[e.message for e in at.exception]}"
    )


def test_app_loads_with_demo_data_pending():
    """
    Simulate the user having clicked 'Try with demo data'. The flag is set
    in session state BEFORE the run, then app.py picks it up.
    """
    at = _make_app_test()
    at.session_state["_pending_demo_load"] = True
    from data.demo_data import DEMO_HISTORY
    at.session_state["you_rows"] = list(DEMO_HISTORY)
    at.run()
    assert len(at.exception) == 0, (
        "App raised on demo-data-loaded path: "
        f"{[e.message for e in at.exception]}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Widget-key uniqueness — the bug class that hit production multiple times
# ──────────────────────────────────────────────────────────────────────────────

def test_no_duplicate_widget_keys():
    """
    Sweep every widget the app creates and verify keys are unique.

    Streamlit raises StreamlitDuplicateElementKey at runtime when two widgets
    share a key. AppTest exposes the widget tree, so we can audit this
    statically AFTER the run completes.

    Caught the mc_monthly collision between the Quick calculator and Monte
    Carlo expander in Session 8.
    """
    at = _make_app_test()
    at.run()

    # Collect every widget's key from across the widget types AppTest tracks.
    # AppTest doesn't have a single "all widgets" accessor, so we sum the
    # individual collections that have a .key attribute.
    keys: list[str] = []
    for collection_name in (
        "button", "checkbox", "radio", "selectbox", "multiselect",
        "slider", "select_slider", "number_input", "text_input",
        "text_area", "date_input", "time_input", "color_picker",
        "file_uploader", "download_button", "toggle",
        # data_editor is also a widget but accessed differently
    ):
        try:
            collection = getattr(at, collection_name, None)
            if collection is None:
                continue
            for widget in collection:
                key = getattr(widget, "key", None)
                if key:
                    keys.append(key)
        except Exception:
            continue

    # Find duplicates
    from collections import Counter
    counts = Counter(keys)
    dupes = {k: c for k, c in counts.items() if c > 1}
    assert not dupes, (
        f"Duplicate widget keys would raise StreamlitDuplicateElementKey: {dupes}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Cross-version Streamlit safety
# ──────────────────────────────────────────────────────────────────────────────

def test_session_state_writes_to_widget_keys_only_before_widget_creation():
    """
    Streamlit forbids `st.session_state[K] = value` after a widget with
    key=K has been created on the same run. AppTest doesn't expose this
    directly, but a successful run means the pattern is OK.

    This test specifically exercises the demo-data flow which previously
    crashed because the button click handler wrote to `you_method` after
    the radio widget had already rendered.
    """
    # Simulate the click by setting the pending flag — this is exactly what
    # the in-app button does. If the pre-seed in _personal_data_section
    # works, the subsequent run sets you_method safely. If it regresses to
    # the old broken pattern, the run will raise.
    at = _make_app_test()
    at.session_state["_pending_demo_load"] = True
    from data.demo_data import DEMO_HISTORY
    at.session_state["you_rows"] = list(DEMO_HISTORY)
    at.run()
    assert len(at.exception) == 0
    # After the run, the radio key should be set to Manual entry (from the
    # pre-seed in _personal_data_section). AppTest's session_state wrapper
    # exposes keys via attribute / __contains__ access, not .get(...).
    assert "you_method" in at.session_state
    assert at.session_state["you_method"] == "Manual entry"


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar settings — exercise the toggle paths
# ──────────────────────────────────────────────────────────────────────────────

def test_log_scale_toggle_no_crash():
    """Flipping the log-scale toggle should not crash. AppTest can flip
    session state to simulate the toggle being on."""
    at = _make_app_test()
    at.session_state["log_scale"] = True
    at.run()
    assert len(at.exception) == 0


def test_real_terms_toggle_no_crash():
    at = _make_app_test()
    at.session_state["real_terms"] = True
    at.run()
    assert len(at.exception) == 0


def test_individual_basis_no_crash():
    """Selecting the 'Individual' basis radio should not crash."""
    at = _make_app_test()
    at.session_state["basis"] = "Individual"
    at.run()
    assert len(at.exception) == 0
