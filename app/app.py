"""Gradio demo with three tabs: Write, Check, Analyse.

Run:  python app/app.py     then open http://127.0.0.1:7860

Without OPENROUTER_API_KEY (and MODEL_MAIN / MODEL_CHEAP) the app runs in demo mode: drafts are
canned placeholders from FakeLLM and the campaign summary is a fixed template. Nothing is ever
posted. On a Hugging Face Space, add the key as a secret and the model IDs as variables.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # works without install

import gradio as gr  # noqa: E402
import pandas as pd  # noqa: E402

from ads_agent.analyst import (  # noqa: E402
    analyse,
    build_facts,
    summarize,
    template_summary,
    verify_numbers,
)
from ads_agent.briefs import list_briefs, load_brief  # noqa: E402
from ads_agent.budget import ASSUMPTIONS  # noqa: E402
from ads_agent.campaign import load_campaign  # noqa: E402
from ads_agent.charts import roas_chart  # noqa: E402
from ads_agent.checker import check_ad  # noqa: E402
from ads_agent.graph import build_graph, finish_run, start_run  # noqa: E402
from ads_agent.llm import FakeLLM, LLMClient, has_api_key  # noqa: E402
from ads_agent.policy_rules import PLACEMENT_LIMITS  # noqa: E402

# Live only when the key and both model IDs are set, so a half-configured Space still starts.
LIVE = has_api_key() and bool(os.getenv("MODEL_MAIN") and os.getenv("MODEL_CHEAP"))
MODE_NOTE = (
    "**Live mode:** drafts come from the model set in `MODEL_MAIN` (OpenRouter)."
    if LIVE
    else "**Demo mode — live AI is off; add OPENROUTER_API_KEY in Space settings to enable** "
    "(plus `MODEL_MAIN` and `MODEL_CHEAP` variables). Drafts in the Write tab are canned "
    "placeholders from `FakeLLM`, not model output. The **Check** and **Analyse** tabs, the "
    "approval log and the number check are real code and work fully."
)
BRIEF_IDS = [b["id"] for b in list_briefs()]
GRAPH = build_graph(LLMClient("main") if LIVE else FakeLLM(), reviewer="gradio-demo")


# --- Write tab ----------------------------------------------------------------------------


def brief_markdown(brief: dict) -> str:
    offer = brief.get("offer") or "none"
    required = "; ".join(brief.get("required_disclaimers", {}).values()) or "none"
    return (
        f"**{brief['product']}** (AED {brief['price_aed']}) · placement `{brief['placement']}` · "
        f"tone: {brief['tone']}  \nAudience: {brief['audience']}  \n"
        f"Key message: {brief['key_message']}  \nOffer: {offer}  \nRequired lines: {required}"
    )


def draft(brief_id: str):
    brief = load_brief(brief_id)
    config, variants = start_run(GRAPH, brief)
    rows = [
        {
            "id": v["id"],
            "primary_text": v["primary_text"],
            "headline": v["headline"],
            "cta": v["cta"],
            "check": v["check_summary"],
            "action": "approve" if v["check"]["passed"] else "reject",
            "edited_primary_text": "",
            "edited_headline": "",
        }
        for v in variants
    ]
    return config, pd.DataFrame(rows), brief_markdown(brief), None


def submit(config: dict | None, table: pd.DataFrame):
    if not config:
        return None, None, "Draft a brief first (each draft can be reviewed once)."
    decisions = []
    for row in table.to_dict("records"):
        decision = {"variant_id": row["id"], "action": str(row["action"]).strip().lower()}
        if decision["action"] == "edit":
            decision["edited"] = {
                "primary_text": row["edited_primary_text"],
                "headline": row["edited_headline"],
            }
        decisions.append(decision)
    try:
        records = finish_run(GRAPH, config, decisions)
    except ValueError as exc:
        return config, None, f"Fix the action column: {exc}"
    columns = ["variant_id", "action", "status", "primary_text", "headline", "note", "posted"]
    return None, pd.DataFrame(records)[columns], "Decisions logged to logs/approval_log.jsonl."


# --- Check tab ---------------------------------------------------------------------------------


def check_text(language: str, placement: str, primary_text: str, headline: str, brief_id: str):
    brief = load_brief(brief_id) if brief_id != "(no brief)" else None
    ad = {"language": language, "primary_text": primary_text, "headline": headline}
    result = check_ad(ad, placement, brief)
    verdict = "### PASS" if result.passed else "### FAIL"
    lengths = f"Primary text {len(primary_text.strip())} chars, headline {len(headline.strip())}."
    issues = pd.DataFrame([vars(i) for i in result.issues] or [{"rule": "none"}])
    return f"{verdict}\n{lengths}", issues


# --- Analyse tab -------------------------------------------------------------------------------


def run_analysis(use_llm: bool):
    frame = load_campaign()
    analysis = analyse(frame)
    facts = build_facts(analysis)
    if use_llm and LIVE:
        text, source = summarize(facts, LLMClient("cheap")), "LLM (MODEL_CHEAP)"
    else:
        text, source = template_summary(analysis), "template (no LLM)"
    check = verify_numbers(text, facts)
    status = "all numbers match the table" if check["ok"] else f"MISMATCH: {check['mismatches']}"
    summary_md = (
        f"**Summary source:** {source}  \n**Number check:** {check['numbers_matched']}/"
        f"{check['numbers_checked']} numbers found in the computed facts ({status})\n\n"
        + text.replace("\n", "  \n")
    )
    actions = analysis["suggestions"].set_index("ad_set_id")["action"].to_dict()
    metric_cols = ["ad_set_id", "spend_aed", "purchases", "revenue_aed", "ctr_pct", "cpc_aed",
                   "cvr_pct", "cpa_aed", "roas"]
    return (
        analysis["metrics"][metric_cols],
        analysis["trends"],
        analysis["suggestions"],
        roas_chart(frame, actions),
        summary_md,
    )


# --- Layout ------------------------------------------------------------------------------------

with gr.Blocks(title="Ads copy agent (demo)") as demo:
    gr.Markdown(
        "# Ads copy agent: write, check, analyse\n"
        "Fictional shop *Lumi Skin*, synthetic data. **Nothing is posted:** there is no "
        "connection to Meta or any ad account. Policy rules are a simplified demo.\n\n"
        + MODE_NOTE
    )

    with gr.Tab("Write"):
        run_state = gr.State(None)
        with gr.Row():
            brief_box = gr.Dropdown(BRIEF_IDS, value=BRIEF_IDS[7], label="Product brief")
            draft_btn = gr.Button("Draft and check", variant="primary")
        brief_info = gr.Markdown()
        gr.Markdown(
            "Set **action** to `approve`, `edit` (fill the edited columns) or `reject`. "
            "A variant that fails the checker cannot be approved as it is."
        )
        # Fixed widths: without them the empty "edited_*" columns shrink to ~30 px and their
        # wrapped headers make the header row about 400 px tall. Order matches draft()'s columns.
        review_table = gr.Dataframe(
            interactive=True,
            wrap=True,
            label="Variants to review",
            column_widths=["6%", "23%", "12%", "8%", "14%", "8%", "16%", "13%"],
        )
        submit_btn = gr.Button("Submit decisions")
        submit_msg = gr.Markdown()
        result_table = gr.Dataframe(label="Logged decisions", wrap=True)
        draft_btn.click(draft, brief_box, [run_state, review_table, brief_info, result_table])
        submit_btn.click(submit, [run_state, review_table], [run_state, result_table, submit_msg])

    with gr.Tab("Check"):
        with gr.Row():
            lang_box = gr.Dropdown(["en", "ar", "fr"], value="en", label="Language")
            place_box = gr.Dropdown(list(PLACEMENT_LIMITS), value="instagram_feed",
                                    label="Placement")
            check_brief = gr.Dropdown(["(no brief)", *BRIEF_IDS], value="(no brief)",
                                      label="Brief (adds product rules)")
        primary_box = gr.Textbox(label="Primary text", lines=3,
                                 value="Are you struggling with acne? Our serum cures it fast.")
        headline_box = gr.Textbox(label="Headline", value="Results guaranteed")
        check_btn = gr.Button("Check", variant="primary")
        verdict_md = gr.Markdown()
        issues_table = gr.Dataframe(label="Issues", wrap=True)
        check_btn.click(check_text, [lang_box, place_box, primary_box, headline_box, check_brief],
                        [verdict_md, issues_table])

    with gr.Tab("Analyse"):
        use_llm_box = gr.Checkbox(value=LIVE, label="Explain with the LLM (needs API key)",
                                  interactive=LIVE)
        analyse_btn = gr.Button("Analyse campaign.csv", variant="primary")
        summary_md = gr.Markdown()
        chart = gr.Plot(label="ROAS per ad set")
        suggestions_table = gr.Dataframe(label="Budget suggestions (rule-based)", wrap=True)
        gr.Markdown(ASSUMPTIONS)
        metrics_table = gr.Dataframe(label="Metrics per ad set (computed by code)")
        trends_table = gr.Dataframe(label="Last 7 days vs previous 7 days")
        analyse_btn.click(run_analysis, use_llm_box,
                          [metrics_table, trends_table, suggestions_table, chart, summary_md])


if __name__ == "__main__":
    demo.launch()
