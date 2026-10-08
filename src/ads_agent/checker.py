"""Brand and ad-policy checker.

Layer 1 (always on, no LLM): code rules from policy_rules.py and data/brand.json.
Layer 2 (optional): an LLM reads docs/policy_checklist.md and reviews the ad.

A FAIL issue blocks approval. A WARN issue is allowed but a person should look at it.
This is a simplified demo of the kind of checks a marketing team runs before submitting
ads; it is not Meta's review system.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from functools import lru_cache

from ads_agent import DATA_DIR, DOCS_DIR
from ads_agent import policy_rules as rules
from ads_agent.llm import parse_json_answer

TEXT_FIELDS = ("primary_text", "headline")
LANGUAGES = ("en", "ar", "fr")


@dataclass
class Issue:
    rule: str  # e.g. "medical_claim", "length", "banned_word"
    severity: str  # "fail" or "warn"
    field: str  # which part of the ad, e.g. "primary_text"
    message: str  # reason shown to the reviewer


@dataclass
class CheckResult:
    passed: bool
    issues: list[Issue] = field(default_factory=list)

    @property
    def failed_rules(self) -> list[str]:
        return sorted({i.rule for i in self.issues if i.severity == "fail"})

    def summary(self) -> str:
        """One line for tables: 'PASS' or 'FAIL: reason; reason' (+ warnings)."""
        fails = [f"{i.rule} ({i.field}): {i.message}" for i in self.issues if i.severity == "fail"]
        warns = [f"{i.rule}: {i.message}" for i in self.issues if i.severity == "warn"]
        text = "PASS" if self.passed else "FAIL: " + "; ".join(fails)
        if warns:
            text += " | WARN: " + "; ".join(warns)
        return text

    def to_dict(self) -> dict:
        return {"passed": self.passed, "issues": [asdict(i) for i in self.issues]}


# --- Text normalisation -------------------------------------------------------------------


def fold(text: str) -> str:
    """Remove accents and Arabic diacritics so spelling variants match.

    NFD splits "é" into "e" + accent and "أ" into "ا" + hamza; we then drop the marks.
    Also: remove tatweel (ـ), turn ى into ي, and unify odd spaces and apostrophes.
    Case is not changed here (regex patterns must keep \\b, \\s and so on).
    """
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    replacements = {"ـ": "", "ى": "ي", " ": " ", " ": " ", "’": "'", "‘": "'"}
    for old, new in replacements.items():
        without_marks = without_marks.replace(old, new)
    return without_marks


def normalize(text: str) -> str:
    """fold() + lower case + single spaces. Used on ad text before matching."""
    return re.sub(r"\s+", " ", fold(text).lower()).strip()


@lru_cache(maxsize=None)
def compile_rule(pattern: str, language: str) -> re.Pattern:
    """Fold a pattern and fill in {c} with that language's list of conditions."""
    conditions = sorted(rules.CONDITIONS[language], key=len, reverse=True)
    condition_group = "|".join(re.escape(fold(c)) for c in conditions)
    return re.compile(fold(pattern).replace("{c}", condition_group))


@lru_cache(maxsize=1)
def load_brand() -> dict:
    return json.loads((DATA_DIR / "brand.json").read_text(encoding="utf-8"))


# --- Individual rules -----------------------------------------------------------------------


def check_lengths(ad: dict, placement: str) -> list[Issue]:
    limits = rules.PLACEMENT_LIMITS[placement]
    issues = []
    for name, limit in limits.items():
        length = len(ad.get(name, "").strip())  # Python counts characters (code points)
        if length > limit:
            issues.append(
                Issue("length", "fail", name, f"{length} characters > {limit} for {placement}")
            )
    return issues


def banned_words_for(language: str, brief: dict | None) -> list[str]:
    words = list(load_brand()["banned_words"].get(language, []))
    if brief:
        words += brief.get("banned_words", {}).get(language, [])
    return words


def find_banned_words(text: str, words: list[str], language: str) -> list[str]:
    found = []
    for word in words:
        target = normalize(word)
        if language == "ar":
            hit = target in text  # Arabic glues prefixes to words, so match inside words
        else:
            hit = re.search(rf"(?<!\w){re.escape(target)}(?!\w)", text) is not None
        if hit:
            found.append(word)
    return found


def check_patterns(field_texts: dict[str, str], language: str) -> list[Issue]:
    """Medical claims, unrealistic claims, before/after, personal attributes, evidence."""
    issues = []
    for field_name, text in field_texts.items():
        for rule, pattern, reason in rules.CLAIM_PATTERNS[language]:
            if compile_rule(pattern, language).search(text):
                issues.append(Issue(rule, "fail", field_name, reason))
        for pattern in rules.PERSONAL_ATTRIBUTE_PATTERNS[language]:
            if compile_rule(pattern, language).search(text):
                reason = "Says or implies the reader has a skin or health condition"
                issues.append(Issue("personal_attribute", "fail", field_name, reason))
        if compile_rule(rules.NEEDS_EVIDENCE_PATTERNS[language], language).search(text):
            reason = "Superlative or clinical claim: keep evidence on file"
            issues.append(Issue("needs_evidence", "warn", field_name, reason))
    return issues


def check_disclaimers(full_text: str, language: str, brief: dict | None) -> list[Issue]:
    issues = []
    has_offer = compile_rule(rules.OFFER_PATTERNS[language], language).search(full_text)
    has_terms = compile_rule(rules.DISCLAIMER_PATTERNS[language], language).search(full_text)
    if has_offer and not has_terms:
        example = rules.DISCLAIMER_EXAMPLES[language]
        reason = f"Offer without terms line (add e.g. '{example}')"
        issues.append(Issue("missing_disclaimer", "fail", "primary_text", reason))
    required = (brief or {}).get("required_disclaimers", {}).get(language)
    if required and normalize(required).rstrip(".!") not in full_text:
        reason = f"Product disclaimer missing: '{required}'"
        issues.append(Issue("missing_disclaimer", "fail", "primary_text", reason))
    return issues


def check_style(ad: dict) -> list[Issue]:
    text = " ".join(ad.get(name, "") for name in TEXT_FIELDS)
    issues = []
    if text.count("!") > rules.MAX_EXCLAMATION_MARKS:
        issues.append(Issue("style", "warn", "all", "More than one exclamation mark"))
    pattern = rf"\b[A-Z]{{{rules.MIN_SHOUTING_WORD_LENGTH},}}\b"
    if re.search(pattern, text):
        issues.append(Issue("style", "warn", "all", "Word in capitals (shouting)"))
    return issues


def check_cta(ad: dict) -> list[Issue]:
    cta = ad.get("cta")
    if cta and cta not in rules.ALLOWED_CTAS:
        return [Issue("cta", "fail", "cta", f"Unknown call-to-action button '{cta}'")]
    return []


# --- Main entry point ----------------------------------------------------------------------


def check_ad(
    ad: dict, placement: str | None = None, brief: dict | None = None, llm=None
) -> CheckResult:
    """Check one ad.

    ad: {"language": "en"|"ar"|"fr", "primary_text": ..., "headline": ..., "cta": optional}
    placement: key of PLACEMENT_LIMITS (default: the brief's placement, else facebook_feed)
    brief: optional product brief (adds product banned words and required disclaimers)
    llm: optional client; if given, the LLM review (layer 2) also runs
    """
    language = ad["language"]
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    placement = placement or (brief or {}).get("placement") or "facebook_feed"

    # Normalised text per field. The product name is blanked out so that a name such as
    # "Salicylic Acne Cleanser" is not read as a claim about acne.
    product = normalize((brief or {}).get("product", ""))
    field_texts = {}
    for name in TEXT_FIELDS:
        text = normalize(ad.get(name, ""))
        field_texts[name] = text.replace(product, " ") if product else text
    full_text = " \n ".join(field_texts.values())

    issues = check_lengths(ad, placement)
    for field_name, text in field_texts.items():
        for word in find_banned_words(text, banned_words_for(language, brief), language):
            issues.append(Issue("banned_word", "fail", field_name, f"Brand-banned word '{word}'"))
    issues += check_patterns(field_texts, language)
    issues += check_disclaimers(full_text, language, brief)
    issues += check_cta(ad)
    issues += check_style(ad)
    if llm is not None:
        issues += llm_review(ad, llm)

    passed = not any(issue.severity == "fail" for issue in issues)
    return CheckResult(passed=passed, issues=issues)


# --- Layer 2: LLM review against the written checklist ----------------------------------------


def load_checklist() -> str:
    return (DOCS_DIR / "policy_checklist.md").read_text(encoding="utf-8")


def llm_review(ad: dict, llm) -> list[Issue]:
    """Ask a model to review the ad against docs/policy_checklist.md."""
    system = (
        "You review draft social media ads for a skincare shop before a human approves them.\n"
        "Apply this checklist strictly. Reply with JSON only: "
        '{"verdict": "pass" or "fail", "reasons": ["short reason", ...]}\n\n' + load_checklist()
    )
    user = json.dumps(
        {k: ad.get(k, "") for k in ("language", "primary_text", "headline")}, ensure_ascii=False
    )
    try:
        answer = parse_json_answer(llm.complete(system, user, task="policy_review", temperature=0))
        verdict = str(answer.get("verdict", "")).lower()
        reasons = "; ".join(answer.get("reasons", [])) or "no reason given"
    except (ValueError, json.JSONDecodeError):
        return [Issue("llm_review", "warn", "all", "LLM answer unreadable: a person must check")]
    if verdict == "fail":
        return [Issue("llm_review", "fail", "all", reasons)]
    return []
