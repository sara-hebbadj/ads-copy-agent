"""Data sanity checks, the eval scoring code, the dry-run pipeline and the LLM client."""

import csv
import json

import pytest

from ads_agent import DATA_DIR
from ads_agent import llm as llm_module
from ads_agent.briefs import list_briefs
from ads_agent.campaign import load_campaign
from ads_agent.llm import FakeLLM, LLMClient, MissingSettingError
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
