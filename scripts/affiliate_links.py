# -*- coding: utf-8 -*-
"""
affiliate_links.py — turn a raw product URL into the right affiliate link.

Amazon links already carry our tag (?tag=thegothicvaul-20) in the catalog, so
those pass through untouched. AliExpress links are wrapped through our Admitad
deeplink (joined 2026-08-12, ad space "Stiletto Vault Website" 2984135):

    https://rzekl.com/g/1e8d1144949a9d9ab95916525dc3e8/?ulp=<url-encoded target>

The wrapper token is per-account/program/ad-space; override via env
ALIEXPRESS_DEEPLINK_BASE if it ever changes.
"""
import os, urllib.parse

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except Exception:
    pass

ALIEXPRESS_DEEPLINK_BASE = os.getenv(
    "ALIEXPRESS_DEEPLINK_BASE",
    "https://rzekl.com/g/1e8d1144949a9d9ab95916525dc3e8/",
).rstrip("/") + "/"

AMAZON_TAG = os.getenv("AMAZON_TAG", "thegothicvaul-20")

# ── Awin (higher-commission brand merchants; also the network Public Desire runs
# on, and ShareASale's successor after Awin absorbed it in 2025) ───────────────
# One publisher id for the account; each approved MERCHANT has its own numeric
# awinmid. Fill both via env once the Awin account + merchant approvals land:
#   AWIN_PUBLISHER_ID=123456
#   AWIN_MERCHANTS=publicdesire.com:9999,asos.com:8888   (domain:awinmid, comma-sep)
# Until AWIN_PUBLISHER_ID is set, nothing routes to Awin — the config is inert.
AWIN_PUBLISHER_ID = os.getenv("AWIN_PUBLISHER_ID", "").strip()


def _awin_merchants():
    """Parse AWIN_MERCHANTS ('domain:mid,domain:mid') into {domain: awinmid}."""
    out = {}
    for pair in os.getenv("AWIN_MERCHANTS", "").split(","):
        pair = pair.strip()
        if ":" in pair:
            dom, mid = pair.rsplit(":", 1)
            dom, mid = dom.strip().lower(), mid.strip()
            if dom and mid:
                out[dom] = mid
    return out


def awin(url, merchant_id, subid=""):
    """Standard Awin deeplink. clickref carries our per-shoe subid (== slug) so a
    sale is attributable to THIS heel, exactly like the Admitad subid flow."""
    q = {"awinmid": merchant_id, "awinaffid": AWIN_PUBLISHER_ID,
         "ued": url}
    if subid:
        q["clickref"] = subid
    return "https://www.awin1.com/cread.php?" + urllib.parse.urlencode(q)


def _awin_for(url, domain, subid=""):
    """Return an Awin link if this domain is an approved Awin merchant AND we have
    a publisher id; else None (caller falls back to the next program)."""
    if not AWIN_PUBLISHER_ID:
        return None
    for dom, mid in _awin_merchants().items():
        if dom in domain or dom in url:
            return awin(url, mid, subid)
    return None


def aliexpress(url, subid=""):
    """Wrap an AliExpress product/category URL in our Admitad deeplink."""
    q = "?ulp=" + urllib.parse.quote(url, safe="")
    if subid:
        q = f"?subid={urllib.parse.quote(subid)}&ulp=" + urllib.parse.quote(url, safe="")
    return ALIEXPRESS_DEEPLINK_BASE + q


def amazon(url):
    """Ensure an Amazon URL carries our associate tag."""
    parts = urllib.parse.urlparse(url)
    qs = dict(urllib.parse.parse_qsl(parts.query))
    qs["tag"] = AMAZON_TAG
    return urllib.parse.urlunparse(parts._replace(query=urllib.parse.urlencode(qs)))


def affiliate_link(item, subid=""):
    """Best affiliate link for a catalog item, chosen by domain.
    Falls back to any pre-set aff_link, then the raw url."""
    url = item.get("url", "") or item.get("aff_link", "")
    domain = (item.get("domain", "") or url).lower()
    # Awin first — it holds the high-commission brand merchants (incl. Public
    # Desire). Only fires when AWIN_PUBLISHER_ID is set and the domain is approved.
    awin_link = _awin_for(url, domain, subid)
    if awin_link:
        return awin_link
    if "aliexpress." in domain:
        return aliexpress(url, subid)
    if "amazon." in domain:
        return item.get("aff_link") or amazon(url)
    return item.get("aff_link") or url


if __name__ == "__main__":
    demo = {"url": "https://www.aliexpress.com/item/1005001749588706.html",
            "domain": "aliexpress.com"}
    print("AliExpress →", affiliate_link(demo))
    print("Amazon     →", affiliate_link(
        {"url": "https://www.amazon.com/dp/B0F7LSL3G1", "domain": "amazon.com"}))
