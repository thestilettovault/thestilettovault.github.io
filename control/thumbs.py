# -*- coding: utf-8 -*-
"""thumbs.py — find a picture for any product (Control Center /api/thumb).

Order: local GELEM folder (post_image / ad_* / source / any image) → AliExpress pool
image by item id → og:image of the product page (cached in data/thumb_cache.json,
local only). Returns ("file", Path) | ("url", str) | (None, None).
"""
import json
import re
import threading
from pathlib import Path
from urllib.parse import quote

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
        CACHE.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
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


def local_image(slug):
    if not slug or not GELEM.exists():
        return None
    for folder in [GELEM / slug] + list(GELEM.glob(f"*/{slug}")):
        if folder.is_dir():
            img = _best_image(folder)
            if img:
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
        r = requests.get(url, headers=UA, timeout=8, allow_redirects=True)
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
