"""Compare two judge runs on the same saved drafts (e.g. judge v1 and judge v2).

    python -m evals.compare_judges evals/results/copy_openai_2026-10-08.csv \
        evals/results/copy_openai_2026-10-08_judge_v2.csv

Writes evals/results/copy_judge_comparison.json. No model is called.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from ads_agent import EVALS_DIR
from ads_agent.briefs import list_briefs
from evals.run import write_json

SCORES = ["judge_brand_fit", "judge_language_quality"]


def means(frame: pd.DataFrame) -> dict:
    return {
        "n": int(len(frame)),
        **{f"{name}_mean": round(float(frame[name].mean()), 2) for name in SCORES},
    }


def describe(frame: pd.DataFrame) -> dict:
    """Mean scores overall, per language, split by whether the brief has an offer or a
    required sentence (the lines judge v1 was not shown), and by placement and offer."""
    return {
        "overall": means(frame),
        "by_language": {lang: means(group) for lang, group in frame.groupby("language")},
        "brief_has_offer": {str(k): means(g) for k, g in frame.groupby("has_offer")},
        "brief_has_required_sentence": {
            str(k): means(g) for k, g in frame.groupby("has_required_sentence")
        },
        "by_placement_and_offer": {
            f"{place} / {'offer' if offer else 'no offer'}": means(g)
            for (place, offer), g in frame.groupby(["placement", "has_offer"])
        },
    }


def load(path: Path) -> pd.DataFrame:
    briefs = {brief["id"]: brief for brief in list_briefs()}
    frame = pd.read_csv(path)
    frame["has_offer"] = frame["brief_id"].map(lambda b: bool(briefs[b].get("offer")))
    frame["has_required_sentence"] = frame["brief_id"].map(
        lambda b: bool(briefs[b].get("required_disclaimers"))
    )
    frame["placement"] = frame["brief_id"].map(lambda b: briefs[b]["placement"])
    return frame


def compare(old_path: Path, new_path: Path) -> dict:
    old, new = load(old_path), load(new_path)
    if list(old["variant_id"] + old["brief_id"]) != list(new["variant_id"] + new["brief_id"]):
        raise SystemExit("The two files must hold the same drafts in the same order.")
    change = new["judge_brand_fit"] - old["judge_brand_fit"]
    return {
        "old": {"file": old_path.name, **describe(old)},
        "new": {"file": new_path.name, **describe(new)},
        "brand_fit_change": {
            "up": int((change > 0).sum()),
            "same": int((change == 0).sum()),
            "down": int((change < 0).sum()),
        },
    }


if __name__ == "__main__":
    result = compare(Path(sys.argv[1]), Path(sys.argv[2]))
    write_json(EVALS_DIR / "results" / "copy_judge_comparison.json", result)
    print(result["old"]["overall"], result["new"]["overall"], result["brand_fit_change"])
