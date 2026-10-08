"""Tests for the analyst: facts text, template summary and the number check."""

from ads_agent.analyst import (
    analyse,
    build_facts,
    extract_numbers,
    summarize,
    template_summary,
    verify_numbers,
)
from ads_agent.campaign import load_campaign
from ads_agent.llm import FakeLLM

FACTS = "- x: spend AED 8,729.52; ROAS 5.01; CTR changed -36.46% on 2026-10-07; 30 days."


def test_extract_numbers_skips_date_parts_and_ids():
    assert extract_numbers("b10 on 2026-10-07 cost AED 1,205.11, ROAS 2.5.") == [
        "2026", "1,205.11", "2.5"
    ]


def test_rounded_numbers_match_and_invented_numbers_do_not():
    ok = verify_numbers("Spend was AED 8,730 with ROAS 5.0; CTR fell 36%.", FACTS)
    assert ok["ok"] and ok["numbers_checked"] == 3
    bad = verify_numbers("ROAS 5.3 and spend AED 9,000.", FACTS)
    assert bad["mismatches"] == ["5.3", "9,000"]


def test_facts_cover_every_ad_set_and_template_summary_passes_check():
    analysis = analyse(load_campaign())
    facts = build_facts(analysis)
    for ad_set_id in analysis["metrics"]["ad_set_id"]:
        assert ad_set_id in facts
    result = verify_numbers(template_summary(analysis), facts)
    assert result["ok"], result["mismatches"]


def test_summarize_sends_only_facts_to_the_model():
    llm = FakeLLM({"summary": "ROAS 5.01 is the best."})
    text = summarize(FACTS, llm)
    assert text == "ROAS 5.01 is the best."
    assert llm.calls[0]["user"] == FACTS
    assert "ONLY numbers" in llm.calls[0]["system"]
