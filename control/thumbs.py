# -*- coding: utf-8 -*-
"""thumbs.py — find a picture for any product (Control Center /api/thumb).

Order: local GELEM folder (post_image / ad_* / source / any image) → AliExpress pool
image by item id → og:image of the product page (cached in data/thumb_cache.json,
local only). Returns ("file", Path) | ("url", str) | (None, None).
"""
import ipaddress
import json
import re
import socket
import threading
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

from .atomic import write_json

ROOT = Path(__file__).resolve().parent.parent
GELEM = ROOT / "GELEM"
DATA = ROOT / "data"
CACHE = DATA / "thumb_cache.json"
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
PREFER = ("post_image", "ad_a", "ad_b", "ad_c", "ad_d", "source")
_LOCK = threading.Lock()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}


def thumb_url(url="", slug=""):
    return "/api/thumb?url=" + quote(url or "", safe="") + "&slug=" + quote(slug or "", safe="")


def _load():
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(c):
    try:
        write_json(CACHE, c, indent=1)
    except Exception:
        pass


def _best_image(folder):
    imgs = [p for p in folder.rglob("*") if p.suffix.lower() in IMG_EXT and "screenshot" not in p.name.lower()]
    if not imgs:
        return None
    def rank(p):
        n = p.stem.lower()
        for i, k in enumerate(PREFER):
            if n.startswith(k):
                return i
        return len(PREFER)
    return sorted(imgs, key=rank)[0]


_SLUG_RE = re.compile(r"^[\w .\-/]+$")


def valid_slug(slug) -> bool:
    if not isinstance(slug, str) or not slug or not _SLUG_RE.fullmatch(slug):
        return False
    parts = slug.split("/")
    return not any(p in ("", ".", "..") for p in parts) and not slug.startswith("/")


def _inside_gelem(p: Path) -> bool:
    try:
        return p.resolve().is_relative_to(GELEM.resolve())
    except Exception:
        return False


def is_public_http_url(url) -> bool:
    """http(s) only, and the host must not resolve to a private/loopback/link-local address."""
    try:
        parts = urlsplit(str(url))
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return False
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
        if not infos:
            return False
        for info in infos:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                    or ip.is_reserved or ip.is_unspecified):
                return False
        return True
    except Exception:
        return False


def local_image(slug):
    if not valid_slug(slug) or not GELEM.exists():
        return None
    for folder in [GELEM / slug] + list(GELEM.glob(f"*/{slug}")):
        if folder.is_dir() and _inside_gelem(folder):
            img = _best_image(folder)
            if img and _inside_gelem(img):
                return img
    return None


def _pool_image(url):
    m = re.search(r"/item/(\d+)", url or "")
    if not m:
        return None
    try:
        pool = json.loads((DATA / "aliexpress_pool.json").read_text(encoding="utf-8")).get("products", [])
    except Exception:
        return None
    for p in pool:
        if m.group(1) in (p.get("url") or "") and p.get("image_url"):
            return p["image_url"]
    return None


def _og_image(url):
    import requests
    try:
        cur = url
        r = None
        for _ in range(4):                      # follow redirects by hand: every hop must be public http(s)
            if not is_public_http_url(cur):
                return None
            r = requests.get(cur, headers=UA, timeout=8, allow_redirects=False)
            if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
                loc = r.headers.get("Location")
                if not loc:
                    return None
                cur = urljoin(cur, loc)
                r = None
                continue
            break
        if r is None:
            return None
        h = r.text[:400000]
    except Exception:
        return None
    for rx in (r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
               r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
               r'"hiRes":"(https:[^"]+)"', r'id="landingImage"[^>]+src="(https:[^"]+)"'):
        m = re.search(rx, h, re.I)
        if m:
            u = m.group(1).replace("&amp;", "&")
            return "https:" + u if u.startswith("//") else u
    return None


def resolve(url="", slug=""):
    if slug and not valid_slug(slug):
        slug = ""
    if url and not str(url).lower().startswith(("http://", "https://")):
        url = ""
    img = local_image(slug)
    if img:
        return "file", img
    key = url or slug
    if not key:
        return None, None
    with _LOCK:
        c = _load()
        if key in c:
            return ("url", c[key]) if c[key] else (None, None)
    found = _pool_image(url) or (_og_image(url) if url.startswith("http") else None)
    with _LOCK:
        c = _load()
        c[key] = found or ""
        _save(c)
    return ("url", found) if found else (None, None)


PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">'
    '<rect width="120" height="120" fill="#17161b"/>'
    '<text x="60" y="68" font-size="34" text-anchor="middle" fill="#3a3842">👠</text></svg>')
