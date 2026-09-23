# -*- coding: utf-8 -*-
"""
pinterest_missing.py — rebuild ONLY the generic-title heels that Pinterest's
Bulk Create rejected as near-duplicates ("Stiletto Heels — only $X ...").

Root cause (2026-09-23): 27 AliExpress-scouted heels carry a bare category
title ("Stiletto Heels" / "Pointed-Toe Pump" / "Platform High Heels"). Bulk
Create dedups on the *leading words* of the title, not the exact string, so
27 rows that all began "Stiletto Heels — only $..." were silently dropped;
only the 17 rows with a distinct product name published.

Fix: give each of the 27 a genuinely distinct EDITORIAL title (different
opening words per pin), deterministically keyed to the item id so re-runs are
stable, then emit a clean Bulk-Create CSV to upload once.

Usage:
    py -3 pinterest_missing.py            # -> dashboard/pinterest_missing.csv
"""
import sys, os, csv, json
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8") if sys.stdout else None
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import space_runner, affiliate_links

ROOT    = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "approved_catalog.json"
OUT     = ROOT / "dashboard" / "pinterest_missing.csv"
SITE    = "thestilettovault.github.io"

# Distinct editorial openers — one per pin, keyed by item id. Each starts with
# different words so Pinterest's title-dedup treats them as unique pins.
OPENERS = [
    "Glossy Black Pointed-Toe Stilettos", "Sleek Party Heels You'll Live In",
    "Date-Night Stilettos That Do The Talking", "The Little Black Heel, Perfected",
    "Barely-There Strappy Stilettos", "Editor-Approved Everyday Heels",
    "Sky-High Pointed Pumps", "Minimalist Stilettos, Maximum Impact",
    "Your New Going-Out Heel", "Classic Court Heels, Reworked",
    "Sharp Pointed-Toe Pumps", "The Under-$20 Heel Worth Hoarding",
    "Runway-Ready Stiletto Pumps", "Sultry Slingback Stilettos",
    "Statement Platform Heels", "The Heel That Elevates Everything",
    "Polished Pointed Pumps", "Wear-With-Anything Black Stilettos",
    "Elegant High-Shine Heels", "Bold Pointed-Toe Party Pumps",
    "Timeless Stiletto Court Shoes", "The 'Where'd-You-Get-Those' Heel",
    "Chic Closet-Staple Stilettos", "Effortless Evening Heels",
    "Modern Pointed Stilettos", "The Quiet-Luxury Black Heel",
    "Show-Stopping Stiletto Pumps", "Sleek Platform Party Stilettos",
    "Refined Pointed-Toe Heels", "Everyday Luxe Stilettos",
]

def hosted(it):
    a = it.get("assets", {}) or {}
    for v in [a.get("image_1x1")] + (a.get("images_ig") or []) + [it.get("image_url", "")]:
        if v and SITE in v:
            return v
    return None

def is_generic(it):
    t = (it.get("title") or "").strip().lower()
    return (not t) or t in ("stiletto heels", "pointed-toe pump",
                            "platform high heels", "high heels") or len(t) < 14

def _live(url):
    import urllib.request
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception:
        return False

def title(it, idx):
    lead = OPENERS[idx % len(OPENERS)]
    d = it.get("deal", {}) or {}
    sale, disc = d.get("sale"), str(d.get("discount", "") or "").strip()
    if sale and disc and disc not in ("0%", "0"):
        return f"{lead} — ${sale} ({disc} off) \U0001f5a4"
    if sale:
        return f"{lead} — just ${sale} \U0001f5a4"
    return f"{lead} \U0001f5a4"

def desc(it):
    d = it.get("deal", {}) or {}
    sale, was, disc = d.get("sale"), d.get("was"), str(d.get("discount", "") or "").strip()
    head = "Obsessed."
    if sale and was and disc:
        head = f"Obsessed. ${sale} instead of ${was} — {disc} off."
    elif sale:
        head = f"Obsessed. Just ${sale}."
    return (f"{head} The stiletto that looks way more expensive than it is. "
            f"Tap to grab yours before it sells out \U0001f5a4 "
            f"#heels #stilettos #shoefinds #affordablefashion #heelsaddict")

def main():
    catalog = json.load(open(CATALOG, encoding="utf-8-sig"))
    rows, skipped, idx = [], 0, 0
    for it in catalog:
        if not is_generic(it):
            continue
        img = hosted(it)
        if not img or not _live(img):
            skipped += 1; continue
        slug = space_runner.slugify(it)
        link = affiliate_links.affiliate_link(it, subid=slug)
        rows.append({
            "Title": title(it, idx)[:90],
            "Media URL": img,
            "Pinterest board": "Stiletto Finds",
            "Thumbnail": "",
            "Description": desc(it)[:480],
            "Link": link,
            "Publish date": "",
            "Keywords": "high heels, stilettos, heels, shoe finds, affordable heels, party shoes",
        })
        idx += 1
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:  # no BOM
        w = csv.DictWriter(f, fieldnames=["Title", "Media URL", "Pinterest board",
                                          "Thumbnail", "Description", "Link",
                                          "Publish date", "Keywords"])
        w.writeheader(); w.writerows(rows)
    print(f"OK {len(rows)} pins -> {OUT}  (skipped {skipped} dead-image rows)")

if __name__ == "__main__":
    main()
