"""Tests for the deterministic checker (no network)."""

import json

import pytest

from ads_agent.checker import check_ad, fold, llm_review, normalize
from ads_agent.llm import FakeLLM


def ad(language, primary, headline="Short headline"):
    return {"language": language, "primary_text": primary, "headline": headline}


def failed(language, primary, headline="Short headline", **kwargs):
    return check_ad(ad(language, primary, headline), **kwargs).failed_rules


def test_fold_removes_accents_and_arabic_marks():
    assert fold("acné") == "acne"
    assert fold("الأكزيما") == "الاكزيما"
    assert fold("نهائياً") == fold("نهائيا")


def test_normalize_lowercases_and_unifies_spaces():
    assert normalize("  Vitamin C  SERUM ") == "vitamin c serum"


@pytest.mark.parametrize(
    "language, text, rule",
    [
        ("en", "Are you struggling with acne?", "personal_attribute"),
        ("fr", "Vous avez de l'acné ?", "personal_attribute"),
        ("ar", "هل تعانين من حب الشباب؟", "personal_attribute"),
        ("en", "This cream cures eczema.", "medical_claim"),
        ("fr", "Ce sérum élimine les boutons.", "medical_claim"),
        ("ar", "كريم يعالج الأكزيما.", "medical_claim"),
        ("en", "Results guaranteed.", "unrealistic_claim"),
        ("fr", "Résultats garantis.", "unrealistic_claim"),
        ("ar", "نتائج مضمونة.", "unrealistic_claim"),
        ("en", "See our before and after photos.", "before_after"),
        ("fr", "Effet avant/après.", "before_after"),
        ("ar", "صور قبل وبعد.", "before_after"),
        ("en", "A miracle serum.", "banned_word"),
        ("fr", "Un sérum miracle.", "banned_word"),
        ("ar", "سيروم معجزة.", "banned_word"),
    ],
)
def test_each_rule_fires_in_each_language(language, text, rule):
    assert rule in failed(language, text)


@pytest.mark.parametrize(
    "language, text",
    [
        ("en", "Made for oily, acne-prone skin. Light and fresh."),
        ("en", "Treat yourself to a calm evening routine."),
        ("en", "Not for you? 14-day returns. Satisfaction guaranteed."),
        ("fr", "Un gel léger pour peaux grasses."),
        ("ar", "مرطب خفيف للبشرة الدهنية."),
    ],
)
def test_compliant_cosmetic_wording_passes(language, text):
    assert failed(language, text) == []


def test_ingredient_percentage_is_not_an_offer():
    assert failed("en", "Vitamin C 15% serum for a fresh-looking glow.") == []


@pytest.mark.parametrize(
    "language, offer, terms",
    [
        ("en", "Save 20% this week.", "T&Cs apply."),
        ("fr", "-20 % cette semaine.", "Voir conditions."),
        ("ar", "خصم 20% هذا الأسبوع.", "تطبق الشروط والأحكام."),
    ],
)
def test_offer_needs_terms_line(language, offer, terms):
    assert failed(language, offer) == ["missing_disclaimer"]
    assert failed(language, f"{offer} {terms}") == []


def test_brief_required_disclaimer_and_product_name_masking():
    brief = {
        "id": "b-test",
        "product": "Salicylic Acne Cleanser",
        "placement": "instagram_feed",
        "required_disclaimers": {"en": "Patch test first."},
    }
    text = "Meet your Salicylic Acne Cleanser, made for oily skin."
    # "your ... Acne" would look like a personal attribute, but it is the product name.
    assert failed("en", text, brief=brief) == ["missing_disclaimer"]
    assert failed("en", text + " Patch test first.", brief=brief) == []


def test_length_limits_depend_on_placement():
    text = "x" * 100
    assert failed("en", text, placement="instagram_feed") == []
    assert failed("en", text, placement="reels") == ["length"]
    assert failed("en", "ok", "h" * 30, placement="facebook_feed") == ["length"]


def test_unknown_cta_fails():
    result = check_ad({**ad("en", "Fresh gel."), "cta": "BUY_EVERYTHING"})
    assert result.failed_rules == ["cta"]


def test_style_issues_are_warnings_not_failures():
    result = check_ad(ad("en", "FRESH new gel! Try it!"))
    assert result.passed
    assert {i.rule for i in result.issues} == {"style"}


def test_unsupported_language_raises():
    with pytest.raises(ValueError):
        check_ad(ad("de", "Hallo"))


def test_llm_review_fail_pass_and_unreadable():
    fail = FakeLLM({"policy_review": json.dumps({"verdict": "fail", "reasons": ["shock hook"]})})
    assert llm_review(ad("en", "x"), fail)[0].severity == "fail"
    assert llm_review(ad("en", "x"), FakeLLM()) == []  # canned answer is "pass"
    unreadable = llm_review(ad("en", "x"), FakeLLM({"policy_review": "no json here"}))
    assert unreadable[0].severity == "warn"


def test_llm_layer_can_fail_an_ad_the_rules_pass():
    fail = FakeLLM({"policy_review": json.dumps({"verdict": "fail", "reasons": ["misleading"]})})
    result = check_ad(ad("en", "Doctors are shocked by this cream."), llm=fail)
    assert not result.passed
    assert result.failed_rules == ["llm_review"]
