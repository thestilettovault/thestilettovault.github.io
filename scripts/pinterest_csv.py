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


def deal_title(it, deal):
    """A UNIQUE, natural pin title. Pinterest bulk-create rejects duplicate
    titles, so we lead with the product's own name (distinct per shoe) and add
    the deal when there is one."""
    sale = deal.get("sale"); disc = str(deal.get("discount", "") or "").strip()
    name = short_name((it.get("title") or "Stiletto heels").strip(), 55)
    if sale and disc and disc not in ("0%", "0"):
        return f"{name} — only ${sale} \U0001f92f ({disc} off)"
    if sale:
        return f"{name} — ${sale} \U0001f5a4"
    return f"{name} \U0001f5a4"


def short_name(t, n):
    t = (t or "").strip()
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


VIBE = ["black", "glossy", "pointed-toe", "strappy", "classic", "party-ready",
        "sleek", "bold", "chic", "statement", "everyday", "date-night",
        "must-have", "editor's pick", "new-in", "trending", "sold-out-soon",
        "closet staple", "the one"]


def unique(title, seen):
    """Guarantee title uniqueness (Pinterest requirement) with a natural suffix."""
    if title not in seen:
        seen.add(title); return title
    for w in VIBE:
        c = f"{title} · {w}"
        if c not in seen:
            seen.add(c); return c
    i = 2
    while f"{title} ({i})" in seen:
        i += 1
    c = f"{title} ({i})"; seen.add(c); return c


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


def _live(url):
    """True only if the image URL actually serves (HTTP 200) — skips phantom
    catalog entries whose image was never pushed, which Pinterest rejects."""
    import urllib.request
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception:
        return False


def main(board, limit, remaining=False, out=None):
    catalog = json.load(open(CATALOG, encoding="utf-8-sig"))
    rows = []
    skipped = 0
    seen = set()
    for it in catalog:
        img = hosted_image(it)
        if not img:
            continue
        # `remaining`: only the no-deal rows (the ones the first bulk upload
        # rejected for duplicate generic titles) — avoids re-pinning the ~27
        # unique-deal rows that already published.
        if remaining and (it.get("deal", {}) or {}).get("sale"):
            continue
        if not _live(img):                       # drop dead/phantom images
            skipped += 1; continue
        slug = space_runner.slugify(it)
        link = affiliate_links.affiliate_link(it, subid=slug)
        deal = it.get("deal", {}) or {}
        rows.append({
            "Title": unique(deal_title(it, deal)[:90], seen),   # unique per Pinterest
            "Media URL": img,
            "Pinterest board": board,
            "Thumbnail": "",
            "Description": deal_desc(deal)[:480],
            "Link": link,
            "Publish date": "",
            "Keywords": "high heels, stilettos, heels, shoe finds, affordable heels, party shoes",
        })
        if len(rows) >= limit:
            break
    OUT.parent.mkdir(exist_ok=True)
    dest = Path(out) if out else OUT
    # Exact Pinterest bulk-create template headers (order + casing matter).
    with open(dest, "w", newline="", encoding="utf-8") as f:   # no BOM — Pinterest reads the raw header
        w = csv.DictWriter(f, fieldnames=["Title", "Media URL", "Pinterest board",
                                          "Thumbnail", "Description", "Link",
                                          "Publish date", "Keywords"])
        w.writeheader(); w.writerows(rows)
    print(f"✅ {len(rows)} pins -> {dest}  (skipped {skipped} dead-image rows)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="Stiletto Finds")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--remaining", action="store_true",
                    help="only the no-deal rows that failed the first upload (dup titles)")
    ap.add_argument("--out", help="output CSV path")
    a = ap.parse_args()
    main(a.board, a.limit, a.remaining, a.out)
