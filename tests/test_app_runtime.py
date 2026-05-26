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


# ──────────────────────────────────────────────────────────────────────────────
# PDF report generation — the most complex code path
# ──────────────────────────────────────────────────────────────────────────────

def _decode_pdf_text(pdf_bytes: bytes) -> str:
    """
    Best-effort text extraction from a fpdf2-produced PDF without adding a
    parsing dependency.

    fpdf2 stores text in FlateDecode-compressed content streams. We:
    1. Find every '<<.../Filter /FlateDecode.../Length N...>>stream...endstream'
       block.
    2. zlib-decompress each stream.
    3. Concatenate the readable bytes (PDF text-showing operators like Tj/TJ
       contain the literal text as ASCII).
    """
    import re, zlib
    out_parts: list[str] = []
    for m in re.finditer(
        rb"<<[^>]*?/Filter\s*/FlateDecode[^>]*?>>\s*stream\s*(.*?)\s*endstream",
        pdf_bytes, re.DOTALL,
    ):
        try:
            decoded = zlib.decompress(m.group(1))
        except Exception:
            continue
        try:
            out_parts.append(decoded.decode("latin-1", errors="ignore"))
        except Exception:
            continue
    return "\n".join(out_parts)


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    """Pull the /Count from the PDF's /Pages object."""
    import re
    m = re.search(rb"/Count\s+(\d+)", pdf_bytes)
    return int(m.group(1)) if m else 0


def test_app_runs_with_partner_data_loaded():
    """
    Both the user's data and the partner's data loaded. Exercises:
    - _personal_data_section called twice (once for 'you', once for 'partner')
    - Combined household banner under the metrics row
    - IHT calculator's combined-household toggle (added in Session 8)
    - Head-to-head leaderboard
    - Partner overlay on every chart
    """
    at = _make_app_test()
    from data.demo_data import DEMO_HISTORY

    at.session_state["_pending_demo_load"] = True
    at.session_state["you_rows"] = list(DEMO_HISTORY)

    # Partner: same shape but 20% larger NW
    at.session_state["partner_method"] = "Manual entry"
    at.session_state["partner_rows"] = [
        {**row, "net_worth": row["net_worth"] * 1.2}
        for row in DEMO_HISTORY
    ]
    at.run()
    assert len(at.exception) == 0, (
        f"App crashed with partner data loaded: "
        f"{[e.message for e in at.exception]}"
    )


def test_app_handles_excel_serial_year_csv_data_end_to_end():
    """
    Reproduce the exact CSV pattern a user uploaded that crashed in
    production (Excel serial-date 'year' values like 42987, 46174). The
    parser should auto-convert them; the app should then render without
    exception with the converted years.
    """
    import io
    from utils.data_loader import parse_personal_csv

    excel_serial_csv = (
        "year,age,net_worth\n"
        "42987,32.4,-216.4\n"     # 2017-09-09, negative balance
        "43413,33.57,5236.98\n"   # 2018
        "45748,40.04,129980.06\n" # 2025
        "46174,41.13,191151.99\n" # 2026
    )
    parsed = parse_personal_csv(io.StringIO(excel_serial_csv))
    # Sanity: years actually converted
    assert parsed["year"].max() < 3000

    # Feed those parsed rows into the app via session_state, just like the
    # upload flow does (via the radio = 'Upload CSV' branch which returns
    # the parsed DataFrame). Easiest path is Manual entry + you_rows since
    # we don't have to simulate the file upload widget.
    at = _make_app_test()
    at.session_state["_pending_demo_load"] = True
    at.session_state["you_rows"] = parsed.to_dict("records")
    at.run()
    assert len(at.exception) == 0, (
        "App crashed on the parsed Excel-serial CSV: "
        f"{[e.message for e in at.exception]}"
    )


def test_pdf_generation_with_demo_data_succeeds_and_includes_monte_carlo():
    """
    Most expensive test in the suite (~10-20s): generates a multi-page PDF
    via matplotlib + fpdf2 end-to-end. Verifies the Monte Carlo page makes
    it into the output — a user reported it missing on the live deploy, and
    a regression that drops the page silently from the cycle of
    `_mpl_monte_carlo()` returning None or the page rendering block being
    skipped would otherwise have to be caught by manual QA every release.
    """
    at = _make_app_test(timeout=120)
    # Pre-seed demo data so personal-data sections + MC + retirement run
    at.session_state["_pending_demo_load"] = True
    from data.demo_data import DEMO_HISTORY
    at.session_state["you_rows"] = list(DEMO_HISTORY)
    at.run()
    assert len(at.exception) == 0

    # Find the 'Generate PDF report' button and click it
    gen_buttons = [b for b in at.button if "Generate PDF" in b.label]
    assert len(gen_buttons) == 1, (
        f"Expected exactly one 'Generate PDF' button, found {len(gen_buttons)}"
    )
    gen_buttons[0].click().run()
    assert len(at.exception) == 0, (
        "PDF generation raised: "
        f"{[e.message for e in at.exception]}"
    )

    # Verify the PDF was actually generated
    assert "_pdf_bytes" in at.session_state
    pdf_bytes = at.session_state["_pdf_bytes"]
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert pdf_bytes.startswith(b"%PDF-"), "Output isn't a valid PDF"
    assert len(pdf_bytes) > 10_000, (
        f"PDF suspiciously small ({len(pdf_bytes)} bytes)"
    )

    # Page count should be ≥10 with all sections rendered. The MC page is
    # one of the conditionals, so missing it would shave off 1 page.
    page_count = _count_pdf_pages(pdf_bytes)
    assert page_count >= 10, (
        f"PDF has only {page_count} pages — at least one section is missing"
    )

    # Extract text from the decompressed streams and verify Monte Carlo
    # content is present. This catches the specific user-reported regression
    # ("Monte Carlo missing from PDF") that the byte-substring approach
    # couldn't see (compressed streams).
    text = _decode_pdf_text(pdf_bytes)
    assert "Monte Carlo" in text, (
        "Monte Carlo page is missing from the generated PDF. "
        f"PDF has {page_count} pages, decoded {len(text)} chars of text. "
        "Either _mpl_monte_carlo() returned None or the page block silently failed."
    )
