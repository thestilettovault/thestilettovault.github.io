"""
Product Scout — The Stiletto Vault
Scrapes high-heel products from affiliate Shopify stores (scout_shopify).
Returns a list of products — caller (daily_heel_scout) decides what to do with them.
The heel gate itself lives in heel_filter.py (shared with aliexpress_scout).
"""

import requests
import time
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

# Re-exported: admitad_feed / daily_heel_scout import these names from here.
from heel_filter import (is_excluded, is_high_heel, passes, EXCLUDE_KEYWORDS,  # noqa: F401
                         HEEL_POSITIVE, AMBIGUOUS_FOOTWEAR, NONHEEL_EXCLUDE)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

# ── Shopify Sites (verified: /collections/*/products.json API works) ──
# Collections are heel/shoe-first for the heels niche. Registered & approved
# affiliates (killstar, darkinlove) lead; tukshoes carries platforms.
SHOPIFY_SOURCES = [
    # ── Designer / mainstream HIGH-HEEL shops (Shopify, live products.json) ──
    # The channel is statement HIGH HEELS, not only gothic. These are the deep,
    # on-brand pool (166+ heels combined). Links surface & post now; Awin tracking
    # gets added to `our_id` once the Awin publisher account is approved.
    {
        "domain": "caperobbin.com",
        "collections": ["heels", "boots", "new-arrivals", "sandals", "pumps"],
        "affiliate": {"commission": "TBD", "program": "Awin", "our_id": None},
        "max_per_collection": 12,
    },
    {
        "domain": "www.publicdesire.com",
        "collections": ["heels", "boots", "new-in", "sandals"],
        "affiliate": {"commission": "8%", "program": "Awin", "our_id": None},
        "max_per_collection": 12,
    },
    {
        "domain": "www.simmi.com",
        "collections": ["heels", "boots", "new-in", "sandals"],
        "affiliate": {"commission": "6%", "program": "Awin", "our_id": None},
        "max_per_collection": 12,
    },
    {
        "domain": "nakedwolfe.com",
        "collections": ["heels", "boots", "new", "all"],
        "affiliate": {"commission": "10%", "program": "Direct", "our_id": None},
        "max_per_collection": 12,
    },
    # ── High-heel gothic/alt expansion (verified Shopify feeds 2026-08-23) ─
    {
        "domain": "koifootwear.com",   # Monster High / platform coffin heels — strongest on-brand
        "collections": ["heels", "platform-heels", "boots", "new-in", "high-heels"],
        "affiliate": {"commission": "TBD", "program": "Awin", "our_id": None},
        "max_per_collection": 12,
    },
    {
        "domain": "www.lamoda.co.uk",  # alt platform heels — "Love Sick / Goodbye Forever"
        "collections": ["heels", "platform-heels", "boots", "new-in"],
        "affiliate": {"commission": "TBD", "program": "Awin", "our_id": None},
        "max_per_collection": 12,
    },
    {
        "domain": "yrushoes.com",       # Draculaura / DEELITE alt platforms
        "collections": ["heels", "platforms", "boots", "new-arrivals", "all"],
        "affiliate": {"commission": "TBD", "program": "Refersion", "our_id": None},
        "max_per_collection": 10,
    },
    # ── Registered affiliate ──────────────────────────────────────────
    {
        "domain": "www.killstar.com",
        "collections": ["shoes", "boots", "heels", "platforms", "new-arrivals"],
        "affiliate": {"commission": "10%", "program": "ShareASale", "our_id": None},
        "max_per_collection": 12,
    },
    {
        "domain": "www.darkinlove.com",
        "collections": ["shoes", "boots", "high-heels", "heels"],
        "affiliate": {"commission": "10%", "program": "UpPromote",
                      "our_id": "ll249558.3UXnWnByxo"},
        "max_per_collection": 5,
        "affiliate_ref": "?sca_ref=ll249558.3UXnWnByxo",
    },
    {
        "domain": "tukshoes.co.uk",
        "collections": ["heels", "platforms", "boots", "sandals", "shoes",
                        "new-in", "womens"],
        "affiliate": {"commission": "TBD", "program": "TradeTracker", "our_id": None},
        "max_per_collection": 10,
    },
]

# ── Shopify JSON scraper ──────────────────────────────────────────────
def scout_shopify(source):
    """Scrape products from a Shopify store via /collections/*/products.json."""
    domain = source["domain"]
    affiliate = source["affiliate"]
    found = []

    # An EARNING brand (source["full_catalog"]) is read whole: /products.json, every
    # page. Collections cap at the first page - Naked Wolfe showed 14 of its 63 in-stock
    # heels that way (2026-10-16). Other stores keep the lighter per-collection scan.
    if source.get("full_catalog"):
        pages = [f"https://{domain}/products.json?limit=250&page={n}" for n in range(1, 9)]
        cap = 10_000
    else:
        pages = [f"https://{domain}/collections/{c}/products.json?limit=50" for c in source["collections"]]
        cap = source["max_per_collection"]
    seen_handles = set()

    for url in pages:
        collection = url.split("/collections/")[-1].split("/")[0] if "/collections/" in url else "all"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if not r.ok:
                continue
            products = r.json().get("products", [])
            if not products and source.get("full_catalog"):
                break                                   # past the last page

            count = 0
            for p in products:
                if count >= cap:
                    break
                if p.get("handle") in seen_handles:
                    continue

                title = p.get("title", "")
                tags  = p.get("tags", [])

                if is_excluded(title):
                    continue
                # Channel = high heels (every height/style). One clean gate.
                if not is_high_heel(title, tags):
                    continue

                handle = p.get("handle", "")
                images = p.get("images", [])
                if not images or not handle:
                    continue

                image_url = images[0].get("src", "")
                if not image_url:
                    continue

                # Price from the first AVAILABLE variant; sold-out products are skipped.
                variants = [v for v in (p.get("variants") or []) if v.get("available", True)]
                if not variants:
                    continue
                price = variants[0].get("price", "?")

                ref = source.get("affiliate_ref", "")
                product_url = f"https://{domain}/products/{handle}"
                tracked_url = product_url + ref if ref else product_url

                seen_handles.add(handle)
                found.append({
                    "title":     title,
                    "url":       tracked_url,
                    "image":     image_url,
                    "price":     price,
                    "affiliate": affiliate,
                    "domain":    domain,
                })
                count += 1

            time.sleep(0.5)
        except Exception as e:
            print(f"    {domain}/{collection}: {e}")

    return found
