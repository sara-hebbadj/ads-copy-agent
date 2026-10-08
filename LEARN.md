# LEARN: ads-copy-agent

Use this to prepare for interviews. Do the walkthrough out loud, answer the 10 questions without looking, then do the 3 "change it live" exercises.

## 10-minute walkthrough script

**0:00–1:00 · The problem.**

"Small marketing teams in the UAE write the same ad in Arabic, English and French. Every ad has to follow the platform's advertising standards and the brand's rules, and every week someone has to decide where the budget goes. An LLM is fast at writing, but it can invent medical claims and numbers. So this project splits the work three ways: the LLM writes and explains, code checks and computes, and a human approves. Nothing is posted; there's no Meta connection at all."

**1:00–3:00 · The copy workflow.**

1. Open `data/briefs/b10-retinol-0-3-night-serum.json`. Show the placement, the tone, and the required line "Patch test first.".
2. Open `src/ads_agent/copywriter.py`. `build_prompt` puts the brief, the brand voice, the character limits, the banned words and the required lines into the prompt.
3. Open `src/ads_agent/graph.py`. Show the four nodes: draft → check → human_review → record.
4. Point at `interrupt(...)`. "The graph pauses here. The checkpointer keeps the state, and the UI resumes it with `Command(resume=decisions)`."

**3:00–5:00 · The checker.**

1. Open `src/ads_agent/policy_rules.py`. Show one category in three languages, for example the personal-attribute patterns.
2. Open `checker.py`. Show `fold()`, which removes accents and Arabic diacritics and unifies the alef forms.
3. Explain why Arabic patterns have no `\b`: prefixes such as و and ب attach to the next word.
4. Show the masking of the product name in `check_ad`.
5. In the app's **Check** tab, paste "Are you struggling with acne? Our serum cures it fast." to show the FAIL reasons. Then paste the same idea in compliant cosmetic wording.

**5:00–6:30 · Approval guardrails.**

In the **Write** tab, draft the retinol brief. The offline fake drafts are missing "Patch test first.", so they fail. Then:

1. Set one variant to `approve`. It comes back **blocked**.
2. Edit another one to add the line. It comes back **approved_after_edit**.
3. Show `logs/approval_log.jsonl` with `posted: false`.

**6:30–8:30 · Campaign analyst.**

1. Open the **Analyse** tab and walk through the chart.
2. `campaign.py` computes CTR, CPC, CVR, CPA and ROAS in code.
3. `budget.py` holds the rules in order: HOLD (small sample) → PAUSE → CUT → KEEP (fatigue) → SCALE → KEEP.
4. Explain one row, for example "nightcream-fr-retarget has a good ROAS, but its click rate fell 36% week on week, so refresh the creative before adding budget".
5. Show `verify_numbers`: every number in the summary must be one of the computed facts.

**8:30–10:00 · Evaluation and honesty.**

1. Open `evals/results/policy_rules_summary.json`. On 48 held-out cases the code rules reach precision 0.94 and recall 0.67.
2. "I wrote the development cases with the rules, then wrote the held-out cases, ran them once and didn't touch the rules again. The file hashes prove which rules made the number."
3. Name the misses:
   - sensational hooks;
   - "10 years younger in two weeks";
   - a feminine French word form;
   - one false positive.
   "That's why there's an LLM layer and a human."
4. Open `evals/results/policy_llm_openai_2026-10-08_summary.json` (first live run, 8 October 2026). Adding the LLM reviewer (`openai/gpt-6-luna`) on the same 48 cases raised recall from 0.67 (16/24) to 1.00 (24/24) and lowered precision from 0.94 (16/17) to 0.89 (24/27). "The first smoke run failed every ad for 'no call-to-action button', because the reviewer was asked to check a field it was never sent."
5. Open `evals/results/copy_judge_comparison.json`. "The judge first marked down the offer lines the brief requires, because it wasn't shown the offer. With the full brief, it found the real problem: on 72-character reels with an offer, the drafts drop the product message (brand fit 1.85 on 27 drafts). Judge scores aren't human scores."

## 10 interview questions with short model answers

1. **How do you keep AI ad copy on-brand and within policy?**
   In three layers:
   - The prompt carries the voice, the limits, the banned words and the required lines.
   - A deterministic checker verifies every variant and gives reasons, with an optional LLM review for meaning the patterns miss.
   - A human approves. A failing variant can't be approved, and an edit is checked again.

2. **Why does code compute the metrics while the LLM only explains them?**
   Arithmetic in code is exact, testable and repeatable. LLMs can miscalculate or invent numbers. The model only receives the computed FACTS, and `verify_numbers` checks its summary against them.

3. **Walk me through one budget suggestion and its assumption.**
   `cleanser-ar-fbfeed-lal` has ROAS 1.11. With an assumed 65% gross margin, break-even ROAS is 1 ÷ 0.65 = 1.54, so it loses money after product costs. The suggestion is to cut by 30%. If the real margin were higher, break-even would fall and the action could change.

4. **What changes in Arabic ad copy compared with English?**
   - You write it natively, not as a word-for-word translation. Modern Standard Arabic works well for the UAE.
   - The grammar has gender: feminine forms for a female audience.
   - It's written right to left, and the button labels are localised by Meta.
   - Technically, prefixes attach to words, so matching can't rely on word boundaries. Diacritics and alef forms vary, so I normalise them. Diacritics also count towards length.
   - Culturally, "whitening" or "fairness" language is banned by the brand.

5. **What do precision 0.94 and recall 0.67 mean here?**
   - Precision: when the rules flag an ad, they're right in 16 of 17 cases, so there are few false alarms for the team.
   - Recall: the rules caught 16 of the 24 violating ads. A third get through, so the rules alone aren't enough. The LLM review and the human step cover the gap.

6. **Why a separate held-out set, and why freeze the rules?**
   If you tune the rules on the same cases you score, the score only measures memorisation; that's why the development set scores 24/24. A held-out set run once gives an honest estimate. The SHA-256 of the rule files ties the result to the exact rules.

7. **How does human approval work in LangGraph?**
   The `human_review` node calls `interrupt(payload)`. The graph stops, and the checkpointer (`InMemorySaver`) saves the state under a thread ID. The UI shows the variants. When the human submits, we call `graph.invoke(Command(resume=decisions), config)`, and the `record` node applies the guardrails and writes the log.

8. **How do you stop the summary from inventing numbers?**
   The prompt says to use only the numbers in FACTS and to calculate nothing new. After the model answers, a regex extracts every number, and each one must equal a fact number after rounding. Two limits: it can't check that the number belongs to the right metric, and it can't check numbers written as words.

9. **How would you use an LLM as a judge fairly?**
   - Use a judge from a different model family than the writer; the runner enforces this.
   - Give it a clear 1–5 rubric and ask for JSON output.
   - Calibrate it against human ratings: the copy CSV doubles as my rating sheet, so I can compare the judge's scores with mine.
   - Report the averages together with examples.

10. **What would you need before using this with a real ad account?**
    - The current, full advertising standards and legal review for skincare claims.
    - A larger test set from real reviewers.
    - Proper authentication and an approval workflow with roles.
    - Monitoring and cost limits.
    - Proper attribution for ROAS.
    - Uploads should still go through a person or a reviewed integration.

## 3 "change it live" exercises

1. **Change the target ROAS.**
   - In `src/ads_agent/budget.py`, set `TARGET_ROAS = 3.5`.
   - Run `uv run pytest -q`. `test_suggestions_on_the_synthetic_campaign` fails because `vitc-en-igfeed` (ROAS 3.12) is no longer a SCALE.
   - Explain why the test protects behaviour, update the expectation to `KEEP`, and check the Analyse tab.

2. **Add an Arabic condition word.**
   - Add `"الهالات السوداء"` (dark circles) to `CONDITIONS["ar"]` in `policy_rules.py`.
   - Add a test case to `tests/test_checker.py`: `("ar", "هل تعانين من الهالات السوداء؟", "personal_attribute")`.
   - Run the tests.
   - Say clearly that this changes the rules after the held-out run, so it's a new version that needs new held-out cases.

3. **Add a new budget rule.**
   - In `decide()`, before SCALE, add: if the last-7-day CPA is more than 50% above the previous 7 days, KEEP with a reason.
   - You'll need `trend["cpa_aed_change_pct"]`, which is already computed in `campaign.trend_table`.
   - Add a parametrised test row in `tests/test_campaign_budget.py` and run the tests.
