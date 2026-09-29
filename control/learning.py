"""Learning: joins catalog/production shoe data with click/sale metrics to find
which attributes (price band, program, discount band, has_video, weekday)
correlate with clicks. No network calls here — callers inject data or use
load_default() to read the real repo files.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

HEBREW_WEEKDAYS = {
    0: "שני",
    1: "שלישי",
    2: "רביעי",
    3: "חמישי",
    4: "שישי",
    5: "שבת",
    6: "ראשון",
}

VALUE_LABELS = {"True": "עם וידאו", "False": "בלי וידאו", "true": "עם וידאו", "false": "בלי וידאו",
                "none": "בלי הנחה", "unknown": "לא ידוע"}


def vlabel(v):
    return VALUE_LABELS.get(str(v), str(v))


ATTRIBUTE_LABELS = {
    "price_band": "טווח מחיר",
    "program": "תוכנית שותפים",
    "discount_band": "אחוז הנחה",
    "has_video": "קיים וידאו",
    "weekday": "יום בשבוע",
}


def _price_band(price):
    if not price:
        return "unknown"
    try:
        value = float(str(price).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return "unknown"
    if value < 20:
        return "<$20"
    if value < 50:
        return "$20-50"
    if value < 100:
        return "$50-100"
    return "$100+"


def _program(aff_link):
    if not aff_link:
        return "unknown"
    link = str(aff_link).lower()
    if "rzekl" in link:
        return "aliexpress"
    if "amazon" in link or "amzn" in link:
        return "amazon"
    try:
        domain = urlparse(str(aff_link)).netloc
        return domain or "unknown"
    except Exception:
        return "unknown"


def _discount_band(discount):
    if not discount:
        return "none"
    try:
        value = float(str(discount).replace("%", "").strip())
    except (TypeError, ValueError):
        return "none"
    if value <= 0:
        return "none"
    if value < 30:
        return "<30%"
    if value < 60:
        return "30-60%"
    return "60%+"


def _weekday(date_str):
    if not date_str:
        return "unknown"
    try:
        dt = datetime.strptime(str(date_str), "%Y-%m-%d")
    except (TypeError, ValueError):
        return "unknown"
    return HEBREW_WEEKDAYS.get(dt.weekday(), "unknown")


def _has_video(shoe, state, gelem_root):
    slug = shoe.get("slug")
    if state:
        entry = state.get(slug) if isinstance(state, dict) else None
        if entry and isinstance(entry, dict):
            video_path = entry.get("video")
            if video_path:
                return True
    if gelem_root and slug:
        candidate = os.path.join(gelem_root, slug, "video.mp4")
        if os.path.exists(candidate):
            return True
    return False


def features(shoe, state=None, gelem_root=None):
    """Compute derived attributes for a single shoe dict."""
    return {
        "price_band": _price_band(shoe.get("price")),
        "program": _program(shoe.get("aff_link")),
        "discount_band": _discount_band(shoe.get("discount")),
        "has_video": _has_video(shoe, state, gelem_root),
        "weekday": _weekday(shoe.get("date")),
    }


def table(shoes, states=None, gelem_root=None):
    """Aggregate clicks/sales per attribute/value across all shoes.

    Returns a list of rows: {attribute, value, shoes, clicks, clicks_per_shoe, sales}
    """
    agg = defaultdict(lambda: {"shoes": 0, "clicks": 0, "sales": 0})

    for shoe in shoes or []:
        feats = features(shoe, states, gelem_root)
        clicks = shoe.get("clicks") or 0
        try:
            clicks = int(clicks)
        except (TypeError, ValueError):
            clicks = 0
        sales = shoe.get("sales") or 0
        try:
            sales = int(sales)
        except (TypeError, ValueError):
            sales = 0

        for attribute, value in feats.items():
            key = (attribute, value)
            entry = agg[key]
            entry["shoes"] += 1
            entry["clicks"] += clicks
            entry["sales"] += sales

    rows = []
    for (attribute, value), entry in agg.items():
        shoe_count = entry["shoes"]
        clicks_per_shoe = round(entry["clicks"] / shoe_count, 1) if shoe_count else 0.0
        rows.append(
            {
                "attribute": attribute,
                "value": value,
                "shoes": shoe_count,
                "clicks": entry["clicks"],
                "clicks_per_shoe": clicks_per_shoe,
                "sales": entry["sales"],
            }
        )

    rows.sort(key=lambda r: (r["attribute"], -r["clicks_per_shoe"]))
    return rows


def summary(rows, min_shoes=3):
    """Build short Hebrew sentences: best/worst value per attribute."""
    total_clicks = sum(r.get("clicks") or 0 for r in rows)
    if total_clicks == 0:
        return ["אין עדיין מספיק נתוני קליקים ללמידה."]

    by_attribute = defaultdict(list)
    for row in rows:
        if row["shoes"] >= min_shoes:
            by_attribute[row["attribute"]].append(row)

    sentences = []
    for attribute, attr_rows in by_attribute.items():
        if not attr_rows:
            continue
        attr_rows_sorted = sorted(attr_rows, key=lambda r: -r["clicks_per_shoe"])
        best = attr_rows_sorted[0]
        worst = attr_rows_sorted[-1]
        label = ATTRIBUTE_LABELS.get(attribute, attribute)
        if best is worst:
            sentences.append(
                f"{label}: {vlabel(best['value'])} מוביל עם {best['clicks_per_shoe']} קליקים לנעל."
            )
        else:
            sentences.append(
                f"{label}: {vlabel(best['value'])} מוביל עם {best['clicks_per_shoe']} קליקים לנעל; "
                f"{vlabel(worst['value'])} הכי חלש ({worst['clicks_per_shoe']})."
            )
    return sentences


def shoes_with_features(shoes=None, states=None, gelem_root=None, catalog=None):
    """Join each shoe with its computed features + the product image/url from
    the approved catalog (matched by aff_link, since that's what both sides share).
    """
    if shoes is None:
        shoes, states = load_default()
    if catalog is None:
        catalog_path = os.path.join(ROOT, "data", "approved_catalog.json")
        catalog = []
        if os.path.exists(catalog_path):
            with open(catalog_path, "r", encoding="utf-8") as f:
                catalog = json.load(f)

    by_aff = {}
    for it in catalog or []:
        key = it.get("aff_link") or it.get("url")
        if key:
            by_aff[key] = it

    out = []
    for shoe in shoes or []:
        feats = features(shoe, states, gelem_root)
        cat = by_aff.get(shoe.get("aff_link"), {})
        clicks = shoe.get("clicks") or 0
        try:
            clicks = int(clicks)
        except (TypeError, ValueError):
            clicks = 0
        sales = shoe.get("sales") or 0
        try:
            sales = int(sales)
        except (TypeError, ValueError):
            sales = 0
        out.append({
            "slug": shoe.get("slug"),
            "title": shoe.get("name") or shoe.get("title"),
            "image_url": cat.get("image_url", ""),
            "url": cat.get("url", ""),
            "aff_link": shoe.get("aff_link", ""),
            "price": shoe.get("price"),
            "clicks": clicks,
            "sales": sales,
            "status": shoe.get("status", ""),
            "date": shoe.get("date", ""),
            "features": feats,
        })
    return out


def insights(shoes, states=None, gelem_root=None, min_shoes=3, min_multiplier=1.15):
    """Plain-Hebrew, actionable insight cards: each value that beats the
    overall average clicks-per-shoe by min_multiplier, phrased as advice,
    with the slice (attribute/value) so the UI can apply it as a filter.
    """
    if not shoes:
        return []
    total_clicks = 0
    count = 0
    for s in shoes:
        try:
            c = int(s.get("clicks") or 0)
        except (TypeError, ValueError):
            c = 0
        total_clicks += c
        count += 1
    overall_avg = (total_clicks / count) if count else 0
    if overall_avg <= 0:
        return []

    rows = table(shoes, states, gelem_root)
    cards = []
    for r in rows:
        if r["shoes"] < min_shoes:
            continue
        cps = r["clicks_per_shoe"]
        mult = cps / overall_avg if overall_avg else 0
        if mult < min_multiplier:
            continue
        label = ATTRIBUTE_LABELS.get(r["attribute"], r["attribute"])
        value_label = vlabel(r["value"])
        cards.append({
            "attribute": r["attribute"],
            "value": r["value"],
            "multiplier": round(mult, 1),
            "shoes": r["shoes"],
            "text": (
                f"💡 {label}: {value_label} מקבל פי {round(mult, 1)} קליקים "
                f"מהממוצע — שווה לבחור יותר כאלה."
            ),
        })

    cards.sort(key=lambda c: -c["multiplier"])
    return cards[:5]


def load_default():
    """Load shoes + orchestrator state from the real repo files."""
    data_path = os.path.join(ROOT, "dashboard", "data.json")
    state_path = os.path.join(ROOT, "data", "orchestrator_state.json")

    shoes = []
    if os.path.exists(data_path):
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        shoes = data.get("shoes", [])

    states = {}
    if os.path.exists(state_path):
        with open(state_path, "r", encoding="utf-8") as f:
            states = json.load(f)

    return shoes, states


def _main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    shoes, states = load_default()
    gelem_root = os.path.join(ROOT, "GELEM")
    rows = table(shoes, states, gelem_root)

    print(f"{'attribute':<14} {'value':<14} {'shoes':>6} {'clicks':>7} {'c/shoe':>7} {'sales':>6}")
    for row in rows:
        print(
            f"{row['attribute']:<14} {str(row['value']):<14} {row['shoes']:>6} "
            f"{row['clicks']:>7} {row['clicks_per_shoe']:>7} {row['sales']:>6}"
        )

    print()
    print("סיכום:")
    for line in summary(rows):
        print("- " + line)


if __name__ == "__main__":
    _main()
