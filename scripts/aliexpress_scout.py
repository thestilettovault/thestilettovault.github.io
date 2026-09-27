# -*- coding: utf-8 -*-
"""
aliexpress_scout.py — FREE AliExpress high-heel sourcing (no API, no cost).

Fetches AliExpress search-result pages, extracts the embedded product list
(itemList.content JSON), keeps the real high heels, and writes them into the
morning-bot pool with a ready Admitad deeplink (6.9%).

Region/currency/language are forced to US/USD/English via cookie so titles are
English (the heel filter + captions need it) and prices are USD.

Usage:
    py -3 aliexpress_scout.py            # scan default heel searches, print
    py -3 aliexpress_scout.py --write    # also write into data/aliexpress_pool.json
"""
import os, sys, re, json, argparse, subprocess
from pathlib import Path

# headless-safe (pythonw scheduled task has no console)
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))
import affiliate_links

DATA = Path(__file__).resolve().parent.parent / "data"
POOL = DATA / "aliexpress_pool.json"

# Each entry: (search term, clean English category label for the product title).
# The search term guarantees the result is that kind of heel, so we don't need to
# read the (geo-localised) title — the label is a clean English category, and Ofer
# approves each product by its IMAGE in Telegram.
SEARCHES = [
    ("stiletto heels",        "Stiletto Heels"),
    ("pointed toe pumps",     "Pointed-Toe Pump"),
    ("platform high heels",   "Platform High Heels"),
    ("ankle boots heels",     "Heeled Ankle Boots"),
    ("slingback heels",       "Slingback Heels"),
    ("knee high heel boots",  "Knee-High Heel Boots"),
    ("thigh high heel boots", "Thigh-High Heel Boots"),
    ("high heel sandals",     "High-Heel Sandals"),
]
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120 Safari/537.36")


def _fetch(term):
    # curl passes AliExpress' TLS bot-check where python requests/urllib get punished.
    # AliExpress still rate-limits by IP, so keep volume low and space requests out.
    slug = term.strip().replace(" ", "-")
    # SortType=total_tranpro_desc = best-sellers first → proven converters surface
    url = f"https://www.aliexpress.com/w/wholesale-{slug}.html?g=y&SortType=total_tranpro_desc"
    # Force US region / USD / English so prices come back as $ and sold-counts as
    # English ("286 sold"), not the IP-geo default (₪ / "נמכרו"). AliExpress reads
    # region+currency+locale from the aep_usuc_f cookie.
    r = subprocess.run(["curl", "-s", "-A", _UA,
                        "-H", "Accept-Language: en-US,en;q=0.9",
                        "-b", "aep_usuc_f=site=glo&c_tp=USD&region=US&b_locale=en_US",
                        "--max-time", "40", url], capture_output=True, timeout=60)
    html = r.stdout.decode("utf-8", "replace")
    if "punish" in html.lower() or '"itemList":' not in html:
        raise RuntimeError("rate-limited (punish) — IP needs to cool down")
    return html


def _items(html):
    i = html.find('"itemList":')
    if i < 0:
        return []
    s = html.find("{", i); depth = 0; end = s
    for j in range(s, len(html)):
        if html[j] == "{": depth += 1
        elif html[j] == "}":
            depth -= 1
            if depth == 0:
                end = j + 1; break
    try:
        return json.loads(html[s:end]).get("content", [])
    except Exception:
        return []


def _title(it):
    return ((it.get("title") or {}).get("displayTitle") or "").strip()


def _num(p):
    return (p or {}).get("minPrice") or (p or {}).get("value") or ""

def _price(it):
    pr = it.get("prices") or {}
    return _num(pr.get("salePrice")) or _num(pr.get("originalPrice")) or ""

def _deal(it):
    """Sales hooks for smart videos: sale price, was-price, discount %, rating, sold."""
    pr = it.get("prices") or {}
    sale = _num(pr.get("salePrice")); orig = _num(pr.get("originalPrice"))
    disc = ""
    try:
        if sale and orig and float(orig) > float(sale):
            disc = f"{round((1 - float(sale) / float(orig)) * 100)}%"
    except Exception:
        pass
    ev = it.get("evaluation") or it.get("trade") or {}
    rating = ev.get("starRating") or ev.get("star") or ev.get("rating") or ""
    sold = (it.get("trade") or {}).get("tradeDesc") or ev.get("tradeDesc") \
        or ev.get("sold") or ""
    return {"sale": sale, "was": orig, "discount": disc,
            "rating": str(rating), "sold": str(sold)}


# Proven-converter gate (2026-09-27): 64 Admitad clicks → 0 sales on heels with
# "1-4 sold". Buyers on AliExpress decide by social proof, so only keep heels that
# already sell. Commission is ~6.9% of price, so a price floor lifts $/sale too.
MIN_SOLD = 300
MIN_RATING = 4.6
MIN_PRICE = 20.0


def _sold_n(txt):
    m = re.search(r"([\d,.]+)\s*(k)?\+?", str(txt or "").lower())
    if not m:
        return 0
    n = float(m.group(1).replace(",", ""))
    return int(n * 1000) if m.group(2) else int(n)


def _proven(deal, price):
    """(ok, reason). Missing sold/rating = unproven → rejected (don't guess)."""
    sold, rating = _sold_n(deal.get("sold")), deal.get("rating") or ""
    try:
        rating = float(rating)
    except ValueError:
        rating = 0.0
    try:
        price = float(price or 0)
    except ValueError:
        price = 0.0
    if sold < MIN_SOLD:
        return False, f"sold {sold}<{MIN_SOLD}"
    if rating < MIN_RATING:
        return False, f"rating {rating}<{MIN_RATING}"
    if price < MIN_PRICE:
        return False, f"price ${price}<${MIN_PRICE}"
    return True, ""


def scout(write=False, per_term=8):
    """Grab up to `per_term` heels from each search (variety over volume)."""
    import time, random
    seen, found, skipped = set(), [], {}
    for term, label in SEARCHES:
        try:
            items = _items(_fetch(term))
        except Exception as e:
            print(f"  {term}: {e}"); time.sleep(2); continue
        time.sleep(random.uniform(3, 6))            # gentle — avoid the IP rate-limit
        kept = 0
        for it in items:
            if kept >= per_term:
                break
            pid = it.get("productId") or it.get("redirectedId")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            deal = _deal(it)
            ok, why = _proven(deal, _price(it))
            if not ok:
                skipped[why.split()[0]] = skipped.get(why.split()[0], 0) + 1
                continue
            img = (it.get("image") or {}).get("imgUrl", "")
            if img.startswith("//"): img = "https:" + img
            url = f"https://www.aliexpress.com/item/{pid}.html"
            found.append({
                "title": label,                                # clean English category
                "url": url,
                "aff_link": affiliate_links.aliexpress(url),   # Admitad deeplink 6.9%
                "image_url": img,
                "price": _price(it),
                "deal": deal,                                  # sale/was/discount/rating/sold
                "commission": "6.9%",
                "domain": "aliexpress.com",
            })
            kept += 1
        print(f"  '{term}': {len(items)} scanned → {kept} added")
    print(f"\nTOTAL proven high heels: {len(found)}  (rejected: {skipped})")
    for h in found[:8]:
        print(f"  ${h['price']}  {h['title'][:55]}")
    if write:
        POOL.write_text(json.dumps(
            {"_note": "Auto-filled from AliExpress search scrape (free). Admitad deeplinks in aff_link.",
             "products": found}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {len(found)} products → {POOL}")
    return found


if __name__ == "__main__":
    import urllib.parse
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    scout(write=a.write)
