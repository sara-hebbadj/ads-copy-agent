"""Human approval step. A person approves, edits or rejects each variant.

Guardrails:
- A variant that FAILS the checker cannot be approved as it is. It must be edited
  (and the edit must pass the checker) or rejected.
- Every decision is written to a JSONL log with who decided and when.
- Nothing is ever posted: there is no connection to Meta or any ad account.
  "approved" only means "ready for a person to upload by hand".
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ads_agent import REPO_ROOT
from ads_agent.checker import check_ad

LOG_FILE = REPO_ROOT / "logs" / "approval_log.jsonl"
ACTIONS = ("approve", "edit", "reject")


def apply_decision(variant: dict, decision: dict, brief: dict, reviewer: str) -> dict:
    """Turn one reviewer decision into a log record with a final status."""
    action = decision.get("action", "").lower()
    if action not in ACTIONS:
        raise ValueError(f"Unknown action {action!r}; use one of {ACTIONS}")

    final = {k: variant[k] for k in ("primary_text", "headline", "cta")}
    check = variant["check"]
    note = ""
    if action == "reject":
        status = "rejected"
    elif action == "edit":
        final.update({k: v for k, v in decision.get("edited", {}).items() if v})
        result = check_ad({**variant, **final}, brief=brief)
        check = result.to_dict()
        status = "approved_after_edit" if result.passed else "blocked"
        note = "" if result.passed else "Edited text still fails: " + result.summary()
    else:  # approve
        status = "approved" if check["passed"] else "blocked"
        note = "" if check["passed"] else "Cannot approve a variant that fails the checker."

    return {
        "time": datetime.now(UTC).isoformat(),
        "reviewer": reviewer,
        "brief_id": brief["id"],
        "variant_id": variant["id"],
        "language": variant["language"],
        "action": action,
        "status": status,
        **final,
        "check_passed": check["passed"],
        "note": note,
        "posted": False,  # always False: this tool never posts ads
    }


def write_log(records: list[dict], log_file: Path = LOG_FILE) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
