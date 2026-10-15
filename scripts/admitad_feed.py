# -*- coding: utf-8 -*-
"""
admitad_feed.py — turn the Admitad AliExpress product feed (CSV) into a pool of
VALID high-heel products for the morning scout.

The feed URL is generated in the panel (Product Feeds > AliExpress WW) and stored
in scripts/.env as ADMITAD_FEED_URL. Each row already carries the ready affiliate
deeplink in its `url` column, so no wrapping is needed.

CSV columns: id;name;url;category;currencyId;param;picture;oldprice;price

Usage:
    py -3 admitad_feed.py            # download + filter, print how many heels found
    py -3 admitad_feed.py --write    # also write them into data/aliexpress_pool.json
    py -3 admitad_feed.py --file X   # parse an already-downloaded CSV instead
"""
import os, sys, csv, json, argparse, urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8") if sys.stdout else None
sys.path.insert(0, os.path.dirname(__file__))
from product_scout import is_high_heel, is_excluded
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except Exception:
    pass

DATA = Path(__file__).resolve().parent.parent / "data"
POOL = DATA / "aliexpress_pool.json"
FEED_URL = os.getenv("ADMITAD_FEED_URL", "")

# The feed is the WHOLE AliExpress catalog (259k rows, every category), so the gate
# must be strict: an explicit heel word AND none of the disqualifiers.
SHOE_CAT   = ("shoe", "women", "pumps", "heels", "boots", "sandal", "footwear")
HEEL_WORDS = ("stiletto", "high heel", "high-heel", "highheel", "pump", "pointed toe",
              "pointed-toe", "platform heel", "heeled", "court shoe", "kitten heel",
              "ankle boot", "knee high", "knee-high", "thigh high", "thigh-high",
              "over the knee", "over-the-knee", "slingback")
BAD_WORDS  = ("kid", "child", "girl", "boy", "baby", "toddler", "infant", "junior",
              "rain boot", "snow boot", "sneaker", "trainer", "slipper", "flat ",
              "flats", "loafer", "men's", "mens ", "man ", "male", "sport", "running",
              "hiking", "work boot", "safety", "orthopedic", "slides", "flip flop",
              "crocs", "moccasin", "espadrille", "wedge sneaker", "insole", "shoe rack",
              "sock", "lace set", "cover", "cleaner", "keychain")
csv.field_size_limit(10_000_000)


def _is_gothic_heel(name):
    n = name.lower()
    if any(b in n for b in BAD_WORDS):
        return False
    if not any(h in n for h in HEEL_WORDS):
        return False
    return True


def _rows(path):
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            yield r


def filter_heels(path, limit=400):
    found = []
    for r in _rows(path):
        name = (r.get("name") or "").strip()
        cat = (r.get("category") or "").lower()
        if not name:
            continue
        # must look like footwear AND pass the high-heel gate
        if not any(s in cat for s in SHOE_CAT):
            continue
        if not _is_gothic_heel(name):
            continue
        pid = (r.get("id") or "").strip()
        found.append({
            "title":   name[:90],
            "url":     f"https://www.aliexpress.com/item/{pid}.html",
            "aff_link": (r.get("url") or "").strip(),      # ready Admitad deeplink
            "image_url": (r.get("picture") or "").strip(),
            "price":   (r.get("price") or "").strip(),
            "commission": "6.9%",
            "domain":  "aliexpress.com",
        })
        if len(found) >= limit:
            break
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write results into the pool")
    ap.add_argument("--file", help="parse a local CSV instead of downloading")
    ap.add_argument("--limit", type=int, default=400)
    a = ap.parse_args()

    path = a.file
    if not path:
        if not FEED_URL:
            print("! ADMITAD_FEED_URL not set in .env"); sys.exit(1)
        path = str(DATA / "_ae_feed.csv")
        print("downloading feed…")
        urllib.request.urlretrieve(FEED_URL, path)
    heels = filter_heels(path, a.limit)
    print(f"high-heel products found: {len(heels)}")
    for h in heels[:8]:
        print(f"  ${h['price']:>6}  {h['title'][:55]}")
    if a.write:
        POOL.write_text(json.dumps(
            {"_note": "Auto-filled from Admitad AliExpress feed. Ready deeplinks in aff_link.",
             "products": heels}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {len(heels)} products → {POOL}")


if __name__ == "__main__":
    main()
