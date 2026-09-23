# -*- coding: utf-8 -*-
"""
pinterest_csv.py — build a Pinterest Bulk-Create CSV from the approved catalog.

Trial API access can't post real pins, and Standard access needs review — so the
fast, free, product-agnostic path is Pinterest's native Bulk Create (Business →
Create → Bulk create): upload a CSV, Pinterest publishes real public pins.

Each produced heel (one with our own hosted image) becomes one pin row:
  Title       — deal hook ("These stilettos are only $X (Y% off)")
  Media URL   — our hosted image (thestilettovault Pages)
  Board       — target board
  Description — obsession/deal copy + hashtags
  Link        — affiliate deeplink with subid=slug (per-shoe attribution)
  Keywords    — SEO terms for Pinterest search

Reusable: swap the catalog + board and it builds a CSV for any affiliate niche.

Usage:
    py -3 pinterest_csv.py                 # -> dashboard/pinterest_bulk.csv
    py -3 pinterest_csv.py --board "X"     # target board name
    py -3 pinterest_csv.py --limit 50
"""
import sys, os, csv, json, argparse
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8") if sys.stdout else None
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import space_runner, affiliate_links

ROOT    = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "approved_catalog.json"
OUT     = ROOT / "dashboard" / "pinterest_bulk.csv"
SITE    = "https://thestilettovault.github.io"


def hosted_image(it):
    """OUR hosted image for this heel (never an AliExpress scrape)."""
    a = it.get("assets", {}) or {}
    for v in [a.get("image_1x1")] + (a.get("images_ig") or []) + [it.get("image_url", "")]:
        if v and SITE.split("//")[1] in v:
            return v
    return None


def deal_title(deal):
    sale = deal.get("sale"); disc = str(deal.get("discount", "") or "").strip()
    if sale and disc and disc not in ("0%", "0"):
        return f"These stilettos are only ${sale} \U0001f92f ({disc} off)"
    if sale:
        return f"Stiletto heels — ${sale} \U0001f5a4"
    return "Stiletto heels worth obsessing over \U0001f5a4"


def deal_desc(deal):
    sale = deal.get("sale"); was = deal.get("was"); disc = str(deal.get("discount", "") or "").strip()
    head = "Obsessed."
    if sale and was and disc:
        head = f"Obsessed. ${sale} instead of ${was} — {disc} off."
    elif sale:
        head = f"Obsessed. Just ${sale}."
    return (f"{head} The stiletto that looks way more expensive than it is. "
            f"Tap to grab yours before it sells out \U0001f5a4 "
            f"#heels #stilettos #shoefinds #affordablefashion #heelsaddict")


def main(board, limit):
    catalog = json.load(open(CATALOG, encoding="utf-8-sig"))
    rows = []
    for it in catalog:
        img = hosted_image(it)
        if not img:
            continue
        slug = space_runner.slugify(it)
        link = affiliate_links.affiliate_link(it, subid=slug)
        deal = it.get("deal", {}) or {}
        rows.append({
            "Title": deal_title(deal),
            "Media URL": img,
            "Board": board,
            "Description": deal_desc(deal),
            "Link": link,
            "Keywords": "high heels, stilettos, heels, shoe finds, affordable heels, party shoes",
        })
        if len(rows) >= limit:
            break
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["Title", "Media URL", "Board", "Description", "Link", "Keywords"])
        w.writeheader(); w.writerows(rows)
    print(f"✅ {len(rows)} pins -> {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="Stiletto Finds")
    ap.add_argument("--limit", type=int, default=200)
    a = ap.parse_args()
    main(a.board, a.limit)
