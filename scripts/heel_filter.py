# -*- coding: utf-8 -*-
"""
heel_filter.py — the single "is this a high heel?" gate, shared by product_scout
(Shopify), aliexpress_scout (raw item titles) and admitad_feed (via product_scout).

Rules (title-driven; tags only ever add a positive signal):
  1. adult-content deny list → out (whole-word match, so "Peacock Stiletto" and
     "Cocktail Heel" are NOT hit by "cock"). Not footwear at all (jeans, dress,
     bag, ring, socks...) → out.
  2. STRONG cue in the title (heel / stiletto / pump with heel context) → in.
  3. non-heel word in the title (sneaker, trainer, flat, loafer, ...) → out.
     This runs BEFORE the weak cues, so "Platform Sneaker", "Wedge Sneakers",
     "Flat Mule" and "Studio Pump Trainers" are rejected.
  4. weak heel cue (platform, wedge, mule, slingback, strappy, ...) in the title
     or tags → in.
  5. ambiguous silhouette (boot / sandal) → in (non-heel words already checked).
"""
import re

# Adult-content deny list (always applied — not niche-related).
EXCLUDE_KEYWORDS = [
    "vibrat", "dildo", "orgasm", "anal", "butt plug", "masturbat",
    "cock", "penis", "vagina", "sex toy", "clitoral",
    "lubric", "condom", "strap-on", "strapon",
]
_STEMS = {"vibrat", "masturbat", "lubric"}      # prefix match (vibrator, lubricant...)

# Weak heel cues (any height / style). Strong cues are handled in has_strong_cue().
HEEL_POSITIVE = [
    "stiletto", "heel", "heels", "heeled", "high heel", "high-heel",
    "pump", "pumps", "court shoe", "slingback", "sling back", "platform",
    "wedge", "mule", "gladiator", "peep toe", "peep-toe", "pointed toe",
    "ankle strap", "strappy", "d'orsay", "thigh high", "thigh-high",
    "over the knee", "over-the-knee", "kitten heel", "block heel", "mid heel",
]

# Ambiguous silhouettes (could be flat) — admit unless a non-heel word is present.
AMBIGUOUS_FOOTWEAR = ["boot", "boots", "bootie", "booties", "sandal", "sandals"]

# Genuinely NOT a heel — matched on the TITLE only, on word boundaries.
NONHEEL_EXCLUDE = [
    "sneaker", "trainer", "running", "hiking", "athletic", "ballet",
    "flat", "flats", "loafer", "slipper", "moccasin", "espadrille", "clog",
    "ugg", "snow boot", "rain boot", "wellington", "wellie", "birkenstock",
    "flip flop", "flip-flop", "canvas", "oxford", "derby", "brogue",
    "flatform", "slide", "slides", "crocs",
]

# Not footwear at all (apparel / accessories). Checked FIRST, on the title: a full-
# catalogue scan of a fashion store (2026-10-16) let "Punk Strappy ... Baggy Jeans"
# through on the weak cue "strappy" + a "heels" store tag.
NON_FOOTWEAR = [
    "jean", "jeans", "pant", "pants", "trouser", "trousers", "legging", "leggings", "shorts",
    "dress", "skirt", "top", "tee", "t-shirt", "shirt", "blouse", "corset", "bodysuit",
    "jacket", "coat", "hoodie", "sweater", "cardigan", "vest", "lingerie", "bra",
    "bag", "handbag", "purse", "backpack", "wallet", "ring", "necklace", "earring",
    "bracelet", "choker", "pendant", "socks", "sock", "stockings", "tights", "belt",
    "hat", "cap", "gloves", "harness", "sunglasses",
]
# Accessories FOR shoes - never a shoe, even next to a footwear word.
SHOE_ACCESSORY = ["protector", "insole", "insoles", "heel grip", "heel cap", "shoe tree",
                  "sock", "socks", "stockings", "tights", "anklet"]
# A footwear noun keeps a product in despite an apparel word ("The Bag Boot").
FOOTWEAR_NOUN = ["boot", "bootie", "sandal", "mule", "pump", "shoe", "stiletto", "heel",
                 "slingback", "loafer", "sneaker", "clog", "wedge", "platform"]

_PUMP_CONTEXT = ["pointed", "kitten", "court", "slingback", "d'orsay", "dorsay",
                 "stiletto", "heel", "heels", "heeled"]


def _has_word(text, words, plural=False):
    """True if any phrase in `words` appears in `text` on word boundaries
    (plural=True also accepts a trailing s/es: sneaker -> sneakers)."""
    tail = r"(?:s|es)?\b" if plural else r"\b"
    return any(re.search(r"\b" + re.escape(w) + tail, text) for w in words)


def is_excluded(title):
    """Adult-content deny list, whole-word (stems prefix-matched)."""
    text = (title or "").lower()
    for kw in EXCLUDE_KEYWORDS:
        pat = r"\b" + re.escape(kw) + (r"\w*" if kw in _STEMS else r"(?:s|es)?\b")
        if re.search(pat, text):
            return True
    return False


def has_strong_cue(title):
    """Unambiguous heel language: stiletto, heel(s/ed), or a 'pump' that has heel context."""
    t = (title or "").lower()
    if re.search(r"\bstilettos?\b|\bheels?\b|\bheeled\b|\bhigh[- ]heel", t):
        return True
    if re.search(r"\bpumps?\b", t) and _has_word(t, _PUMP_CONTEXT):
        return True
    return False


def is_high_heel(title, tags=None):
    """High-heels gate — every heel height. See module docstring for the order."""
    title_l = (title or "").lower()
    tag_l = (tags if isinstance(tags, str) else " ".join(map(str, tags or []))).lower()
    if _has_word(title_l, SHOE_ACCESSORY, plural=True):
        return False
    if _has_word(title_l, NON_FOOTWEAR, plural=True) and not _has_word(title_l, FOOTWEAR_NOUN, plural=True):
        return False
    if has_strong_cue(title_l):
        return True
    if _has_word(title_l, NONHEEL_EXCLUDE, plural=True):
        return False
    if _has_word(title_l, HEEL_POSITIVE, plural=True):
        return True
    if tag_l and any(w in tag_l for w in HEEL_POSITIVE):
        return True
    if any(w in title_l for w in AMBIGUOUS_FOOTWEAR):
        return True
    return False


def passes(title, tags=None):
    """Adult deny-list AND high-heel gate."""
    return (not is_excluded(title)) and is_high_heel(title, tags)
