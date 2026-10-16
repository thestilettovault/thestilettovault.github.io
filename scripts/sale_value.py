"""
sale_value.py: expected commission per sale (USD) for a product, so the scout and
the producer can put the shoes that actually pay first.

  value = price x commission%      (AliExpress $18 x 6.9% = $1.24; Naked Wolfe $300 x 10% = $30)

Price comes from the product (Shopify price / AliExpress deal sale). When it is
missing (brand entries in the production queue carry no deal), fall back to the
affiliate registry's `value_per_sale` for that domain (heel_hunter computes it from
the store's average heel price).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data" / "affiliate_registry.json"

# commission used when the item carries none (domain suffix -> percent)
DEFAULT_PCT = {"aliexpress.com": 6.9, "amazon.com": 4.0}
AMAZON_EST_PRICE = 45.0      # Amazon pool carries no price; typical heel price there


def _domain(d):
    d = (d or "").lower().strip()
    return d[4:] if d.startswith("www.") else d


def commission_pct(commission, domain=""):
    """'6.9%' -> 6.9; '' / 'TBD' -> the domain default or 0."""
    m = re.search(r"(\d+(?:\.\d+)?)", str(commission or ""))
    if m:
        return float(m.group(1))
    dom = _domain(domain)
    return next((v for k, v in DEFAULT_PCT.items() if dom.endswith(k)), 0.0)


def _price(x):
    try:
        return float(str(x).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _registry_value(domain):
    try:
        import jsonio
        brands = jsonio.load(REGISTRY, {}).get("brands", {})
    except Exception:
        return None
    e = brands.get(_domain(domain)) or {}
    v = e.get("value_per_sale")
    return float(v) if isinstance(v, (int, float)) and v > 0 else None


def value_per_sale(domain="", price=None, commission=""):
    """Expected USD commission for one sale. 0.0 when it cannot be estimated."""
    dom = _domain(domain)
    pct = commission_pct(commission, dom)
    p = _price(price)
    if p is None and dom.endswith("amazon.com"):
        p = AMAZON_EST_PRICE
    if p is not None and pct:
        return round(p * pct / 100.0, 2)
    reg = _registry_value(dom)
    return round(reg, 2) if reg else 0.0


def value_of_entry(entry):
    """value_per_sale for a catalog / production-queue entry (url, deal, commission)."""
    url = entry.get("url") or ""
    m = re.search(r"https?://([^/?#]+)", url)
    dom = entry.get("domain") or (m.group(1) if m else "")
    deal = entry.get("deal") or {}
    price = deal.get("sale") or entry.get("price")
    return value_per_sale(dom, price, entry.get("commission", ""))
