"""Copy generator: asks the LLM for ad variants in English, Arabic and French.

The prompt carries the brief, the brand voice, the length limits for the placement, the
banned words and the required disclaimers. The model's answer is still checked by
checker.py afterwards: the prompt asks for good behaviour, the checker verifies it.
"""

from __future__ import annotations

import json

from ads_agent.checker import banned_words_for, load_brand
from ads_agent.llm import parse_json_answer
from ads_agent.policy_rules import ALLOWED_CTAS, DISCLAIMER_EXAMPLES, PLACEMENT_LIMITS

VARIANTS_PER_LANGUAGE = 3
LANGUAGE_NAMES = {"en": "English", "ar": "Arabic", "fr": "French"}

SYSTEM_TEMPLATE = """You write Facebook and Instagram ad copy for {brand},
a skincare shop in the UAE.
Brand voice: {voice}

Never:
- claim the product treats, cures, heals or removes a skin or health condition;
- say or imply that the reader has a condition or a flaw ("Are you struggling with acne?",
  "your wrinkles");
- promise guaranteed, permanent, overnight or "before and after" results;
- use more than one exclamation mark, or words in capitals.
Cosmetic wording is fine: "helps skin feel hydrated", "for a fresh-looking glow",
"made for oily skin".

Reply with JSON only, in this shape:
{{"variants": [{{"language": "en", "primary_text": "...", "headline": "...",
  "cta": "SHOP_NOW"}}]}}"""


def build_prompt(brief: dict, per_language: int = VARIANTS_PER_LANGUAGE) -> tuple[str, str]:
    """Return (system prompt, user prompt) for one brief."""
    brand = load_brand()
    system = SYSTEM_TEMPLATE.format(brand=brand["brand"], voice=brand["voice"])
    limits = PLACEMENT_LIMITS[brief["placement"]]

    lines = [
        f"Product: {brief['product']}",
        f"Key ingredients: {', '.join(brief['key_ingredients'])}",
        f"Price: AED {brief.get('price_aed', 'n/a')}",
        f"Audience: {brief['audience']}",
        f"Key message: {brief['key_message']}",
        f"Tone: {brief['tone']}",
        f"Placement: {brief['placement']} (primary text at most {limits['primary_text']} "
        f"characters, headline at most {limits['headline']} characters, spaces included)",
        f"Call-to-action button: one of {', '.join(ALLOWED_CTAS)}",
    ]
    if brief.get("offer"):
        lines.append(f"Offer: {brief['offer']}. Mention it and add the terms line.")
    lines.append("")
    for language in brief["languages"]:
        name = LANGUAGE_NAMES[language]
        lines.append(f"{name} ({language}): {load_brand()['languages'][language]}")
        banned = banned_words_for(language, brief)
        lines.append(f"  Never use these words: {', '.join(banned)}")
        required = brief.get("required_disclaimers", {}).get(language)
        if required:
            lines.append(f"  The primary text must include this sentence exactly: {required}")
        if brief.get("offer"):
            lines.append(f"  Terms line: {DISCLAIMER_EXAMPLES[language]}")
    lines.append("")
    lines.append(
        f"Write {per_language} different variants for each language "
        f"({', '.join(brief['languages'])}). Write each language natively, not as a "
        "word-for-word translation."
    )
    return system, "\n".join(lines)


def clean_variants(raw_variants: list[dict], brief: dict) -> list[dict]:
    """Keep well-formed variants for the brief's languages and give each an id like 'en-1'."""
    variants, counts = [], {}
    for raw in raw_variants:
        language = str(raw.get("language", "")).lower()
        if language not in brief["languages"]:
            continue
        counts[language] = counts.get(language, 0) + 1
        variants.append(
            {
                "id": f"{language}-{counts[language]}",
                "brief_id": brief["id"],
                "language": language,
                "placement": brief["placement"],
                "primary_text": str(raw.get("primary_text", "")).strip(),
                "headline": str(raw.get("headline", "")).strip(),
                "cta": str(raw.get("cta", "SHOP_NOW")).strip().upper(),
            }
        )
    return variants


def draft_variants(brief: dict, llm, per_language: int = VARIANTS_PER_LANGUAGE) -> list[dict]:
    """Ask the model for variants and return them as a list of dicts."""
    system, user = build_prompt(brief, per_language)
    answer = llm.complete(system, user, task="draft", temperature=0.8)
    try:
        data = parse_json_answer(answer)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"Model answer for {brief['id']} was not valid JSON") from exc
    return clean_variants(data.get("variants", []), brief)
