"""Rule data for the deterministic ad checker (a SIMPLIFIED DEMO).

The categories are paraphrased, in general terms, from Meta's public Advertising
Standards (https://transparency.meta.com/policies/ad-standards/) plus the fictional
Lumi Skin brand rules. They are not Meta's real review system and not legal advice.
See docs/policy_checklist.md for the plain-language version.

How to read the patterns:
- They are regular expressions, written in lower case.
- Before matching, both the text and the patterns are "folded": accents and Arabic
  diacritics are removed, and أ/إ/آ become ا (see checker.fold). So "acné" matches "acne".
- `{c}` inside a pattern is replaced by the list of skin conditions for that language.
- English and French patterns use \\b word boundaries. Arabic patterns do not, because
  Arabic attaches prefixes such as و (and) and ب (with) to the next word.
"""

# --- Length guidelines per placement (characters) ------------------------------------
# Display recommendations so text is not cut off ("...See more"), taken from a third-party
# summary of Meta's Ads Guide (adsuploader.com/blog/meta-ad-copy-specs, read 2026-10-08).
# Meta accepts longer text; this demo treats going over as a FAIL to keep copy tight.
# Check Meta's current Ads Guide before relying on these numbers.
PLACEMENT_LIMITS = {
    "facebook_feed": {"primary_text": 125, "headline": 27},
    "instagram_feed": {"primary_text": 125, "headline": 40},
    "stories": {"primary_text": 125, "headline": 40},
    "reels": {"primary_text": 72, "headline": 40},
}

# Call-to-action buttons this demo allows. Meta translates the button label itself,
# so the copy stores a button type, not free text.
ALLOWED_CTAS = {
    "SHOP_NOW": {"en": "Shop now", "ar": "تسوّق الآن", "fr": "Acheter"},
    "LEARN_MORE": {"en": "Learn more", "ar": "اعرف المزيد", "fr": "En savoir plus"},
    "ORDER_NOW": {"en": "Order now", "ar": "اطلب الآن", "fr": "Commander"},
    "GET_OFFER": {"en": "Get offer", "ar": "احصل على العرض", "fr": "Profiter de l'offre"},
    "SIGN_UP": {"en": "Sign up", "ar": "سجّل الآن", "fr": "S'inscrire"},
}

# --- Skin and health conditions -------------------------------------------------------
# Used for two rules: claims to treat them (medical claim) and saying the reader has them
# (personal attribute). Skin TYPES (dry, oily, sensitive) are deliberately not here:
# "made for dry skin" describes the product, which this demo allows.
CONDITIONS = {
    "en": [
        "acne", "pimples", "breakouts", "eczema", "psoriasis", "rosacea", "dermatitis",
        "melasma", "hyperpigmentation", "pigmentation", "dark spots", "wrinkles",
        "fine lines", "scars", "acne scars", "cellulite", "hair loss", "blemishes",
    ],
    "fr": [
        "acné", "boutons", "eczéma", "psoriasis", "rosacée", "dermatite", "mélasma",
        "hyperpigmentation", "taches brunes", "taches pigmentaires", "taches", "rides",
        "ridules", "cicatrices", "cellulite", "chute de cheveux", "imperfections",
    ],
    "ar": [
        "حب الشباب", "البثور", "الحبوب", "الأكزيما", "الإكزيما", "الصدفية", "الوردية",
        "الكلف", "التصبغات", "البقع الداكنة", "التجاعيد", "الخطوط الدقيقة", "الندوب",
        "آثار حب الشباب", "السيلوليت", "تساقط الشعر",
    ],
}

# --- FAIL rules: (rule name, pattern, reason shown to the reviewer) ---------------------
CLAIM_PATTERNS = {
    "en": [
        ("medical_claim", r"\bcur(e|es|ed|ing)\b", "Says the product cures something"),
        ("medical_claim", r"\bheal(s|ed|ing)?\b", "Says the product heals"),
        (
            "medical_claim",
            r"\btreat(s|ed|ing)?\s+(your\s+)?({c})\b",
            "Says it treats a condition",
        ),
        (
            "medical_claim",
            r"\btreatment\s+(for|of)\s+({c})\b",
            "Presents itself as a treatment",
        ),
        (
            "medical_claim",
            r"\b(eliminat\w*|erase\w*|remov\w*|get(s)? rid of|clear(s)?( up)?|stop(s)?)\s+"
            r"(\w+\s+){0,2}({c})\b",
            "Promises to remove a skin or health condition",
        ),
        (
            "unrealistic_claim",
            # "guaranteed" promises a result; "satisfaction guaranteed" and a
            # "money-back guarantee" are about refunds, so they are allowed.
            r"\bguarantee(s)?\s+(results?|to|you)\b|(?<!satisfaction )\bguaranteed\b",
            "Guaranteed results",
        ),
        (
            "unrealistic_claim",
            r"\b100\s?%\s*(guaranteed|effective|results|safe)\b",
            "100% claim",
        ),
        ("unrealistic_claim", r"\bno side effects\b", "Says there are no side effects"),
        ("unrealistic_claim", r"\b(forever|permanent(ly)?)\b", "Permanent or forever result"),
        (
            "unrealistic_claim",
            r"\b(overnight|instant(ly)?|in (\d+|one|two|three) days?)\b[^.!?]{0,30}"
            r"\b(disappear\w*|eras\w*|remov\w*|gone|transform\w*|flawless)\b",
            "Unrealistic speed of results",
        ),
        ("before_after", r"\bbefore\s*(and|&|/|vs\.?)\s*after\b", "Before/after claim"),
    ],
    "fr": [
        ("medical_claim", r"\bgueri(t|r|ssent|son)\b", "Dit que le produit guérit"),
        (
            "medical_claim",
            r"\b(trait|soign)(e|ent|er)\s+(l'|les\s+|vos\s+|votre\s+)?({c})\b",
            "Dit traiter ou soigner une affection",
        ),
        (
            "medical_claim",
            r"\btraitement\s+(contre|de|des|anti)\s*(l'|les\s+)?({c})\b",
            "Se présente comme un traitement",
        ),
        (
            "medical_claim",
            r"\b(elimin\w*|efface\w*|supprim\w*|fait disparaitre|debarrass\w*|stoppe\w*)\s+"
            r"(\w+'?\s*){0,2}({c})\b",
            "Promet de supprimer une affection",
        ),
        (
            "unrealistic_claim",
            r"\bresultats?\s+garantis?\b|\bgaranti(e|s|es)?\s+(a\s+)?100\b|"
            r"\bgarantit\s+des\s+resultats\b",
            "Résultats garantis",
        ),
        (
            "unrealistic_claim",
            r"\b100\s?%\s*(garanti\w*|efficace|sur|sans risque)\b",
            "Promesse à 100 %",
        ),
        (
            "unrealistic_claim",
            r"\bsans effets? secondaires?\b",
            "Dit qu'il n'y a pas d'effets secondaires",
        ),
        ("unrealistic_claim", r"\b(pour toujours|definitivement|a jamais)\b", "Résultat permanent"),
        (
            "unrealistic_claim",
            r"\b(en une nuit|instantanement|du jour au lendemain|en (\d+|un|deux|trois) jours?)\b"
            r"[^.!?]{0,30}\b(dispar\w*|efface\w*|transform\w*|parfaite?)\b",
            "Vitesse de résultat irréaliste",
        ),
        ("before_after", r"\bavant\s*(et|/|-|vs\.?)\s*apres\b", "Allégation avant/après"),
    ],
    "ar": [
        ("medical_claim", r"يعالج|يعالجان|علاج ({c})|لعلاج", "يدّعي علاج حالة"),
        ("medical_claim", r"يشفي|شفاء", "يدّعي الشفاء"),
        (
            "medical_claim",
            r"(يقضي على|تقضي على|القضاء على|يزيل|تزيل|إزالة|تخلص(ي|وا)? من|يخلصك من|يمحو)\s*({c})",
            "يعد بإزالة حالة جلدية",
        ),
        ("unrealistic_claim", r"نتائج مضمونة|مضمونة 100|نتيجة مضمونة|نضمن لك", "نتائج مضمونة"),
        ("unrealistic_claim", r"(100|١٠٠)\s?(%|٪)\s*(مضمون|فعال|آمن)", "ادعاء 100٪"),
        (
            "unrealistic_claim",
            r"بدون آثار جانبية|بلا آثار جانبية|دون آثار جانبية",
            "ينفي الآثار الجانبية",
        ),
        ("unrealistic_claim", r"للأبد|إلى الأبد|نهائيا|بشكل نهائي|بشكل دائم", "نتيجة دائمة"),
        (
            "unrealistic_claim",
            r"(بين ليلة وضحاها|في ليلة واحدة|فورا|خلال (\d+|يوم|يومين|ثلاثة) (أيام|يوم))"
            r"[^.!?،؟]{0,30}(تختفي|يختفي|تزول|يزول|بشرة مثالية)",
            "سرعة نتائج غير واقعية",
        ),
        ("before_after", r"قبل\s*(و|/|-)\s*بعد", "ادعاء قبل/بعد"),
    ],
}

# Saying or implying that the reader has a condition ("Are you struggling with acne?").
PERSONAL_ATTRIBUTE_PATTERNS = {
    "en": [
        r"\b(are you|do you( have| suffer)?|you have|you've got|you're|your|struggling with|"
        r"suffering from|suffer from|tired of|embarrassed by|hate your)\b[^.!?,]{0,25}\b({c})\b",
    ],
    "fr": [
        r"\b(vous avez|avez-vous|tu as|as-tu|vous souffrez|souffrez-vous|tu souffres|"
        r"marre de|fatigue(e)? de|honte de|votre|vos|ton|ta|tes)\b[^.!?,]{0,25}\b({c})\b",
    ],
    "ar": [
        r"(هل تعاني|تعانين|تعاني|هل لديك|هل عندك|لديك|عندك|سئمت|مللت|تعبت|تخجلين)"
        r"[^.!?،؟]{0,25}({c})",
        r"({c})\s*(لديك|عندك|في وجهك)",
        r"تجاعيدك|بثورك|حبوبك|كلفك|ندوبك|تصبغاتك|حبوب وجهك",
    ],
}

# --- WARN rules: allowed, but a person must check the evidence ---------------------------
NEEDS_EVIDENCE_PATTERNS = {
    "en": r"\bclinically (proven|tested)\b|\bdermatologist[- ](recommended|approved)\b|"
    r"\b(#1|number one|no\. ?1)\b|\bbest in (the )?(world|uae|gulf)\b",
    "fr": r"\bcliniquement (prouve|teste)e?s?\b|\brecommande(e)? par (les )?dermatologues\b|"
    r"\bn°\s?1\b|\bnumero un\b",
    "ar": r"مثبت سريريا|مختبر سريريا|ينصح به أطباء الجلد|يوصي به أطباء الجلد|"
    r"رقم 1|الأفضل في العالم",
}

# --- Offers need a terms-and-conditions line ---------------------------------------------
# A bare percentage is NOT treated as an offer, because skincare copy often names
# ingredient strengths ("vitamin C 15%"). Only discount wording counts.
OFFER_PATTERNS = {
    "en": r"\d+\s?%\s*off\b|\b(save|up to)\s+\d+\s?%|-\s?\d+\s?%|"
    r"\b(discount|sale|promo|coupon|voucher|free gift)\b|\bbuy (one|1|two|2),? get\b",
    "fr": r"-\s?\d+\s?%|\d+\s?%\s*(de\s+)?(reduction|remise)|"
    r"\b(reduction|remise|promo|soldes|code promo|offert|offerte|cadeau)\b",
    "ar": r"-\s?\d+\s?(%|٪)|خصم|تخفيض|تخفيضات|عرض خاص|هدية مجانية|كود",
}
DISCLAIMER_PATTERNS = {
    "en": r"\bt&cs? apply\b|\bterms( and conditions| & conditions)? apply\b",
    "fr": r"\bvoir conditions\b|\bconditions applicables\b|\bsous conditions\b|"
    r"\boffre soumise a conditions\b",
    "ar": r"تطبق الشروط|الشروط والأحكام",
}
DISCLAIMER_EXAMPLES = {"en": "T&Cs apply.", "fr": "Voir conditions.", "ar": "تطبق الشروط والأحكام."}

# Product names can contain condition words ("Salicylic Acne Cleanser"). When a brief is
# given, the checker blanks out the product name before running the claim rules.

# --- Style warnings (brand voice) -----------------------------------------------------
MAX_EXCLAMATION_MARKS = 1
MIN_SHOUTING_WORD_LENGTH = 4  # Latin words written fully in capitals, e.g. "SALE", "FREE"
