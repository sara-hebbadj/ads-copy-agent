"""Create 30 product briefs (data/briefs/*.json) from data/products.csv.

Run once:  python data/make_briefs.py
The output is committed, so you only re-run this if you change the templates.

Choice of products: the first 6 in-stock products of each of the 5 categories
(out-of-stock products are never advertised). Audience, tone, placement and offer
rotate so the briefs are varied but fully reproducible (no randomness).
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
PER_CATEGORY = 6

AUDIENCES = {
    "all": "Women and men aged 22-45 in the UAE who want a simple daily routine",
    "dry": "Adults aged 25-50 in the UAE who spend long days in air-conditioned offices",
    "oily": "Adults aged 18-35 in the UAE who want light textures in hot, humid weather",
    "combination": "Adults aged 22-40 in the UAE who want one product for the whole face",
    "sensitive": "Adults aged 22-50 in the UAE who prefer gentle, fragrance-light products",
}
KEY_MESSAGES = {
    "cleanser": "A gentle daily cleanse that leaves skin clean and comfortable, not tight.",
    "serum": "A few drops of {ingredient} for a routine step that feels light and easy.",
    "moisturiser": "Comfortable hydration with {ingredient} that suits the UAE climate.",
    "sunscreen": "Daily sun protection that is light enough to wear every day.",
    "mask": "A short self-care moment with {ingredient}.",
}
TONES = ["warm and calm", "fresh and upbeat", "expert but simple"]
PLACEMENTS = ["instagram_feed", "stories", "facebook_feed", "reels"]
OFFERS = [
    None,
    "15% off with code LUMI15 until 31 October 2026",
    None,
    "Free Honey Glow Mask sample with orders over AED 200",
    None,
]

# Products with strong actives need a patch-test line; sunscreens need a reapply line.
ACTIVE_WORDS = ("retinol", "salicylic", "glycolic", "azelaic", "lactic", "aha")
PATCH_TEST = {
    "en": "Patch test first.",
    "ar": "اختبريه على منطقة صغيرة أولاً.",
    "fr": "Faites un test cutané avant usage.",
}
REAPPLY = {
    "en": "Reapply every 2 hours.",
    "ar": "أعيدي وضعه كل ساعتين.",
    "fr": "Renouvelez toutes les 2 heures.",
}
SUNSCREEN_BANNED = {
    "en": ["sunblock", "waterproof", "all-day protection"],
    "ar": ["مقاوم للماء تماماً", "حماية طوال اليوم"],
    "fr": ["écran total", "waterproof", "protection toute la journée"],
}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def required_disclaimers(product: dict) -> dict:
    ingredients = product["key_ingredients"].lower()
    if product["category"] == "sunscreen":
        return REAPPLY
    if any(word in ingredients for word in ACTIVE_WORDS):
        return PATCH_TEST
    return {}


def make_brief(number: int, product: dict) -> dict:
    ingredients = [i.strip() for i in product["key_ingredients"].split(";")]
    return {
        "id": f"b{number:02d}-{slug(product['name'])}",
        "product_id": product["id"],
        "product": product["name"],
        "category": product["category"],
        "skin_type": product["skin_type"],
        "key_ingredients": ingredients,
        "price_aed": int(product["price_aed"]),
        "audience": AUDIENCES[product["skin_type"]],
        "key_message": KEY_MESSAGES[product["category"]].format(ingredient=ingredients[0]),
        "offer": OFFERS[number % len(OFFERS)],
        "tone": TONES[number % len(TONES)],
        "placement": PLACEMENTS[number % len(PLACEMENTS)],
        "languages": ["en", "ar", "fr"],
        "banned_words": SUNSCREEN_BANNED if product["category"] == "sunscreen" else {},
        "required_disclaimers": required_disclaimers(product),
    }


def main() -> None:
    with (HERE / "products.csv").open(encoding="utf-8") as f:
        products = [p for p in csv.DictReader(f) if int(p["stock"]) > 0]

    chosen = []
    for category in ["cleanser", "serum", "moisturiser", "sunscreen", "mask"]:
        chosen += [p for p in products if p["category"] == category][:PER_CATEGORY]

    out_dir = HERE / "briefs"
    out_dir.mkdir(exist_ok=True)
    for old in out_dir.glob("*.json"):
        old.unlink()
    for number, product in enumerate(chosen, start=1):
        brief = make_brief(number, product)
        path = out_dir / f"{brief['id']}.json"
        path.write_text(json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(chosen)} briefs to {out_dir}")


if __name__ == "__main__":
    main()
