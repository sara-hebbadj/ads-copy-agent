"""Smoke test for the Gradio handlers (skipped if gradio is not installed)."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("gradio")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import app as demo_app  # noqa: E402


def test_check_tab_flags_a_bad_ad():
    verdict, issues = demo_app.check_text(
        "en", "instagram_feed", "Are you struggling with acne?", "Results guaranteed", "(no brief)"
    )
    assert verdict.startswith("### FAIL")
    assert "personal_attribute" in set(issues["rule"])


def test_analyse_tab_uses_template_without_llm():
    metrics, trends, suggestions, figure, summary = demo_app.run_analysis(use_llm=False)
    assert len(metrics) == 6 and len(suggestions) == 6
    assert "all numbers match the table" in summary


def test_submit_without_draft_is_refused():
    state, table, message = demo_app.submit(None, None)
    assert state is None and table is None and "Draft" in message
