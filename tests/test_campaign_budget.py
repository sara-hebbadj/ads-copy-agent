"""Tests for metrics and budget rules, using small hand-made numbers."""

import math

import pandas as pd
import pytest

from ads_agent.budget import BREAK_EVEN_ROAS, budget_shift, decide, suggest_budgets
from ads_agent.campaign import ad_set_metrics, add_ratios, load_campaign, trend_table


def tiny_frame():
    rows = []
    for day in range(14):
        date = pd.Timestamp("2026-09-01") + pd.Timedelta(days=day)
        # "a": constant; "b": clicks halve in the last 7 days
        rows.append(dict(date=date, ad_set_id="a", ad_set_name="A", spend_aed=100.0,
                         impressions=10_000, clicks=100, purchases=5, revenue_aed=400.0))
        clicks_b = 100 if day < 7 else 50
        rows.append(dict(date=date, ad_set_id="b", ad_set_name="B", spend_aed=50.0,
                         impressions=10_000, clicks=clicks_b, purchases=1, revenue_aed=40.0))
    return pd.DataFrame(rows)


def test_ratio_formulas():
    row = add_ratios(pd.DataFrame([dict(spend_aed=200.0, impressions=10_000, clicks=100,
                                        purchases=4, revenue_aed=600.0)])).iloc[0]
    assert row["ctr_pct"] == 1.0  # 100 / 10,000 x 100
    assert row["cpc_aed"] == 2.0  # 200 / 100
    assert row["cvr_pct"] == 4.0  # 4 / 100 x 100
    assert row["cpa_aed"] == 50.0  # 200 / 4
    assert row["roas"] == 3.0  # 600 / 200


def test_zero_purchases_gives_nan_not_error():
    row = add_ratios(pd.DataFrame([dict(spend_aed=10.0, impressions=100, clicks=0,
                                        purchases=0, revenue_aed=0.0)])).iloc[0]
    assert math.isnan(row["cpa_aed"]) and math.isnan(row["cpc_aed"])


def test_metrics_sorted_by_roas_and_trend_detects_ctr_drop():
    frame = tiny_frame()
    metrics = ad_set_metrics(frame)
    assert list(metrics["ad_set_id"]) == ["a", "b"]
    trends = trend_table(frame).set_index("ad_set_id")
    assert trends.loc["b", "ctr_pct_change_pct"] == -50.0
    assert trends.loc["a", "avg_daily_spend_aed"] == 100.0


def metrics_row(roas, purchases=100):
    return {"roas": roas, "purchases": purchases}


def trend_row(ctr_change=0.0, roas_last=3.0):
    return {"ctr_pct_change_pct": ctr_change, "ctr_pct_prev": 2.0, "ctr_pct_last": 1.0,
            "roas_last": roas_last}


@pytest.mark.parametrize(
    "metrics, trend, action",
    [
        (metrics_row(5.0, purchases=9), trend_row(), "HOLD"),
        (metrics_row(0.6), trend_row(), "PAUSE"),
        (metrics_row(BREAK_EVEN_ROAS - 0.1), trend_row(), "CUT"),
        (metrics_row(4.0), trend_row(ctr_change=-30.0), "KEEP"),
        (metrics_row(4.0), trend_row(roas_last=3.0), "SCALE"),
        (metrics_row(4.0), trend_row(roas_last=2.0), "KEEP"),
        (metrics_row(2.0), trend_row(), "KEEP"),
    ],
)
def test_budget_rules(metrics, trend, action):
    got, multiplier, reasons = decide(metrics, trend)
    assert got == action
    assert reasons and all(isinstance(r, str) for r in reasons)


def test_suggestions_on_the_synthetic_campaign():
    frame = load_campaign()
    suggestions = suggest_budgets(ad_set_metrics(frame), trend_table(frame))
    actions = suggestions.set_index("ad_set_id")["action"].to_dict()
    assert actions == {
        "vitc-ar-stories": "SCALE",
        "nightcream-fr-retarget": "KEEP",
        "vitc-en-igfeed": "SCALE",
        "eyepatch-en-reels-test": "HOLD",
        "cleanser-ar-fbfeed-lal": "CUT",
        "spf-en-fbfeed-broad": "PAUSE",
    }
    shift = budget_shift(suggestions)
    assert shift["suggested_total_daily_aed"] < shift["current_total_daily_aed"]
