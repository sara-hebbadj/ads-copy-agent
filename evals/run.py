"""Evaluation runner. One command per task; results go to evals/results/.

    python -m evals.run --task policy                         # code rules only, no LLM (runs now)
    python -m evals.run --task policy-llm --model cheap --split dev   # smoke run, dev set
    python -m evals.run --task policy-llm --model cheap              # held-out set, once
    python -m evals.run --task copy --model cheap --limit 10   # drafts + rule check + judge
    python -m evals.run --task copy-rejudge --source evals/results/copy_<family>_<date>.csv
    python -m evals.run --task analyst --model cheap
    python -m evals.run --model cheap --limit 10               # everything (--task all)
    python -m evals.run --dry-run                              # fake model, writes evals/dry_run/

--dry-run uses FakeLLM (canned answers). Its numbers are NOT results: they only prove
that the pipeline runs end to end. Dry-run files go to evals/dry_run/ so they are never
mixed up with real results.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd

from ads_agent import EVALS_DIR, REPO_ROOT
from ads_agent.analyst import analyse, build_facts, summarize, verify_numbers
from ads_agent.briefs import list_briefs
from ads_agent.campaign import load_campaign
from ads_agent.checker import check_ad, llm_review, load_brand
from ads_agent.copywriter import LANGUAGE_NAMES, draft_variants
from ads_agent.llm import FakeLLM, LLMClient, MissingSettingError, parse_json_answer

CASES_DIR = EVALS_DIR / "data"
RULE_FILES = ["src/ads_agent/policy_rules.py", "src/ads_agent/checker.py", "data/brand.json"]
TODAY = date.today().isoformat()


# --- Small helpers --------------------------------------------------------------------------


def load_cases(split: str) -> list[dict]:
    path = CASES_DIR / f"policy_cases_{split}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rules_fingerprint() -> dict:
    """SHA-256 of the rule files, so a result can be tied to the exact rules that made it."""
    return {
        name: hashlib.sha256((REPO_ROOT / name).read_bytes()).hexdigest()[:16]
        for name in RULE_FILES
    }


def score(rows: list[dict], predicted_key: str = "predicted") -> dict:
    """Precision and recall for the 'violating' class, overall and per language."""

    def counts(subset: list[dict]) -> dict:
        tp = sum(r["label"] == "violating" and r[predicted_key] == "violating" for r in subset)
        fp = sum(r["label"] == "compliant" and r[predicted_key] == "violating" for r in subset)
        fn = sum(r["label"] == "violating" and r[predicted_key] == "compliant" for r in subset)
        tn = len(subset) - tp - fp - fn
        return {
            "n": len(subset),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "accuracy": round((tp + tn) / len(subset), 3) if subset else None,
        }

    result = counts(rows)
    result["by_language"] = {
        lang: counts([r for r in rows if r["language"] == lang]) for lang in ("en", "ar", "fr")
    }
    return result


def make_client(role: str, dry_run: bool, trace_file: Path):
    if dry_run:
        return FakeLLM(trace_file=trace_file)
    return LLMClient(role, trace_file=trace_file)


def model_family(model_id: str) -> str:
    return model_id.split("/")[0]


# --- Task 1: code rules on labelled ad texts (deterministic, no LLM) --------------------------


def run_policy_rules(out_dir: Path) -> dict:
    summary = {"task": "policy_rules", "date": TODAY, "rules_sha256": rules_fingerprint()}
    for split in ("dev", "test"):
        rows = []
        for case in load_cases(split):
            result = check_ad(case, case["placement"])
            rows.append(
                {
                    "id": case["id"],
                    "language": case["language"],
                    "label": case["label"],
                    "predicted": "compliant" if result.passed else "violating",
                    "failed_rules": ";".join(result.failed_rules),
                    "checker_output": result.summary(),
                    "primary_text": case["primary_text"],
                    "headline": case["headline"],
                }
            )
        write_csv(out_dir / f"policy_rules_{split}.csv", rows)
        summary[split] = score(rows)
    write_json(out_dir / "policy_rules_summary.json", summary)
    return summary


# --- Task 2: LLM review layer on the same cases ---------------------------------------------


def run_policy_llm(
    out_dir: Path, role: str, limit: int | None, dry_run: bool, trace: Path, split: str = "test"
):
    """Rules alone vs rules OR LLM. Use split="dev" for smoke runs, so the held-out
    test set is only sent to the model once, after the prompt is settled."""
    llm = make_client(role, dry_run, trace)
    cases = load_cases(split)[:limit]
    rows = []
    for case in cases:
        rules_result = check_ad(case, case["placement"])
        llm_issues = llm_review(case, llm)
        llm_fail = any(i.severity == "fail" for i in llm_issues)
        rows.append(
            {
                "id": case["id"],
                "language": case["language"],
                "label": case["label"],
                "rules": "compliant" if rules_result.passed else "violating",
                "llm": "violating" if llm_fail else "compliant",
                "combined": "violating" if llm_fail or not rules_result.passed else "compliant",
                # An unreadable answer is a warning, so it counts as "compliant" above.
                "llm_unreadable": any(i.severity == "warn" for i in llm_issues),
                "llm_reasons": "; ".join(i.message for i in llm_issues),
            }
        )
    prefix = "" if split == "test" else f"{split}_"
    tag = prefix + ("dry_run" if dry_run else f"{model_family(llm.model)}_{TODAY}")
    write_csv(out_dir / f"policy_llm_{tag}.csv", rows)
    summary = {
        "task": "policy_llm", "date": TODAY, "model": llm.model, "split": split,
        "rules_sha256": rules_fingerprint(),
        "rules_only": score(rows, "rules"), "llm_only": score(rows, "llm"),
        "rules_or_llm": score(rows, "combined"),
        "llm_unreadable": sum(r["llm_unreadable"] for r in rows),
        "cost_usd": round(llm.total_cost_usd, 4),
    }
    write_json(out_dir / f"policy_llm_{tag}_summary.json", summary)
    return summary


# --- Task 3: copy quality (drafts -> rule check -> judge) -----------------------------------

# v1 (first live run, 8 October 2026) showed the judge only product, audience, key message
# and tone. It then marked down the offer and the required sentences that the brief makes
# compulsory, and it never saw the brand voice. v2 shows the judge all three.
JUDGE_VERSION = "v2"
JUDGE_SYSTEM = """You review ad copy for a skincare brand.
Brand voice: {voice}
Score two things from 1 (poor) to 5 (excellent):
- brand_fit: matches the brief (product, audience, key message, tone) and the brand voice.
  The brief's offer with its terms line, and its required sentence, must appear in the ad:
  don't lower the score for including them, but do lower it if they crowd out the key message.
- language_quality: natural, correct {language} that a native speaker in the UAE would find
  fluent and culturally appropriate (Arabic: correct grammar and gender forms;
  French: correct accents and typography).
Reply with JSON only: {{"brand_fit": 1-5, "language_quality": 1-5, "reason": "one sentence"}}"""


def judge_variant(judge, brief: dict, variant: dict) -> dict:
    language = variant["language"]
    system = JUDGE_SYSTEM.format(language=LANGUAGE_NAMES[language], voice=load_brand()["voice"])
    brief_view = {k: brief[k] for k in ("product", "audience", "key_message", "tone")}
    brief_view["offer"] = brief.get("offer") or "none"
    brief_view["required_sentence"] = (
        brief.get("required_disclaimers", {}).get(language) or "none"
    )
    user = json.dumps(
        {
            "brief": brief_view,
            "ad": {k: variant[k] for k in ("language", "primary_text", "headline", "cta")},
        },
        ensure_ascii=False,
    )
    try:
        return parse_json_answer(judge.complete(system, user, task="judge", temperature=0))
    except (ValueError, json.JSONDecodeError):
        return {"brand_fit": None, "language_quality": None, "reason": "unreadable judge answer"}


def copy_scores(rows: list[dict]) -> dict:
    """Rule pass rate and mean judge scores, overall and per language."""
    if not rows:
        return {}
    frame = pd.DataFrame(rows)
    frame["passed"] = frame["rule_check"] == "pass"

    def stats(group: pd.DataFrame) -> dict:
        brand_fit = pd.to_numeric(group["judge_brand_fit"])
        language_quality = pd.to_numeric(group["judge_language_quality"])
        return {
            "variants": int(len(group)),
            "rule_pass_rate": round(group["passed"].mean(), 3),
            "judge_scored": int(brand_fit.notna().sum()),
            "judge_brand_fit_mean": round(brand_fit.mean(), 2),
            "judge_language_quality_mean": round(language_quality.mean(), 2),
        }

    result = stats(frame)
    result["by_language"] = {lang: stats(group) for lang, group in frame.groupby("language")}
    return result


def judged_row(row: dict, scores: dict) -> dict:
    return {
        **row,
        "judge_brand_fit": scores.get("brand_fit"),
        "judge_language_quality": scores.get("language_quality"),
        "judge_reason": scores.get("reason", ""),
    }


def run_copy(out_dir: Path, role: str, limit: int | None, dry_run: bool, trace: Path):
    writer = make_client(role, dry_run, trace)
    judge = make_client("judge", dry_run, trace)
    if not dry_run and model_family(judge.model) == model_family(writer.model):
        raise SystemExit("MODEL_JUDGE must be from a different model family than the writer.")

    rows, failures = [], []
    briefs = list_briefs()[:limit]
    for brief in briefs:
        try:
            variants = draft_variants(brief, writer)
        except ValueError as exc:
            failures.append({"brief_id": brief["id"], "error": str(exc)})
            continue
        for v in variants:
            check = check_ad(v, brief=brief)
            row = {
                "brief_id": brief["id"], "variant_id": v["id"], "language": v["language"],
                "primary_text": v["primary_text"], "headline": v["headline"], "cta": v["cta"],
                "rule_check": "pass" if check.passed else "fail",
                "failed_rules": ";".join(check.failed_rules),
            }
            rows.append(judged_row(row, judge_variant(judge, brief, v)))
            rows[-1].update(sara_brand_fit="", sara_language_quality="", sara_notes="")
    tag = f"{model_family(writer.model)}_{TODAY}" if not dry_run else "dry_run"
    if rows:
        write_csv(out_dir / f"copy_{tag}.csv", rows)  # also Sara's manual rating sheet
    summary = {
        "task": "copy", "date": TODAY, "writer_model": writer.model, "judge_model": judge.model,
        "judge_version": JUDGE_VERSION,
        "briefs": len(briefs), "briefs_failed_to_parse": failures,
        "cost_usd": round(writer.total_cost_usd + judge.total_cost_usd, 4),
        **copy_scores(rows),
    }
    write_json(out_dir / f"copy_{tag}_summary.json", summary)
    return summary


def run_rejudge(out_dir: Path, source: Path, dry_run: bool, trace: Path):
    """Score saved drafts again with the current judge prompt. No new drafts are written,
    so two judge versions can be compared on exactly the same ads."""
    judge = make_client("judge", dry_run, trace)
    briefs = {brief["id"]: brief for brief in list_briefs()}
    with source.open(encoding="utf-8") as f:
        saved = list(csv.DictReader(f))
    rows = []
    for row in saved:
        variant = {**row, "id": row["variant_id"]}
        rows.append(judged_row(row, judge_variant(judge, briefs[row["brief_id"]], variant)))
    name = f"{source.stem}_judge_{JUDGE_VERSION}" if not dry_run else "copy_rejudge_dry_run"
    write_csv(out_dir / f"{name}.csv", rows)
    summary = {
        "task": "copy_rejudge", "date": TODAY, "source": source.name,
        "judge_model": judge.model, "judge_version": JUDGE_VERSION,
        "cost_usd": round(judge.total_cost_usd, 4), **copy_scores(rows),
    }
    write_json(out_dir / f"{name}_summary.json", summary)
    return summary


# --- Task 4: analyst number check -------------------------------------------------------------

SCENARIOS = {
    "all_30_days": lambda f: f,
    "first_15_days": lambda f: f[f["date"] < f["date"].min() + pd.Timedelta(days=15)],
    "last_15_days": lambda f: f[f["date"] > f["date"].max() - pd.Timedelta(days=15)],
    "arabic_ad_sets": lambda f: f[f["language"] == "ar"],
    "english_ad_sets": lambda f: f[f["language"] == "en"],
}


def run_analyst(out_dir: Path, role: str, limit: int | None, dry_run: bool, trace: Path):
    llm = make_client(role, dry_run, trace)
    frame = load_campaign()
    rows = []
    for name, select in list(SCENARIOS.items())[:limit]:
        facts = build_facts(analyse(select(frame)))
        summary_text = summarize(facts, llm)
        check = verify_numbers(summary_text, facts)
        rows.append(
            {
                "scenario": name,
                "numbers_checked": check["numbers_checked"],
                "numbers_matched": check["numbers_matched"],
                "mismatches": " ".join(check["mismatches"]),
                "summary": summary_text,
            }
        )
    tag = f"{model_family(llm.model)}_{TODAY}" if not dry_run else "dry_run"
    write_csv(out_dir / f"analyst_{tag}.csv", rows)
    checked = sum(r["numbers_checked"] for r in rows)
    matched = sum(r["numbers_matched"] for r in rows)
    summary = {
        "task": "analyst", "date": TODAY, "model": llm.model, "summaries": len(rows),
        "summaries_without_mismatch": sum(not r["mismatches"] for r in rows),
        "numbers_checked": checked, "numbers_matched": matched,
        "cost_usd": round(llm.total_cost_usd, 4),
    }
    write_json(out_dir / f"analyst_{tag}_summary.json", summary)
    return summary


# --- Command line -------------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--task", default="all",
                        choices=["all", "policy", "policy-llm", "copy", "copy-rejudge",
                                 "analyst"])
    parser.add_argument("--model", default="cheap", choices=["main", "cheap"],
                        help="model role under test (the judge is always MODEL_JUDGE)")
    parser.add_argument("--limit", type=int, default=None, help="only the first N items")
    parser.add_argument("--split", default="test", choices=["dev", "test"],
                        help="policy-llm only: dev for smoke runs, test for the held-out run")
    parser.add_argument("--source", type=Path,
                        help="copy-rejudge only: a saved copy_*.csv whose drafts are scored again")
    parser.add_argument("--dry-run", action="store_true", help="fake model; NOT real results")
    args = parser.parse_args()
    if args.task == "copy-rejudge" and args.source is None:
        parser.error("--task copy-rejudge needs --source evals/results/copy_<...>.csv")

    out_dir = EVALS_DIR / ("dry_run" if args.dry_run else "results")
    trace = out_dir / "traces.jsonl" if args.dry_run else EVALS_DIR / "traces.jsonl"
    if args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        trace.unlink(missing_ok=True)  # keep only the latest dry-run trace
        (out_dir / "NOT_RESULTS.md").write_text(
            "# Dry run: not results\n\nEverything in this folder came from `--dry-run`, which "
            "uses FakeLLM canned answers instead of a model. It only proves the pipeline runs "
            "end to end. Never quote these numbers.\n",
            encoding="utf-8",
        )

    tasks = {
        "policy": lambda: run_policy_rules(out_dir),
        "policy-llm": lambda: run_policy_llm(
            out_dir, args.model, args.limit, args.dry_run, trace, args.split
        ),
        "copy": lambda: run_copy(out_dir, args.model, args.limit, args.dry_run, trace),
        "copy-rejudge": lambda: run_rejudge(out_dir, args.source, args.dry_run, trace),
        "analyst": lambda: run_analyst(out_dir, args.model, args.limit, args.dry_run, trace),
    }
    all_tasks = ["policy", "policy-llm", "copy", "analyst"]
    chosen = all_tasks if args.task == "all" else [args.task]
    for name in chosen:
        try:
            summary = tasks[name]()
        except MissingSettingError as exc:  # no key yet: LLM tasks stay pending
            print(f"\n== {name} [PENDING] == {exc}")
            continue
        label = "DRY RUN (fake model, not results)" if args.dry_run else "result"
        print(f"\n== {name} [{label}] ==")
        print(json.dumps(summary, ensure_ascii=False, indent=2)[:2000])
    print(f"\nFiles written to {out_dir}")


if __name__ == "__main__":
    main()
