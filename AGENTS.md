# Notes for coding agents: ads-copy-agent

This is a portfolio project for Sara Hebbadj. She must be able to explain every line, so keep functions short and names plain, and comment only where a decision isn't obvious.

## Commands

```bash
uv sync --extra app --extra dev
uv run pytest -q && uv run ruff check .
uv run python -m evals.run --task policy        # deterministic checker eval
uv run python -m evals.run --dry-run            # fake model, writes evals/dry_run/
uv run python app/app.py                        # Gradio demo
uv run python data/make_briefs.py               # regenerate data/briefs/
uv run python data/make_campaign.py             # regenerate data/campaign.csv (seed 42)
uv run python -m ads_agent.charts               # regenerate docs/campaign_roas.png
```

## Hard rules

- **Nothing is posted.** There's no Meta or ad-account integration. Don't add one without Sara's explicit approval.
- **Only `src/ads_agent/llm.py` talks to a model.** Tests use `FakeLLM` and never touch the network.
  - Keys come from `.env` (repo or `Portfolio Projects/.env`). Never print or log them.
- **Honest numbers.** Don't write a metric in the README or in `RESULTS.md` unless a run saved it in `evals/results/`. Report it with the denominator, model ID and date. `evals/dry_run/` is never a result.
- **The held-out policy set is now "seen".**
  - The rules were frozen before it was run (hashes are in `evals/results/policy_rules_summary.json`).
  - If you change `policy_rules.py`, `checker.py` or `data/brand.json`, the old held-out score no longer describes the new rules. Bump the version, write NEW held-out cases first, and report both.
- **Keep the checklist examples apart from the test cases.** `docs/policy_checklist.md` is sent to the LLM reviewer. Its examples must never copy sentences from `evals/data/policy_cases_test.jsonl`, or the LLM-layer score leaks.
- **Arabic and French.** Patterns are folded by `checker.fold()` (accents and diacritics removed, alef forms unified). Write them in lower case, and don't use `\B`, `\S`, `\W` or `\D`. Arabic patterns don't use `\b`.
- **Data.**
  - Synthetic only. Use the fictional shop name "Lumi Skin" and no real company names.
  - Fake people use `@example.com` emails and `+971 50 000 xxxx` phone numbers.

## Where things are

| Path | What it holds |
|---|---|
| `src/ads_agent/` | `llm` · `briefs` · `copywriter` · `policy_rules` · `checker` · `approval` · `graph` · `campaign` · `budget` · `analyst` · `charts` |
| `app/app.py` | Gradio app with the Write, Check and Analyse tabs |
| `evals/run.py` | All evaluations |
| `evals/data/` | Labelled policy cases (dev and test) |
| `data/` | Synthetic data and its generators |
| `docs/` | Architecture and policy checklist |

## Adding a rule

1. Add the pattern to `policy_rules.py` for all three languages.
2. Add a parametrised test in `tests/test_checker.py`.
3. Run the policy evaluation and record that it is a new rules version.
