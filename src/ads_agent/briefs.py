"""Load product briefs from data/briefs/*.json (made by data/make_briefs.py)."""

from __future__ import annotations

import json
from pathlib import Path

from ads_agent import DATA_DIR
from ads_agent.policy_rules import PLACEMENT_LIMITS

BRIEFS_DIR = DATA_DIR / "briefs"
REQUIRED_FIELDS = ["id", "product", "key_ingredients", "audience", "key_message", "tone",
                   "placement", "languages"]


def validate_brief(brief: dict) -> dict:
    missing = [name for name in REQUIRED_FIELDS if name not in brief]
    if missing:
        raise ValueError(f"Brief {brief.get('id', '?')} is missing: {missing}")
    if brief["placement"] not in PLACEMENT_LIMITS:
        raise ValueError(f"Unknown placement {brief['placement']!r}")
    return brief


def load_brief(path_or_id: str | Path) -> dict:
    """Load a brief by file path or by its id (e.g. 'b08-vitamin-c-brightening-serum')."""
    path = Path(path_or_id)
    if not path.exists():
        path = BRIEFS_DIR / f"{path_or_id}.json"
    return validate_brief(json.loads(path.read_text(encoding="utf-8")))


def list_briefs() -> list[dict]:
    return [load_brief(path) for path in sorted(BRIEFS_DIR.glob("*.json"))]
