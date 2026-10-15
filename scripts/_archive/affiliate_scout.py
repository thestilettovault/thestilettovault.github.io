# -*- coding: utf-8 -*-
"""
Affiliate Scout -- TheGothicVault
Runs every morning. Searches for new gothic/fetish/alternative affiliate programs
that are not yet in our known list. Outputs actionable findings.

Usage:
    python affiliate_scout.py
"""

import sys
import os
import json
import time
import requests
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from gothic_scout import KNOWN_AFFILIATE_PROGRAMS, DATA_DIR

FINDINGS_FILE = os.path.join(DATA_DIR, "new_affiliate_findings.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ── Awin Public Merchant Search ───────────────────────────────────────
# Awin's public advertiser search (no auth needed for basic search)
AWIN_SEARCH_TERMS = [
    "gothic", "fetish", "alternative", "goth", "punk",
    "latex", "corset", "costume", "dark", "occult"
]

def search_awin_merchants():
    """Search Awin public advertiser directory for gothic-relevant merchants."""
    found = []
    known_domains = set(KNOWN_AFFILIATE_PROGRAMS.keys())

    for term in AWIN_SEARCH_TERMS:
        try:
            url = f"https://ui.awin.com/awin/api/2.0/programmes"
            params = {
                "accessToken": "",   # public search, no token needed for basic
                "searchTerm": term,
                "countryCode": "US",
                "relationship": "notjoined",
                "pageSize": 20
            }
            r = requests.get(url, params=params, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                data = r.json()
                for prog in data.get("programmes", []):
                    domain = (prog.get("primaryRegion", {}).get("country") or "").lower()
                    name   = prog.get("programName", "")
                    prog_url = prog.get("displayUrl", "")
                    commission = prog.get("commissionRange", {}).get("min", "TBD")

                    if prog_url and not any(d in prog_url for d in known_domains):
                        found.append({
                            "source": "Awin",
                            "name": name,
                            "url": prog_url,
                            "commission": f"{commission}%",
                            "term": term
                        })
        except Exception as e:
            pass  # Awin may block unauthenticated requests
        time.sleep(0.5)

    return found


# ── Shopify Affiliate Directory Scan ─────────────────────────────────
# Search for Shopify stores in gothic/fetish niche with /pages/affiliates

SHOPIFY_CANDIDATE_DOMAINS = [
    "blackcraft.com",
    "sourpuss.net",
    "current-mood.com",
    "foxblood.com",
    "witchcraftcouture.com",
    "blackmilkclothing.com",
    "iheartrave.com",
    "spikedandsexxy.com",
    "darlingminis.com",
    "deathwishcoffee.com",
    "skullandcakebones.com",
    "kreepsville666.com",
    "zockto.com",
    "twistedwickedthings.com",
    "deathbyaudio.com",
    "darkinlove.com",
    "attitude-clothing.com",
    "alternatewear.co.uk",
    "disturbia.co.uk",
    "darksouls.co.uk",
    "phaze.com",
    "nightshadeapparel.com",
    "hell-bunny.com",
    "heartofgold.store",
    "blackvelvet.co.uk",
    "jawbreaker.co.uk",
    "sinisterclothing.com",
    "gothicplus.com",
    "pyramidcollection.com",
    "spencers.com",
    "hot-topic.com",
    "torrid.com",
]

AFFILIATE_PATHS = [
    "/pages/affiliates",
    "/pages/affiliate",
    "/pages/affiliate-program",
    "/pages/become-an-affiliate",
    "/affiliate",
    "/affiliates",
]

def check_shopify_affiliate(domain):
    """Check if a Shopify store has an affiliate program page."""
    for path in AFFILIATE_PATHS:
        url = f"https://{domain}{path}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
            if r.status_code == 200 and len(r.text) > 500:
                # Basic check: page exists and has content
                text_lower = r.text.lower()
                if any(kw in text_lower for kw in ["affiliate", "commission", "earn", "referral", "partner"]):
                    return url
        except Exception:
            pass
    return None


# ── Main Scout ────────────────────────────────────────────────────────
def run_affiliate_scout():
    print("\n" + "="*60)
    print(f"Affiliate Scout -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)

    known_domains = set(KNOWN_AFFILIATE_PROGRAMS.keys())
    findings = []

    # 1. Check candidate Shopify stores
    print(f"\nChecking {len(SHOPIFY_CANDIDATE_DOMAINS)} gothic/alt stores for affiliate pages...")
    for domain in SHOPIFY_CANDIDATE_DOMAINS:
        if any(d in domain for d in known_domains):
            continue  # already known
        aff_url = check_shopify_affiliate(domain)
        if aff_url:
            print(f"  [NEW] {domain} -> {aff_url}")
            findings.append({
                "domain": domain,
                "affiliate_page": aff_url,
                "source": "Shopify scan",
                "date": datetime.now().isoformat()
            })
        else:
            print(f"  [ ]  {domain}")
        time.sleep(0.3)

    # 2. Awin search (may need auth — logs if blocked)
    print(f"\nSearching Awin for new gothic merchants...")
    awin_results = search_awin_merchants()
    for r in awin_results:
        print(f"  [AWIN] {r['name']} -- {r['url']} ({r['commission']})")
        findings.append({
            "domain": r["url"],
            "affiliate_page": f"https://ui.awin.com (search: {r['term']})",
            "commission": r["commission"],
            "source": "Awin",
            "date": datetime.now().isoformat()
        })

    # 3. Save findings
    existing = []
    if os.path.exists(FINDINGS_FILE):
        with open(FINDINGS_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)

    # Deduplicate by domain
    known_found = {e["domain"] for e in existing}
    new_findings = [f for f in findings if f["domain"] not in known_found]

    existing.extend(new_findings)
    with open(FINDINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"RESULTS: {len(new_findings)} new affiliate programs found today")
    if new_findings:
        print("\nACTION REQUIRED -- New programs to investigate:")
        for f in new_findings:
            print(f"  -> {f['domain']}")
            print(f"     {f['affiliate_page']}")
    else:
        print("No new programs found today.")
    print(f"\nAll findings saved to: {FINDINGS_FILE}")
    print("="*60)

    return new_findings


if __name__ == "__main__":
    run_affiliate_scout()
