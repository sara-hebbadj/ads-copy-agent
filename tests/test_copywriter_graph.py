"""Tests for drafting, the LangGraph workflow and the approval guardrails (fake model only)."""

import json

import pytest

from ads_agent.approval import apply_decision
from ads_agent.briefs import load_brief
from ads_agent.copywriter import build_prompt, clean_variants, draft_variants
from ads_agent.graph import build_graph, finish_run, start_run
from ads_agent.llm import FakeLLM, parse_json_answer

RETINOL = "b10-retinol-0-3-night-serum"  # needs "Patch test first."
SUNSCREEN = "b21-sun-stick-spf-50"


def test_prompt_contains_limits_disclaimers_and_banned_words():
    system, user = build_prompt(load_brief(RETINOL))
    assert "Product: Retinol 0.3% Night Serum" in user
    assert "at most 125 characters" in user and "at most 27 characters" in user
    assert "Patch test first." in user
    assert "miracle" in user  # brand-banned word
    assert "JSON" in system
    _, sun_user = build_prompt(load_brief(SUNSCREEN))
    assert "waterproof" in sun_user  # brief-specific banned word


def test_clean_variants_numbers_per_language_and_drops_others():
    brief = load_brief(RETINOL)
    raw = [{"language": "en", "primary_text": "a", "headline": "b", "cta": "shop_now"},
           {"language": "EN", "primary_text": "c", "headline": "d"},
           {"language": "de", "primary_text": "e", "headline": "f"}]
    variants = clean_variants(raw, brief)
    assert [v["id"] for v in variants] == ["en-1", "en-2"]
    assert variants[0]["cta"] == "SHOP_NOW" and variants[1]["cta"] == "SHOP_NOW"


def test_draft_with_fake_model_gives_three_per_language():
    variants = draft_variants(load_brief(RETINOL), FakeLLM())
    assert len(variants) == 9
    assert {v["language"] for v in variants} == {"en", "ar", "fr"}


def test_draft_rejects_non_json_answer():
    with pytest.raises(ValueError):
        draft_variants(load_brief(RETINOL), FakeLLM({"draft": "Sorry, I cannot help."}))


def test_parse_json_answer_handles_code_fences():
    assert parse_json_answer('```json\n{"a": 1}\n```') == {"a": 1}


def test_graph_pauses_for_human_then_logs_decisions(tmp_path):
    log = tmp_path / "log.jsonl"
    graph = build_graph(FakeLLM(), log_file=log, reviewer="tester")
    config, variants = start_run(graph, load_brief(RETINOL))
    assert len(variants) == 9
    # The fake drafts miss the required "Patch test first." line, so they fail the checker.
    assert not variants[0]["check"]["passed"]

    fixed = "Meet our Retinol 0.3% Night Serum for a light evening step. Patch test first."
    records = finish_run(graph, config, [
        {"variant_id": "en-1", "action": "approve"},
        {"variant_id": "en-2", "action": "edit", "edited": {"primary_text": fixed}},
        {"variant_id": "en-3", "action": "reject"},
    ])
    statuses = {r["variant_id"]: r["status"] for r in records}
    assert statuses == {"en-1": "blocked", "en-2": "approved_after_edit", "en-3": "rejected"}

    logged = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(logged) == 3
    assert all(r["posted"] is False and r["reviewer"] == "tester" for r in logged)


def test_edit_that_still_fails_is_blocked():
    brief = load_brief(RETINOL)
    variant = {"id": "en-1", "language": "en", "primary_text": "x", "headline": "y",
               "cta": "SHOP_NOW", "check": {"passed": True, "issues": []}}
    decision = {"action": "edit", "edited": {"primary_text": "This serum cures acne."}}
    record = apply_decision(variant, decision, brief, reviewer="t")
    assert record["status"] == "blocked"
    assert "medical_claim" in record["note"]


def test_unknown_action_raises():
    variant = {"id": "en-1", "language": "en", "primary_text": "x", "headline": "y",
               "cta": "SHOP_NOW", "check": {"passed": True, "issues": []}}
    with pytest.raises(ValueError):
        apply_decision(variant, {"action": "post"}, load_brief(RETINOL), reviewer="t")
