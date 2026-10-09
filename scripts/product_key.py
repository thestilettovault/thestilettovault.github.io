"""One identity per shoe, so the same product never appears twice.

Two catalog entries are the same shoe when their URLs differ only by www.,
http/https, query string (tracking/ref params), fragment or trailing slash
(2026-10-09: Hallie appeared twice as publicdesire.com and www.publicdesire.com).
AliExpress listings are keyed by their numeric item id.
"""
import re
from urllib.parse import urlparse


def product_key(url):
    url = (url or "").strip()
    if not url:
        return ""
    m = re.search(r"aliexpress\.[a-z.]+/item/(\d+)", url, re.I) or \
        re.search(r"item%2F(\d+)", url, re.I)
    if m:
        return "aliexpress:" + m.group(1)
    p = urlparse(url if "://" in url else "https://" + url)
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host + p.path.rstrip("/").lower()


def dedupe(items, url_of=lambda it: it.get("url") or it.get("aff_link")):
    """Keep the first occurrence of each shoe; return (kept, dropped)."""
    seen, kept, dropped = set(), [], []
    for it in items:
        k = product_key(url_of(it))
        if k and k in seen:
            dropped.append(it)
            continue
        seen.add(k)
        kept.append(it)
    return kept, dropped
