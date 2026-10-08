"""Data sanity checks, the eval scoring code, the dry-run pipeline and the LLM client."""

import csv
import json
import re

import pytest

from ads_agent import DATA_DIR, DOCS_DIR
from ads_agent import llm as llm_module
from ads_agent.briefs import list_briefs
from ads_agent.campaign import load_campaign
from ads_agent.checker import llm_review
from ads_agent.llm import FakeLLM, LLMClient, MissingSettingError
from evals import compare_judges
from evals import run as evals_run


def test_campaign_file_shape_and_sanity():
    frame = load_campaign()
    assert len(frame) == 180
    assert frame["ad_set_id"].nunique() == 6 and frame["date"].nunique() == 30
    assert (frame[["spend_aed", "impressions", "clicks", "purchases"]] >= 0).all().all()
    assert (frame["clicks"] <= frame["impressions"]).all()
    assert (frame["purchases"] <= frame["clicks"]).all()


def test_thirty_briefs_for_in_stock_products():
    with (DATA_DIR / "products.csv").open(encoding="utf-8") as f:
        stock = {p["id"]: int(p["stock"]) for p in csv.DictReader(f)}
    briefs = list_briefs()
    assert len(briefs) == 30
    assert all(stock[b["product_id"]] > 0 for b in briefs)


@pytest.mark.parametrize("split, size", [("dev", 24), ("test", 48)])
def test_eval_cases_are_balanced_and_unique(split, size):
    cases = evals_run.load_cases(split)
    assert len(cases) == size
    assert len({c["id"] for c in cases}) == size
    assert sum(c["label"] == "violating" for c in cases) == size // 2
    for language in ("en", "ar", "fr"):
        assert sum(c["language"] == language for c in cases) == size // 3


def test_score_precision_recall():
    rows = [
        {"language": "en", "label": "violating", "predicted": "violating"},
        {"language": "en", "label": "violating", "predicted": "compliant"},
        {"language": "ar", "label": "compliant", "predicted": "violating"},
        {"language": "fr", "label": "compliant", "predicted": "compliant"},
    ]
    result = evals_run.score(rows)
    assert (result["tp"], result["fp"], result["fn"], result["tn"]) == (1, 1, 1, 1)
    assert result["precision"] == 0.5 and result["recall"] == 0.5


def test_policy_rules_eval_writes_files(tmp_path):
    summary = evals_run.run_policy_rules(tmp_path)
    assert summary["dev"]["n"] == 24 and summary["test"]["n"] == 48
    assert (tmp_path / "policy_rules_test.csv").exists()


def test_dry_run_pipeline_end_to_end(tmp_path):
    trace = tmp_path / "traces.jsonl"
    copy = evals_run.run_copy(tmp_path, "cheap", limit=2, dry_run=True, trace=trace)
    analyst = evals_run.run_analyst(tmp_path, "cheap", limit=2, dry_run=True, trace=trace)
    policy = evals_run.run_policy_llm(tmp_path, "cheap", limit=4, dry_run=True, trace=trace)
    assert copy["variants"] == 18 and copy["writer_model"] == "fake/offline-canned"
    assert analyst["summaries"] == 2
    assert policy["llm_only"]["n"] == 4
    traces = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    assert traces and all(t["outcome"] == "fake" for t in traces)


def test_judge_sees_offer_required_sentence_and_brand_voice():
    """Judge v1 never saw these, so it marked down the offer lines the brief requires."""
    brief = next(b for b in list_briefs() if b.get("offer") and b.get("required_disclaimers"))
    variant = {"language": "en", "primary_text": "Hi", "headline": "Hi", "cta": "SHOP_NOW"}
    fake = FakeLLM()
    evals_run.judge_variant(fake, brief, variant)
    user = json.loads(fake.calls[0]["user"])
    assert user["brief"]["offer"] == brief["offer"]
    assert user["brief"]["required_sentence"] == brief["required_disclaimers"]["en"]
    assert evals_run.load_brand()["voice"] in fake.calls[0]["system"]


def test_rejudge_scores_the_same_saved_drafts(tmp_path):
    trace = tmp_path / "traces.jsonl"
    evals_run.run_copy(tmp_path, "cheap", limit=1, dry_run=True, trace=trace)
    summary = evals_run.run_rejudge(tmp_path, tmp_path / "copy_dry_run.csv", True, trace)
    assert summary["variants"] == 9 and summary["judge_version"] == evals_run.JUDGE_VERSION
    with (tmp_path / "copy_rejudge_dry_run.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [r["variant_id"] for r in rows][:3] == ["en-1", "en-2", "en-3"]
    comparison = compare_judges.compare(
        tmp_path / "copy_dry_run.csv", tmp_path / "copy_rejudge_dry_run.csv"
    )
    assert comparison["brand_fit_change"] == {"up": 0, "same": 9, "down": 0}
    assert comparison["new"]["brief_has_offer"]["True"]["n"] == 9  # brief b01 has an offer


def test_policy_llm_smoke_split_uses_dev_cases(tmp_path):
    trace = tmp_path / "traces.jsonl"
    summary = evals_run.run_policy_llm(
        tmp_path, "cheap", limit=3, dry_run=True, trace=trace, split="dev"
    )
    assert summary["split"] == "dev" and summary["rules_only"]["n"] == 3
    assert summary["llm_unreadable"] == 0
    assert (tmp_path / "policy_llm_dev_dry_run.csv").exists()


def test_llm_reviewer_is_told_that_code_checks_length_and_cta():
    """Live run 1 (dev set): without this note the model failed every ad for 'no CTA'."""
    fake = FakeLLM()
    llm_review({"language": "en", "primary_text": "Hello", "headline": "Hi"}, fake)
    system = fake.calls[0]["system"]
    assert "Judge the wording against items 1 to 6" in system


def test_checklist_shares_no_sentence_with_held_out_cases():
    """The checklist is the LLM reviewer's prompt: no test sentence may leak into it."""

    def word_runs(text: str, size: int = 4) -> set[str]:
        words = re.findall(r"\w+", text.lower())
        return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}

    checklist = word_runs((DOCS_DIR / "policy_checklist.md").read_text(encoding="utf-8"))
    for case in evals_run.load_cases("test"):
        for field in ("primary_text", "headline"):
            assert not word_runs(case[field]) & checklist, case["id"]


def test_real_client_needs_a_key(monkeypatch):
    monkeypatch.setattr(llm_module, "ENV_FILES", [])  # never read a real .env in tests
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(MissingSettingError):
        LLMClient("cheap")


def test_model_ids_come_from_env(monkeypatch):
    monkeypatch.setattr(llm_module, "ENV_FILES", [])
    monkeypatch.setenv("MODEL_JUDGE", "vendor/judge-model")
    monkeypatch.setenv("MODEL_CHEAP", "")
    assert llm_module.model_for_role("judge") == "vendor/judge-model"
    with pytest.raises(MissingSettingError):
        llm_module.model_for_role("cheap")


def test_fake_llm_writes_trace(tmp_path):
    trace = tmp_path / "t.jsonl"
    FakeLLM(trace_file=trace).complete("s", "u", task="judge")
    record = json.loads(trace.read_text(encoding="utf-8"))
    assert record["model"] == "fake/offline-canned" and record["cost_usd"] == 0.0
