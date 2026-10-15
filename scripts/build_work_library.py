# -*- coding: utf-8 -*-
"""
build_work_library.py — turn a product that has images + _LINK.txt into a
ready-to-edit work library by auto-writing _CAPTIONS.md.

Called automatically the moment a product gets its content:
  • non-AliExpress → right after approval (image auto-downloaded)
  • AliExpress     → right after the first photo is attached

Idempotent: skips a product that already has _CAPTIONS.md.
"""
import os

# Style variants keyed on words in the product title. First match wins;
# otherwise the generic high-heel angle is used. Copy is about the SHOE (high
# heels, stilettos, pumps, platforms, heeled boots) - no URLs, no niche aesthetics.
_STYLES = [
    (("glitter", "sparkl", "sequin", "rhinestone", "crystal"),
     "Midnight, cast in glitter. \u2728",
     "The heel that turns an ordinary night into an entrance.",
     ["glitterheels", "sparkleheels"]),
    (("satin", "silk"),
     "Liquid black, poured into a heel. \U0001F460",
     "Satin that catches the light only when you move.",
     ["satinheels", "eveningshoes"]),
    (("platform", "chunky"),
     "Elevation, with a little extra. \U0001F460",
     "Platform power without losing the stiletto line.",
     ["platformheels", "platformpumps"]),
    (("gladiator", "lace-up", "lace up", "strappy", "thigh"),
     "Laced from heel to thigh. \U0001F460",
     "Strappy, sculpted, and made to be noticed.",
     ["gladiatorheels", "strappyheels"]),
    (("boot", "knee", "otk"),
     "Every step lands. \U0001F460",
     "The heeled boot that finishes the whole outfit.",
     ["heeledboots", "bootsseason"]),
    (("clear", "transparent", "perspex"),
     "Nothing to hide. \u2728",
     "A transparent heel with serious presence.",
     ["clearheels", "transparentheels"]),
    (("red", "burgundy"),
     "The red heel moment. \u2764\uFE0F",
     "One red pair that makes the whole look.",
     ["redheels", "statementheels"]),
]
_GENERIC = ("The one pair that never asks permission. \U0001F460",
            "Pointed, poised, and impossible to ignore.",
            ["stilettoheels", "blackheels"])

_BASE_TAGS = ["stilettos", "highheels", "heels", "heelsaddict", "pumps",
              "thestilettovault"]


def _style_for(title):
    t = (title or "").lower()
    for keys, hook, line, tags in _STYLES:
        if any(k in t for k in keys):
            return hook, line, tags
    return _GENERIC


def _list_media(folder):
    imgs = sorted(f for f in os.listdir(folder)
                  if f.lower().endswith((".jpg", ".jpeg", ".png")))
    return imgs


def captions_text(title, aff_link, commission, folder):
    hook, line, style_tags = _style_for(title)
    tags = style_tags + _BASE_TAGS
    ig_tags = " ".join("#" + x for x in tags) + " #ad #affiliate"
    tt_tags = " ".join("#" + x for x in (["shoetok"] + tags)) + " #ad #affiliate"
    hook_pov = hook.rstrip(" 👠✨❤️")
    media = ", ".join(_list_media(folder)) or "(תמונות ייווצרו בהפקה)"
    return f"""# Captions — {title}
מוצר: {title} (עמלה {commission or 'TBD'})
לינק: {aff_link}

## מדיה בתיקייה
{media}

## 📸 Instagram caption
{hook}
{line}

Link in bio \U0001F517

{ig_tags}

## 🎵 TikTok caption
POV: {hook_pov} - {line}
Link in bio \U0001F517

{tt_tags}

## הערות
- גילוי שותפים: #ad + commission earned.
- תזמון: 14:00 / 18:00 / 22:00 (IL). שיבוץ לפי GELEM/_SCHEDULE.md (יום כן יום לא, בלי שבת).
"""


def scaffold(item):
    """Write _CAPTIONS.md for a catalog item if its folder has content and no
    captions yet. Returns the captions path on success, or "" (skip/failure)."""
    local = item.get("local_asset") or ""
    if not local:
        return ""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    folder = os.path.join(root, local)
    if not os.path.isdir(folder):
        return ""
    cap_path = os.path.join(folder, "_CAPTIONS.md")
    if os.path.exists(cap_path):
        return cap_path            # idempotent — already scaffolded
    # need at least one image present
    if not _list_media(folder):
        return ""
    try:
        text = captions_text(item.get("title", "Product"),
                             item.get("aff_link", item.get("url", "")),
                             item.get("commission", ""), folder)
        with open(cap_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[worklib] captions ready: {local}/_CAPTIONS.md")
        return cap_path
    except Exception as e:
        print(f"[worklib] scaffold failed: {e}")
        return ""


if __name__ == "__main__":
    # Backfill: scaffold every catalog product that has content but no captions.
    import json
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    cat = json.load(open(os.path.join(root, "data", "approved_catalog.json"), encoding="utf-8"))
    done = sum(1 for it in cat if scaffold(it))
    print(f"[worklib] scaffolded {done} product(s).")
