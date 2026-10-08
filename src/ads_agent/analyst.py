"""Campaign analyst: code computes, the LLM only explains.

1. `analyse(frame)` runs the code: metrics, 7-day trends, budget suggestions.
2. `build_facts(...)` turns those tables into plain text lines ("FACTS").
3. `summarize(facts, llm)` asks the model to explain the FACTS without new numbers.
   Without a model, `template_summary(...)` writes a fixed-format summary instead.
4. `verify_numbers(summary, facts)` checks that every number in the summary appears in
   the FACTS (allowing rounding). Any other number is listed as a mismatch.
"""

from __future__ import annotations

import re

import pandas as pd

from ads_agent.budget import ASSUMPTIONS, budget_shift, suggest_budgets
from ads_agent.campaign import ad_set_metrics, campaign_totals, trend_table

SUMMARY_SYSTEM = """You are a marketing analyst writing for a small marketing team.
Explain the campaign results below in plain English, in at most 180 words.
Rules:
- Use ONLY numbers that appear in FACTS, copied exactly as written (same rounding and units).
- Do not calculate anything new: no sums, differences, averages or percentages of your own.
- Cover: the overall result, what works, what does not, the suggested budget changes and why,
  and one caution about the data (for example a small sample).
- These are suggestions for a person to approve. Never say a change has been made."""


def analyse(frame: pd.DataFrame) -> dict:
    """Run all deterministic analysis on a campaign frame."""
    metrics = ad_set_metrics(frame)
    trends = trend_table(frame)
    suggestions = suggest_budgets(metrics, trends)
    return {
        "totals": campaign_totals(frame),
        "metrics": metrics,
        "trends": trends,
        "suggestions": suggestions,
        "shift": budget_shift(suggestions),
    }


def money(value: float) -> str:
    return f"AED {value:,.2f}"


def build_facts(analysis: dict) -> str:
    """Write the computed numbers as text lines. This is the only input the LLM gets."""
    t = analysis["totals"]
    lines = [
        f"FACTS (synthetic campaign, {t['start']} to {t['end']}, {t['days']} days, "
        f"{t['ad_sets']} ad sets, currency AED)",
        f"- Campaign total: spend {money(t['spend_aed'])}; revenue {money(t['revenue_aed'])}; "
        f"purchases {int(t['purchases'])}; ROAS {t['roas']:.2f}; CPA {money(t['cpa_aed'])}; "
        f"CTR {t['ctr_pct']:.2f}%.",
    ]
    trends = analysis["trends"].set_index("ad_set_id").to_dict("index")
    suggestions = analysis["suggestions"].set_index("ad_set_id").to_dict("index")
    for m in analysis["metrics"].to_dict("records"):
        tr, s = trends[m["ad_set_id"]], suggestions[m["ad_set_id"]]
        lines.append(
            f"- {m['ad_set_id']} ({m['ad_set_name']}): spend {money(m['spend_aed'])}; "
            f"revenue {money(m['revenue_aed'])}; purchases {int(m['purchases'])}; "
            f"ROAS {m['roas']:.2f}; CPA {money(m['cpa_aed'])}; CTR {m['ctr_pct']:.2f}%; "
            f"CPC {money(m['cpc_aed'])}; CVR {m['cvr_pct']:.2f}%. "
            f"Last 7 days vs previous 7 days: ROAS {tr['roas_prev']:.2f} -> {tr['roas_last']:.2f} "
            f"({tr['roas_change_pct']:.2f}%); CTR {tr['ctr_pct_prev']:.2f}% -> "
            f"{tr['ctr_pct_last']:.2f}% ({tr['ctr_pct_change_pct']:.2f}%). "
            f"Suggestion: {s['action']} from {money(s['current_daily_aed'])} to "
            f"{money(s['suggested_daily_aed'])} per day. Reason: {s['reasons']}"
        )
    sh = analysis["shift"]
    lines.append(
        f"- Budget shift: current {money(sh['current_total_daily_aed'])} per day -> suggested "
        f"{money(sh['suggested_total_daily_aed'])} per day; cuts free "
        f"{money(sh['freed_daily_aed'])} per day; increases add {money(sh['added_daily_aed'])} "
        "per day."
    )
    lines.append(f"- {ASSUMPTIONS}")
    return "\n".join(lines)


def summarize(facts: str, llm) -> str:
    return llm.complete(SUMMARY_SYSTEM, facts, task="summary", temperature=0.2)


def template_summary(analysis: dict) -> str:
    """Offline summary built from the same numbers (used when no API key is set)."""
    t, sh = analysis["totals"], analysis["shift"]
    s = analysis["suggestions"].set_index("ad_set_id")
    m = analysis["metrics"]
    best, worst = m.iloc[0], m.iloc[-1]
    parts = [
        f"Over {t['days']} days the campaign spent {money(t['spend_aed'])} and returned "
        f"{money(t['revenue_aed'])} (ROAS {t['roas']:.2f}).",
        f"Best: {best['ad_set_id']} (ROAS {best['roas']:.2f}). "
        f"Weakest: {worst['ad_set_id']} (ROAS {worst['roas']:.2f}).",
    ]
    for ad_set_id, row in s.iterrows():
        parts.append(f"{ad_set_id}: {row['action']}. {row['reasons']}")
    parts.append(
        f"Suggested total: {money(sh['suggested_total_daily_aed'])} per day instead of "
        f"{money(sh['current_total_daily_aed'])}. A person must approve any change."
    )
    return "\n".join(parts)


# --- Number check -----------------------------------------------------------------------------

# A number not glued to a letter, dot, hyphen or slash before it (so "2026-09-08" yields
# only "2026", and an ID like "b10" yields nothing).
NUMBER = re.compile(r"(?<![\w.\-/])-?\d[\d,]*(?:\.\d+)?")


def extract_numbers(text: str) -> list[str]:
    return [m.group().rstrip(",") for m in NUMBER.finditer(text)]


def to_float(number: str) -> float:
    return float(number.replace(",", ""))


def number_matches(number: str, allowed: list[float]) -> bool:
    """True if `number` equals an allowed value after rounding to the same decimals.

    The sign is ignored, so "fell 36.46%" matches "-36.46%".
    """
    decimals = len(number.split(".")[1]) if "." in number else 0
    value = abs(to_float(number))
    return any(abs(round(abs(a), decimals) - value) < 1e-9 for a in allowed)


def verify_numbers(summary: str, facts: str) -> dict:
    allowed = [to_float(n) for n in extract_numbers(facts)]
    found = extract_numbers(summary)
    mismatches = [n for n in found if not number_matches(n, allowed)]
    return {
        "numbers_checked": len(found),
        "numbers_matched": len(found) - len(mismatches),
        "mismatches": mismatches,
        "ok": not mismatches,
    }
