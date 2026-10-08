# Ad policy and brand checklist (simplified demo)

This checklist is what the optional LLM reviewer reads, and what the labels in `evals/data/` follow. Its examples are deliberately different from the held-out test cases, so the LLM reviewer never sees test sentences.

It's a **simplified demo** for the fictional shop Lumi Skin. The policy items are paraphrased, in general terms, from the themes in [Meta's public Advertising Standards](https://transparency.meta.com/policies/ad-standards/). They don't quote Meta's rules, they don't cover all of them, and they're not legal advice. Meta's own review decides what runs. Before using any of this for real ads, read the current Advertising Standards and Ads Guide.

An ad **fails** if it breaks any item from 1 to 8. Items marked "warn" are allowed, but a person should check them.

**Note for the LLM reviewer:** you only see the language, the primary text and the headline. Length (item 7) and the call-to-action button (item 8) are checked exactly by code. Don't fail an ad because the placement or the button isn't shown. Judge the wording against items 1 to 6.

## 1. Personal attributes

Don't say or imply that the reader has a health or skin condition, a body feature, an age, or a negative feeling about how they look.

- Fails: "Do you have eczema?", "Hate your dark circles?", "Not happy with how you look in photos?", «Vous avez des rougeurs ?», «هل تعانين من الكلف؟».
- Fine: saying who the product is made for, such as "formulated for sensitive skin" or «للبشرة الدهنية».

## 2. Medical or health claims

Cosmetics must not claim to treat, cure, heal or remove a condition such as acne, eczema, melasma or scars.

- Fails: "heals eczema", "gets rid of acne", «guérit les boutons», «يعالج حب الشباب».
- Fine: cosmetic wording such as "helps skin look more even" or "skin feels soothed".

## 3. Unrealistic or guaranteed results

No guaranteed, permanent, instant or age-reversing promises, and no before/after comparisons.

- Fails: "guaranteed glow", "permanent results", "instantly erases lines", "turn back the clock", «avant / après», «قبل وبعد».
- Fine: a money-back or returns promise, because it's about refunds, not results.

## 4. Misleading or sensational claims

No invented authority, "secret" hooks, shock headlines or false urgency.

- Fails: "Celebrities secretly use this cream", "Doctors are shocked", "Last chance, only 2 left" (when that isn't true).
- Warn: "clinically proven", "dermatologist recommended", "#1". These are allowed only if the shop keeps the evidence on file.

## 5. Brand rules (Lumi Skin)

- No brand-banned words. The list is in `data/brand.json`, and a brief can add more. The list includes miracle, flawless, perfect skin, anti-aging and cheap, plus skin "whitening", "fairness" or "bleaching" language in any language and any word form.
- Voice: warm, simple and honest, with at most one exclamation mark. Don't write words in capitals (a style warning).

## 6. Offers and product disclaimers

- A discount, promo code or free gift needs a terms line: "T&Cs apply." / «Voir conditions.» / «تطبق الشروط والأحكام.»
- If the brief lists a required sentence, such as "Patch test first." for strong actives or "Reapply every 2 hours." for sunscreens, the primary text must include it.

## 7. Length per placement (characters, spaces included)

| Placement | Primary text | Headline |
|---|---|---|
| facebook_feed | 125 | 27 |
| instagram_feed | 125 | 40 |
| stories | 125 | 40 |
| reels | 72 | 40 |

These limits are display recommendations, so the text isn't cut off. They come from a third-party summary of Meta's Ads Guide (adsuploader.com, read 8 October 2026). Meta accepts longer text, but this demo treats going over the limit as a fail. Python counts Arabic diacritics as characters.

## 8. Call to action

Use one of these button types: SHOP_NOW, LEARN_MORE, ORDER_NOW, GET_OFFER or SIGN_UP. Meta translates the button label itself.

## What the code checks and what needs the LLM or a person

| Item | Code rules (`checker.py`) | Needs LLM review or a person |
|---|---|---|
| 1 Personal attributes | Phrases such as "your" or "do you have" near a listed condition word | Implied feelings with no condition word |
| 2 Medical claims | Verbs such as treat, cure or remove near a condition word | Paraphrases the patterns don't list |
| 3 Unrealistic results | Guaranteed, forever, overnight, before/after | Age-reversing claims and other time spans |
| 4 Misleading claims | Warns on "clinically proven" or "#1" | Sensational hooks and fake authority |
| 5 Brand words | Exact words from the list | Other word forms (gender or plural endings) |
| 6 Offers and disclaimers | Discount words without a terms line; required sentences | Unusual offer wording |
| 7 Length | Yes, exactly | — |
| 8 CTA | Yes, exactly | — |
