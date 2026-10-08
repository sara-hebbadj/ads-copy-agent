"""Rule-based budget suggestions. Every suggestion comes with its reasons.

The rules run in this order; the first one that matches decides the action:

1. HOLD   fewer than MIN_PURCHASES purchases: too little data to judge.
2. PAUSE  ROAS below 1.0: the ad set brings back less revenue than it costs.
3. CUT    ROAS below break-even (1 / gross margin): it loses money after product costs.
4. KEEP   click rate fell by FATIGUE_CTR_DROP_PCT or more: refresh the creative first.
5. SCALE  ROAS at or above target, both overall and in the last 7 days.
6. KEEP   everything else.

The thresholds are ASSUMPTIONS for this demo, not Meta rules. A real team would set
them from its own margins and goals. They are constants here so they are easy to change.
Nothing is applied automatically: a person reads the suggestions and decides.
"""

from __future__ import annotations

import pandas as pd

GROSS_MARGIN = 0.65  # assumption: Lumi Skin keeps 65% of revenue after product cost
BREAK_EVEN_ROAS = round(1 / GROSS_MARGIN, 2)  # 1.54
TARGET_ROAS = 2.5  # assumption: the team's goal, leaves room for other costs
MIN_PURCHASES = 30  # assumption: below this, ROAS swings too much to trust
FATIGUE_CTR_DROP_PCT = -25.0  # CTR last 7 days vs previous 7 days
SCALE_STEP = 0.20  # rule of thumb: raise budgets in steps of about 20%
CUT_STEP = 0.30


def decide(metrics: dict, trend: dict) -> tuple[str, float, list[str]]:
    """Return (action, budget multiplier, reasons) for one ad set."""
    roas, purchases = metrics["roas"], metrics["purchases"]
    ctr_change = trend["ctr_pct_change_pct"]

    if purchases < MIN_PURCHASES:
        return "HOLD", 1.0, [
            f"Only {purchases} purchases (minimum {MIN_PURCHASES}): ROAS {roas} is not reliable "
            "yet. Keep the budget and collect more data."
        ]
    if roas < 1.0:
        return "PAUSE", 0.0, [
            f"ROAS {roas} is below 1.0: each AED spent brought back less than 1 AED of revenue."
        ]
    if roas < BREAK_EVEN_ROAS:
        return "CUT", 1 - CUT_STEP, [
            f"ROAS {roas} is below break-even {BREAK_EVEN_ROAS} (gross margin {GROSS_MARGIN:.0%}), "
            f"so it loses money after product costs. Cut by {CUT_STEP:.0%}."
        ]
    if ctr_change <= FATIGUE_CTR_DROP_PCT:
        return "KEEP", 1.0, [
            f"CTR changed {ctr_change}% (from {trend['ctr_pct_prev']}% to "
            f"{trend['ctr_pct_last']}%) in the last 7 days: likely ad fatigue. "
            "Refresh the creative before adding budget."
        ]
    if roas >= TARGET_ROAS and trend["roas_last"] >= TARGET_ROAS:
        return "SCALE", 1 + SCALE_STEP, [
            f"ROAS {roas} overall and {trend['roas_last']} in the last 7 days, both at or above "
            f"target {TARGET_ROAS}. Increase by {SCALE_STEP:.0%} and watch CPA."
        ]
    return "KEEP", 1.0, [
        f"ROAS {roas} (last 7 days {trend['roas_last']}) is between break-even "
        f"{BREAK_EVEN_ROAS} and a steady result at target {TARGET_ROAS}. No change."
    ]


def suggest_budgets(metrics: pd.DataFrame, trends: pd.DataFrame) -> pd.DataFrame:
    """One row per ad set: action, current and suggested daily budget, reasons."""
    trends_by_id = trends.set_index("ad_set_id").to_dict("index")
    rows = []
    for row in metrics.to_dict("records"):
        trend = trends_by_id[row["ad_set_id"]]
        action, multiplier, reasons = decide(row, trend)
        current = trend["avg_daily_spend_aed"]
        suggested = round(current * multiplier, 2)
        rows.append(
            {
                "ad_set_id": row["ad_set_id"],
                "action": action,
                "current_daily_aed": current,
                "suggested_daily_aed": suggested,
                "change_aed": round(suggested - current, 2),
                "reasons": " ".join(reasons),
            }
        )
    return pd.DataFrame(rows)


def budget_shift(suggestions: pd.DataFrame) -> dict:
    """How much daily budget is freed by cuts and how much the scale-ups need."""
    freed = -suggestions.loc[suggestions["change_aed"] < 0, "change_aed"].sum()
    added = suggestions.loc[suggestions["change_aed"] > 0, "change_aed"].sum()
    return {
        "current_total_daily_aed": round(float(suggestions["current_daily_aed"].sum()), 2),
        "suggested_total_daily_aed": round(float(suggestions["suggested_daily_aed"].sum()), 2),
        "freed_daily_aed": round(float(freed), 2),
        "added_daily_aed": round(float(added), 2),
    }


ASSUMPTIONS = (
    f"Assumptions: gross margin {GROSS_MARGIN:.0%} (break-even ROAS {BREAK_EVEN_ROAS}), "
    f"target ROAS {TARGET_ROAS}, at least {MIN_PURCHASES} purchases before judging, "
    f"fatigue when CTR drops {abs(FATIGUE_CTR_DROP_PCT):.0f}% or more week on week, "
    f"scale in steps of {SCALE_STEP:.0%}. Synthetic data; suggestions only, nothing is changed."
)
