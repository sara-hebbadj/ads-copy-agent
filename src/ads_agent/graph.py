"""The copy workflow as a LangGraph graph with a human approval pause.

    START -> draft -> check -> human_review (interrupt) -> record -> END

- draft:        the LLM writes variants (copywriter.py)
- check:        code rules check each variant (checker.py), plus the optional LLM review
- human_review: the graph PAUSES with `interrupt(...)` and waits for a person's decisions
- record:       decisions are applied with guardrails and logged (approval.py)

Run from the command line (offline fake model unless --live):
    python -m ads_agent.graph --brief b08-vitamin-c-brightening-serum
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from ads_agent.approval import LOG_FILE, apply_decision, write_log
from ads_agent.briefs import load_brief
from ads_agent.checker import check_ad
from ads_agent.copywriter import draft_variants


class AdState(TypedDict, total=False):
    brief: dict
    variants: list[dict]  # each variant also carries its "check" result
    decisions: list[dict]  # from the human: {"variant_id", "action", "edited"}
    records: list[dict]  # what was logged


def build_graph(llm, review_llm=None, log_file: Path = LOG_FILE, reviewer: str = "reviewer"):
    """Build and compile the graph. `review_llm` turns on the optional LLM policy review."""

    def draft(state: AdState) -> dict:
        return {"variants": draft_variants(state["brief"], llm)}

    def check(state: AdState) -> dict:
        checked = []
        for variant in state["variants"]:
            result = check_ad(variant, brief=state["brief"], llm=review_llm)
            checked.append(
                {**variant, "check": result.to_dict(), "check_summary": result.summary()}
            )
        return {"variants": checked}

    def human_review(state: AdState) -> dict:
        # The graph stops here. The caller shows the variants to a person and resumes
        # with Command(resume=[...decisions...]).
        decisions = interrupt({"brief_id": state["brief"]["id"], "variants": state["variants"]})
        return {"decisions": decisions}

    def record(state: AdState) -> dict:
        by_id = {v["id"]: v for v in state["variants"]}
        records = [
            apply_decision(by_id[d["variant_id"]], d, state["brief"], reviewer)
            for d in state["decisions"]
            if d["variant_id"] in by_id
        ]
        write_log(records, log_file)
        return {"records": records}

    graph = StateGraph(AdState)
    graph.add_node("draft", draft)
    graph.add_node("check", check)
    graph.add_node("human_review", human_review)
    graph.add_node("record", record)
    graph.add_edge(START, "draft")
    graph.add_edge("draft", "check")
    graph.add_edge("check", "human_review")
    graph.add_edge("human_review", "record")
    graph.add_edge("record", END)
    # The checkpointer saves the paused state so the run can resume after the human answers.
    return graph.compile(checkpointer=InMemorySaver())


def start_run(graph, brief: dict) -> tuple[dict, list[dict]]:
    """Run until the human_review pause. Returns (config, variants waiting for review)."""
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    state = graph.invoke({"brief": brief}, config)
    paused = state["__interrupt__"][0].value
    return config, paused["variants"]


def finish_run(graph, config: dict, decisions: list[dict]) -> list[dict]:
    """Resume after the human has decided. Returns the logged records."""
    state = graph.invoke(Command(resume=decisions), config)
    return state["records"]


def main() -> None:
    from ads_agent.llm import FakeLLM, LLMClient

    parser = argparse.ArgumentParser(description="Draft, check and approve ads in the terminal.")
    parser.add_argument("--brief", default="b08-vitamin-c-brightening-serum")
    parser.add_argument("--live", action="store_true", help="use OpenRouter (needs a key)")
    args = parser.parse_args()

    llm = LLMClient("main") if args.live else FakeLLM()
    if not args.live:
        print("OFFLINE: using FakeLLM canned drafts (not model output).")
    graph = build_graph(llm, reviewer="terminal-user")
    config, variants = start_run(graph, load_brief(args.brief))

    decisions = []
    for v in variants:
        print(f"\n[{v['id']}] {v['primary_text']}\n  Headline: {v['headline']} | CTA: {v['cta']}")
        print(f"  Check: {v['check_summary']}")
        action = input("  approve / edit / reject? ").strip().lower() or "reject"
        decision = {"variant_id": v["id"], "action": action}
        if action == "edit":
            decision["edited"] = {"primary_text": input("  New primary text: ").strip()}
        decisions.append(decision)

    for record in finish_run(graph, config, decisions):
        print(json.dumps({k: record[k] for k in ("variant_id", "status", "note")}))
    print(f"Logged to {LOG_FILE}. Nothing was posted.")


if __name__ == "__main__":
    main()
