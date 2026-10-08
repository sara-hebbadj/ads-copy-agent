"""Campaign metrics, computed by code (never by the LLM).

Definitions (per ad set, over the chosen days):
- CTR  click-through rate   = clicks / impressions x 100   (%)
- CPC  cost per click       = spend / clicks               (AED)
- CVR  conversion rate      = purchases / clicks x 100     (%)
- CPA  cost per purchase    = spend / purchases            (AED)
- ROAS return on ad spend   = revenue / spend              (AED of revenue per 1 AED spent)

Numbers are rounded to 2 decimals here, once, so the table, the chart and the LLM
summary all use exactly the same values.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ads_agent import DATA_DIR

CAMPAIGN_FILE = DATA_DIR / "campaign.csv"
SUM_COLUMNS = ["spend_aed", "impressions", "clicks", "purchases", "revenue_aed"]


def load_campaign(path: Path = CAMPAIGN_FILE) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["date"])
    missing = set(SUM_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Campaign file is missing columns: {sorted(missing)}")
    return frame


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide, giving NaN (shown as 'n/a') instead of an error when the denominator is 0."""
    return numerator / denominator.where(denominator > 0)


def add_ratios(totals: pd.DataFrame) -> pd.DataFrame:
    out = totals.copy()
    out["ctr_pct"] = safe_divide(out["clicks"], out["impressions"]) * 100
    out["cpc_aed"] = safe_divide(out["spend_aed"], out["clicks"])
    out["cvr_pct"] = safe_divide(out["purchases"], out["clicks"]) * 100
    out["cpa_aed"] = safe_divide(out["spend_aed"], out["purchases"])
    out["roas"] = safe_divide(out["revenue_aed"], out["spend_aed"])
    return out.round(2)


def ad_set_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per ad set with totals and ratios, best ROAS first."""
    totals = frame.groupby(["ad_set_id", "ad_set_name"], as_index=False)[SUM_COLUMNS].sum()
    return add_ratios(totals).sort_values("roas", ascending=False).reset_index(drop=True)


def campaign_totals(frame: pd.DataFrame) -> dict:
    """Whole-campaign totals and ratios as a plain dict."""
    totals = frame[SUM_COLUMNS].sum().to_frame().T
    row = add_ratios(totals).iloc[0].to_dict()
    row["days"] = int(frame["date"].nunique())
    row["ad_sets"] = int(frame["ad_set_id"].nunique())
    row["start"] = frame["date"].min().date().isoformat()
    row["end"] = frame["date"].max().date().isoformat()
    return row


def trend_table(frame: pd.DataFrame, window_days: int = 7) -> pd.DataFrame:
    """Compare the last `window_days` with the `window_days` before them, per ad set."""
    last_day = frame["date"].max()
    last_start = last_day - pd.Timedelta(days=window_days - 1)
    prev_start = last_start - pd.Timedelta(days=window_days)
    last = ad_set_metrics(frame[frame["date"] >= last_start])
    prev = ad_set_metrics(frame[(frame["date"] >= prev_start) & (frame["date"] < last_start)])

    merged = prev.merge(last, on=["ad_set_id", "ad_set_name"], suffixes=("_prev", "_last"))
    columns = ["ad_set_id"]
    for metric in ["ctr_pct", "cpa_aed", "roas"]:
        change = safe_divide(merged[f"{metric}_last"] - merged[f"{metric}_prev"],
                             merged[f"{metric}_prev"]) * 100
        merged[f"{metric}_change_pct"] = change.round(2)
        columns += [f"{metric}_prev", f"{metric}_last", f"{metric}_change_pct"]
    # Current daily budget = average daily spend in the most recent window.
    merged["avg_daily_spend_aed"] = (merged["spend_aed_last"] / window_days).round(2)
    return merged[columns + ["avg_daily_spend_aed"]]


def daily_roas(frame: pd.DataFrame) -> pd.DataFrame:
    """Date x ad set table of daily ROAS, used for the chart."""
    daily = frame.groupby(["date", "ad_set_id"], as_index=False)[SUM_COLUMNS].sum()
    daily = add_ratios(daily)
    return daily.pivot(index="date", columns="ad_set_id", values="roas")
