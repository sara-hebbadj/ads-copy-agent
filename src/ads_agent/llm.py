"""The only place that talks to a language model.

- `LLMClient` calls OpenRouter through the OpenAI-compatible SDK.
- `FakeLLM` returns canned answers. Tests and `--dry-run` use it. Its output is
  NOT model output and must never be reported as a result.

Settings come from a `.env` file (repo/.env, or `Portfolio Projects/.env` two folders
above the repo) or from environment variables:
OPENROUTER_API_KEY, OPENROUTER_BASE_URL, MODEL_MAIN, MODEL_CHEAP, MODEL_JUDGE.
The key is never printed or logged.

Every call (real or fake) is appended to a JSONL trace file with the model, tokens,
cost, latency and outcome.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from ads_agent import EVALS_DIR, REPO_ROOT

ENV_FILES = [REPO_ROOT / ".env", REPO_ROOT.parent.parent / ".env"]
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
TRACE_FILE = EVALS_DIR / "traces.jsonl"
ROLE_TO_ENV = {"main": "MODEL_MAIN", "cheap": "MODEL_CHEAP", "judge": "MODEL_JUDGE"}


class MissingSettingError(RuntimeError):
    """Raised when the API key or a model ID is not configured."""


class BudgetExceededError(RuntimeError):
    """Raised when one run spends more than MAX_COST_PER_RUN_USD."""


def load_env() -> None:
    """Load .env files without overriding variables that are already set."""
    for path in ENV_FILES:
        if path.exists():
            load_dotenv(path, override=False)


def has_api_key() -> bool:
    load_env()
    return bool(os.getenv("OPENROUTER_API_KEY"))


def model_for_role(role: str) -> str:
    """Return the model ID for 'main', 'cheap' or 'judge' (from .env)."""
    load_env()
    env_name = ROLE_TO_ENV[role]
    model = os.getenv(env_name, "").strip()
    if not model:
        raise MissingSettingError(f"{env_name} is empty. Set it in Portfolio Projects/.env")
    return model


def write_trace(trace_file: Path | None, record: dict) -> None:
    if trace_file is None:
        return
    trace_file.parent.mkdir(parents=True, exist_ok=True)
    with trace_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


class LLMClient:
    """Small wrapper around the OpenAI SDK pointed at OpenRouter."""

    def __init__(self, role: str = "cheap", trace_file: Path | None = TRACE_FILE):
        load_env()
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise MissingSettingError(
                "OPENROUTER_API_KEY is not set. Live LLM runs are pending until a key exists."
            )
        from openai import OpenAI  # imported here so tests never need the network

        self.role = role
        self.model = model_for_role(role)
        self.trace_file = trace_file
        self.total_cost_usd = 0.0
        self.max_cost_usd = float(os.getenv("MAX_COST_PER_RUN_USD", "3"))
        self._client = OpenAI(
            api_key=api_key, base_url=os.getenv("OPENROUTER_BASE_URL") or DEFAULT_BASE_URL
        )

    def complete(self, system: str, user: str, task: str, temperature: float = 0.7) -> str:
        """Send one chat request and return the text answer."""
        started = time.perf_counter()
        record = {"time": datetime.now(UTC).isoformat(), "task": task, "model": self.model}
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=temperature,
                extra_body={"usage": {"include": True}},  # asks OpenRouter to return the cost
            )
            text = response.choices[0].message.content or ""
            usage = response.usage
            cost = float(getattr(usage, "cost", 0.0) or 0.0)
            record.update(
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                cost_usd=cost,
                outcome="ok",
            )
        except Exception as exc:  # record the failure, then let the caller decide
            record.update(outcome=f"error: {type(exc).__name__}")
            raise
        finally:
            record["latency_s"] = round(time.perf_counter() - started, 3)
            write_trace(self.trace_file, record)

        self.total_cost_usd += cost
        if self.total_cost_usd > self.max_cost_usd:
            raise BudgetExceededError(
                f"Run cost US${self.total_cost_usd:.2f} > limit US${self.max_cost_usd:.2f}"
            )
        return text


class FakeLLM:
    """Offline stand-in for LLMClient. Answers are canned and clearly labelled as fake.

    Pass `responses={"task_name": "text"}` to control the answer for a task (used in tests).
    """

    model = "fake/offline-canned"

    def __init__(self, responses: dict[str, str] | None = None, trace_file: Path | None = None):
        self.responses = responses or {}
        self.trace_file = trace_file
        self.calls: list[dict] = []
        self.total_cost_usd = 0.0

    def complete(self, system: str, user: str, task: str, temperature: float = 0.7) -> str:
        self.calls.append({"task": task, "system": system, "user": user})
        text = self.responses.get(task) or _canned_answer(task, user)
        write_trace(
            self.trace_file,
            {
                "time": datetime.now(UTC).isoformat(),
                "task": task,
                "model": self.model,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cost_usd": 0.0,
                "latency_s": 0.0,
                "outcome": "fake",
            },
        )
        return text


def _canned_answer(task: str, user: str) -> str:
    """Deterministic placeholder answers so the pipeline can run end to end offline."""
    if task == "draft":
        product = _find(r"Product: (.+)", user) or "Lumi Skin product"
        return json.dumps({"variants": _fake_variants(product)}, ensure_ascii=False)
    if task == "judge":
        return json.dumps({"brand_fit": 3, "language_quality": 3, "reason": "FAKE judge answer"})
    if task == "policy_review":
        return json.dumps({"verdict": "pass", "reasons": ["FAKE review: no model was called"]})
    if task == "summary":
        facts = [line for line in user.splitlines() if line.startswith("- ")]
        return "FAKE offline summary (no model was called). " + " ".join(facts[:2])
    return "FAKE answer"


def _find(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def _fake_variants(product: str) -> list[dict]:
    """Three short, rule-compliant placeholder variants per language."""
    templates = {
        "en": ("Meet {p}: a simple step for a fresh, comfortable routine.", "Your new daily step"),
        "ar": ("تعرّفي على {p}: خطوة بسيطة لروتين منعش ومريح.", "خطوتك اليومية الجديدة"),
        "fr": ("Découvrez {p} : un geste simple pour une routine fraîche.", "Votre nouveau geste"),
    }
    variants = []
    for language, (primary, headline) in templates.items():
        for number in range(1, 4):
            variants.append(
                {
                    "language": language,
                    "primary_text": primary.format(p=product),
                    "headline": f"{headline} {number}",
                    "cta": "SHOP_NOW",
                }
            )
    return variants


def parse_json_answer(text: str) -> dict:
    """Read a JSON object from a model answer (tolerates ```json fences and extra text)."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in the model answer")
    return json.loads(cleaned[start : end + 1])
