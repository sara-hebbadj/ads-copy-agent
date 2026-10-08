# Evaluations

| Task | Command | Needs a key? | Output |
|---|---|---|---|
| Policy checker, code rules only | `python -m evals.run --task policy` | No | `results/policy_rules_*.csv`, `results/policy_rules_summary.json` |
| Policy checker with the LLM review layer | `python -m evals.run --task policy-llm --model cheap` | Yes | `results/policy_llm_<family>_<date>*` |
| Copy quality (drafts → rule check → judge) | `python -m evals.run --task copy --model main --limit 10` | Yes | `results/copy_<family>_<date>*`; the CSV is also Sara's rating sheet |
| Analyst number check | `python -m evals.run --task analyst --model cheap` | Yes | `results/analyst_<family>_<date>*` |
| Everything | `python -m evals.run --model cheap --limit 10` | Partly | LLM tasks print `PENDING` if there's no key |
| Pipeline check with a fake model | `python -m evals.run --dry-run` | No | `dry_run/`. **Not results.** |

Each model call is appended to `traces.jsonl` with the model, tokens, cost, latency and outcome. A run stops if it costs more than `MAX_COST_PER_RUN_USD`. The judge must come from a different model family than the writer, and the runner refuses to start otherwise.

## Policy cases (`data/`)

- `policy_cases_dev.jsonl` has 24 cases: 8 per language, half violating. They were written together with the rules and used while building them. Scores on this set are optimistic by design.
- `policy_cases_test.jsonl` has 48 held-out cases: 16 per language, half violating, following `docs/policy_checklist.md`. They were written after the last rule change. The checker was run on them once, and the rule files haven't changed since. `policy_rules_summary.json` stores the SHA-256 of the rule files, so the result is tied to the exact rules that produced it.
- Caveat: the same coding agent wrote both the rules and the test cases, so it knew roughly what the rules can and can't catch. A test set written by someone else (Sara) would be a stronger check.
- A violating case breaks one of the 8 checklist items. Some test cases are in categories the code rules don't cover on purpose (sensational hooks, for example). Those are there to show what the LLM layer or a person must catch.
- The labels were written by a coding agent. The Arabic and French cases still need review by a native speaker (Sara).

Precision and recall are reported for the "violating" class:

- precision = flagged and truly violating ÷ all flagged
- recall = flagged and truly violating ÷ all truly violating

## Analyst check

Five scenarios: all 30 days, the first 15 days, the last 15 days, the Arabic ad sets and the English ad sets. For each one, the LLM explains the computed FACTS, and `verify_numbers` lists any number in the summary that isn't, after rounding, one of the fact numbers. The target is zero mismatches.

The check has two limits:

- It can't tell whether a correct number is attached to the right metric.
- It can't check numbers written as words.
