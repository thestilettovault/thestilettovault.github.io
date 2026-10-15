"""
Taste Engine — The Stiletto Vault
Learns user's aesthetic taste from approve/reject signals.
Scores new products against the accumulated profile.
"""
import sys
import json
import os
from datetime import datetime
from urllib.parse import urlparse

if sys.stdout is None:          # pythonw (scheduled task) has no console
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jsonio

DATA_DIR       = os.path.join(os.path.dirname(__file__), "..", "data")
TASTE_FILE     = os.path.join(DATA_DIR, "taste_profile.json")
REJECT_FILE    = os.path.join(DATA_DIR, "rejected_profile.json")
SCORES_FILE    = os.path.join(DATA_DIR, "taste_scores.json")
PENDING_FILE   = os.path.join(DATA_DIR, "pending_reviews.json")
CATALOG_FILE   = os.path.join(DATA_DIR, "approved_catalog.json")  # library for content creation
PROJECT_ROOT   = os.path.abspath(os.path.join(DATA_DIR, ".."))
GELEM_ROOT     = os.path.join(PROJECT_ROOT, "GELEM")

os.makedirs(DATA_DIR, exist_ok=True)

def _brand_name():
    """Niche display name from niches/<active>/niche.json (literal fallback)."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        from control.niche import cfg
        return cfg("identity.name", "The Stiletto Vault")
    except Exception:
        return "The Stiletto Vault"


# ── Affiliate injection rules ─────────────────────────────────────────
# Maps domain → how to inject affiliate ID into a product URL.
AFFILIATE_RULES = {
    "amazon.com":       {"param": "tag",     "value": "thegothicvaul-20"},
    "darkinlove.com":   {"param": "sca_ref", "value": "ll249558.3UXnWnByxo"},
    # add more as programs are registered
}

def _set_query_param(url: str, param: str, value: str) -> str:
    """Return url with query param `param` set to `value`: a foreign value is
    replaced, our value is left alone, a missing param is appended."""
    base, hashsep, frag = url.partition("#")
    path, _, query = base.partition("?")
    parts = query.split("&") if query else []
    found = False
    for i, seg in enumerate(parts):
        if seg.split("=", 1)[0] == param:
            parts[i] = f"{param}={value}"
            found = True
    if not found:
        parts.append(f"{param}={value}")
    return path + "?" + "&".join(p for p in parts if p) + (hashsep + frag if hashsep else "")


def inject_affiliate_link(url: str) -> str:
    """Return url with our affiliate link. AliExpress → Admitad deeplink wrapper
    (central source); Amazon/Dark In Love → tag param (a foreign tag is replaced
    by ours). Unknown domains unchanged — call affiliate_links.is_earning() on the
    result to learn whether it will actually earn."""
    domain = get_domain(url)
    # AliExpress is wrapped through the Admitad deeplink, not a query param.
    if "aliexpress." in domain:
        try:
            import affiliate_links
            return affiliate_links.aliexpress(url)
        except Exception as e:
            print(f"[aff] AliExpress wrap failed: {e}")
            return url
    for d, rule in AFFILIATE_RULES.items():
        if d in domain:
            return _set_query_param(url, rule["param"], rule["value"])
    return url

# ── Helpers ───────────────────────────────────────────────────────────

def load_json(path, default):
    """Default only when the file is missing; a corrupt file is backed up and raises."""
    return jsonio.load(path, default)

def save_json(path, data):
    jsonio.save(path, data, ensure_ascii=False, indent=2)

def get_domain(url):
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""

STOPWORDS = {"the", "a", "an", "and", "or", "for", "with", "in", "on",
             "at", "to", "of", "by", "from", "is", "are", "was", "be"}

def get_keywords(text):
    words = (text or "").lower().replace("-", " ").replace("_", " ").split()
    return [w.strip(".,!?") for w in words
            if len(w) > 3 and w not in STOPWORDS]

# ── Pending reviews (short-id → product data) ─────────────────────────

def save_pending(product_id, url, title, image_url="", commission="", domain=""):
    with jsonio.locked(PENDING_FILE):
        pending = load_json(PENDING_FILE, {})
        pending[product_id] = {
            "url": url, "title": title,
            "image_url": image_url, "commission": commission,
            "domain": domain or get_domain(url),
            "ts": datetime.now().isoformat()
        }
        # Keep only last 200 pending items
        if len(pending) > 200:
            oldest = sorted(pending.items(), key=lambda x: x[1].get("ts", ""))
            for k, _ in oldest[:len(pending) - 200]:
                del pending[k]
        save_json(PENDING_FILE, pending)

def get_pending(product_id):
    pending = load_json(PENDING_FILE, {})
    return pending.get(product_id, {})

def remove_pending(product_id):
    with jsonio.locked(PENDING_FILE):
        pending = load_json(PENDING_FILE, {})
        pending.pop(product_id, None)
        save_json(PENDING_FILE, pending)

# ── Scoring ───────────────────────────────────────────────────────────

def _update_scores(url, title, approved):
    domain  = get_domain(url)
    keywords = get_keywords(title)
    weight  = 2 if approved else 1   # approvals count more
    delta   = +weight if approved else -weight

    with jsonio.locked(SCORES_FILE):
        scores  = load_json(SCORES_FILE, {"brands": {}, "keywords": {}})
        if domain:
            scores["brands"][domain] = scores["brands"].get(domain, 0) + delta

        for kw in keywords:
            scores["keywords"][kw] = scores["keywords"].get(kw, 0) + (1 if approved else -1)

        save_json(SCORES_FILE, scores)

def score_product(url, title):
    """Return a taste score for a product. Higher = better match."""
    scores   = load_json(SCORES_FILE, {"brands": {}, "keywords": {}})
    domain   = get_domain(url)
    keywords = get_keywords(title or "")

    total = 0
    if domain in scores["brands"]:
        total += scores["brands"][domain] * 2   # brand signal is strong
    for kw in keywords:
        total += scores["keywords"].get(kw, 0)
    return total

# ── Record decisions ──────────────────────────────────────────────────

import re as _re

def _slugify(text):
    s = (text or "").lower()
    s = _re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s[:60] or "product").rstrip("-")

def _extract_asin(url):
    m = _re.search(r"/(?:dp|gp/product|d)/([A-Z0-9]{10})", url or "", _re.I)
    return m.group(1).upper() if m else ""

def _og_image(url):
    """Scrape og:image / twitter:image from a product page. Works for AliExpress,
    Shopify, and most stores. Returns "" on failure."""
    try:
        import requests
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        html = r.text
        for pat in (r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                    r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']'):
            m = _re.search(pat, html, _re.I)
            if m:
                src = m.group(1)
                return ("https:" + src) if src.startswith("//") else src
    except Exception as e:
        print(f"[gelem] og:image scrape failed: {e}")
    return ""

def _resolve_image_url(url, domain, image_url):
    """Best available product image URL.
    Amazon → PA-API by ASIN; else the given image_url; else og:image scrape."""
    if image_url:
        return image_url
    if "amazon" in (domain or ""):
        asin = _extract_asin(url)
        if asin:
            try:
                import paapi
                data = paapi.get_item(asin)
                imgs = data.get("images") or []
                if imgs:
                    return imgs[0]
            except Exception as e:
                print(f"[gelem] PA-API image lookup failed: {e}")
    # General fallback (AliExpress, Shopify, direct stores).
    return _og_image(url)

def _gelem_dir_for(url, title):
    """Deterministic GELEM folder for a product: GELEM/<YYYY-MM-DD>/<slug>/.
    AliExpress items share titles ("Stiletto Heels"), so the item id keeps each
    heel's folder unique — otherwise two picks collide onto one folder."""
    asin = _extract_asin(url)
    m = _re.search(r"/item/(\d+)", url or "")   # AliExpress
    if m:
        slug = f"{_slugify(title or 'heel')[:30]}-{m.group(1)}".strip("-")[:60] or m.group(1)
    else:
        slug = _slugify(title) if title else (asin.lower() if asin else _slugify(url))
    day  = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(GELEM_ROOT, day, slug)

def _write_link_file(dest_dir, title, aff_link, commission):
    """Write _LINK.txt — the ready-to-use affiliate link for this product."""
    try:
        with open(os.path.join(dest_dir, "_LINK.txt"), "w", encoding="utf-8") as f:
            f.write(f"{title}\n{aff_link}\n")
            if commission:
                f.write(f"commission: {commission}\n")
    except Exception as e:
        print(f"[gelem] _LINK.txt write failed: {e}")

def download_to_gelem(url, title, domain="", image_url="", aff_link="", commission=""):
    """At approval time: create the product's GELEM folder, write _LINK.txt, and try
    to fetch source.jpg. ALWAYS returns (local_asset_dir_rel, image_ok:bool).
    If the image can't be fetched (e.g. AliExpress anti-bot), the folder + link still
    exist and image_ok=False — a photo sent to Telegram fills source.jpg later."""
    dest_dir = _gelem_dir_for(url, title)
    os.makedirs(dest_dir, exist_ok=True)
    _write_link_file(dest_dir, title, aff_link or url, commission)
    dest = os.path.join(dest_dir, "source.jpg")
    rel_dir = os.path.relpath(dest_dir, PROJECT_ROOT).replace("\\", "/")
    if os.path.exists(dest):
        return rel_dir, True
    # Auto-fetch source from the scout-provided image_url. This works for the
    # AliExpress media CDN too (the old anti-scrape wait was what stranded every
    # AliExpress lead on _LINK.txt) — the automatic chain needs a source to run.
    # Any photo Ofer sends afterwards still lands as an extra angle (img_2, …).
    src = image_url or _resolve_image_url(url, domain, image_url)
    if not src:
        print(f"[gelem] folder ready, image pending (send photo): {rel_dir}")
        return rel_dir, False
    if _fetch_image(src, dest):
        print(f"[gelem] downloaded → {rel_dir}/source.jpg")
        return rel_dir, True
    print(f"[gelem] image fetch failed — pending photo: {rel_dir}")
    return rel_dir, False


def _is_real_image(path):
    """True if `path` is a decodable image (PIL verify; magic bytes if PIL is missing)."""
    try:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return False
        try:
            from PIL import Image
        except ImportError:
            with open(path, "rb") as f:
                head = f.read(16)
            return (head.startswith(b"\xff\xd8\xff") or head.startswith(b"\x89PNG\r\n\x1a\n")
                    or head[:6] in (b"GIF87a", b"GIF89a")
                    or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"))
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


def _discard(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _fetch_image(src, dest):
    """Fetch an image to dest. Try requests first; fall back to curl, which gets
    past the AliExpress media-CDN TLS fingerprint that rejects requests under load.
    The file must decode as a real image — an HTML block page saved as .jpg is
    deleted and counts as a failure."""
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    try:
        import requests
        r = requests.get(src, headers={"User-Agent": ua}, timeout=20)
        r.raise_for_status()
        if r.content:
            with open(dest, "wb") as f:
                f.write(r.content)
            if _is_real_image(dest):
                return True
            print("[gelem] downloaded file is not an image; trying curl")
            _discard(dest)
    except Exception as e:
        print(f"[gelem] requests fetch failed ({e}); trying curl")
        _discard(dest)
    try:
        import subprocess
        rc = subprocess.run(["curl", "-s", "-L", "-A", ua, "-o", dest, src],
                            timeout=60).returncode
        if rc == 0 and _is_real_image(dest):
            return True
        _discard(dest)
        return False
    except Exception as e:
        print(f"[gelem] curl fetch failed ({e})")
        _discard(dest)
        return False

def _autobuild_worklib(item):
    """Auto-generate the work library (captions) for a product with content.
    Never raises — a scaffold failure must not break approval/photo handling."""
    try:
        import build_work_library
        build_work_library.scaffold(item)
    except Exception as e:
        print(f"[worklib] auto-build skipped: {e}")


def attach_photo_to_pending(photo_path, window_min=45):
    """Place a Telegram-sent photo into the product folder Ofer is currently working.
    Target = the newest approved product that is still awaiting photos (image_ok False)
    OR any AliExpress product approved within the last `window_min` minutes (so several
    angles for the same shoe all land together). First photo → source.jpg; the next
    ones → img_2.jpg, img_3.jpg … Returns "(title, filename)" or "" if none matches
    (caller then treats the photo as a taste reference).
    A sticky 'current target' keeps successive photos flowing to the SAME product
    (multiple angles). Advance to the next waiting product with set_photo_target(None)
    — the bot triggers that on the word 'הבא'/'next'."""
    catalog = load_json(CATALOG_FILE, [])
    now = datetime.now()

    def _pick():
        # sticky target first
        tgt = get_photo_target()
        if tgt:
            for it in catalog:
                if it.get("local_asset") == tgt:
                    return it
        # else newest product still awaiting photos
        for it in reversed(catalog):
            if it.get("local_asset") and not it.get("image_ok", True):
                return it
        return None

    item = _pick()
    if not item:
        return ""
    dest_dir = os.path.join(PROJECT_ROOT, item["local_asset"])
    os.makedirs(dest_dir, exist_ok=True)
    if not os.path.exists(os.path.join(dest_dir, "source.jpg")):
        fname = "source.jpg"
    else:
        n = 2
        while os.path.exists(os.path.join(dest_dir, f"img_{n}.jpg")):
            n += 1
        fname = f"img_{n}.jpg"
    try:
        import shutil
        shutil.copyfile(photo_path, os.path.join(dest_dir, fname))
        item["image_ok"] = True
        item["downloaded"] = now.strftime("%Y-%m-%d")
        with jsonio.locked(CATALOG_FILE):       # reload so a concurrent approval isn't lost
            fresh = load_json(CATALOG_FILE, [])
            for it in fresh:
                if it.get("local_asset") == item["local_asset"]:
                    it["image_ok"] = True
                    it["downloaded"] = item["downloaded"]
            save_json(CATALOG_FILE, fresh)
        set_photo_target(item["local_asset"])      # stay on this product
        print(f"[gelem] photo attached → {item['local_asset']}/{fname}")
        _autobuild_worklib(item)
        # first photo (source.jpg) completes the lead → queue it for production
        if fname == "source.jpg":
            _enqueue_production(item["url"], item.get("title", ""), item["local_asset"],
                                image_url=item.get("image_url", ""), deal=item.get("deal", {}))
        return f"{item.get('title','product')}|{fname}"
    except Exception as e:
        print(f"[gelem] attach failed: {e}")
        return ""


_TARGET_FILE = os.path.join(DATA_DIR, "_photo_target.json")

def get_photo_target():
    d = load_json(_TARGET_FILE, {})
    return d.get("local_asset") or None

def set_photo_target(local_asset):
    """Set the product photos attach to; pass None/'' to advance to the next waiting one."""
    save_json(_TARGET_FILE, {"local_asset": local_asset or ""})

_POOL_FILE = os.path.join(DATA_DIR, "aliexpress_pool.json")

def _deal_for_url(url):
    """Pull the real AliExpress deal (sale/was/discount/rating/sold) for a product
    url from the scout pool, so the on-screen price overlay has real data to burn.
    Returns {} when the url isn't a pooled AliExpress product."""
    pool = load_json(_POOL_FILE, {})
    products = pool.get("products", []) if isinstance(pool, dict) else pool
    for p in products:
        if p.get("url") == url:
            return p.get("deal") or {}
    return {}

_PROD_QUEUE = os.path.join(DATA_DIR, "production_queue.json")

def _enqueue_production(url, title, local_asset, image_url="", deal=None):
    """Append a freshly-approved lead to the production queue the runner drains.
    status='approved' → the runner (a local Claude session/scheduled task) picks it
    up, runs the Space to 4 ads, and pushes them to Telegram for the A/B/C/D pick.
    Idempotent by url. This is the missing link that makes approval → production
    automatic instead of stranding the lead after record_approval."""
    with jsonio.locked(_PROD_QUEUE):
        q = load_json(_PROD_QUEUE, [])
        if any(e.get("url") == url for e in q):
            return
        q.append({
            "url": url, "title": title, "local_asset": local_asset,
            "image_url": image_url, "deal": deal or {},
            "status": "approved", "approved_ts": datetime.now().isoformat(),
        })
        save_json(_PROD_QUEUE, q)
    print(f"[queue] enqueued for production: {title[:40]}")

def _earning_check(aff_link):
    try:
        import affiliate_links
        return bool(affiliate_links.is_earning(aff_link))
    except Exception as e:
        print(f"[aff] earning check failed: {e}")
        return False


def record_approval(url, title, image_url="", commission="", domain=""):
    """Record an approval. Never blocks on a non-earning link, but sets
    `earning` on the catalog entry and returns
    {"earning": bool, "warning": str} so the bot can tell the owner when a
    product has NO active affiliate tracking."""
    aff_link = inject_affiliate_link(url)
    earning = _earning_check(aff_link)
    warning = "" if earning else (
        f"⚠️ אין לינק שותפים פעיל ל-{get_domain(url) or url[:40]} — "
        "לא תרוויח על המוצר הזה (חסר our_id / רישום)")
    if warning:
        print(f"[aff] NOT EARNING: {url[:70]}")
    if not domain:
        domain = get_domain(url)

    # Taste profile (legacy — keep for backward compat)
    with jsonio.locked(TASTE_FILE):
        profile = load_json(TASTE_FILE, {"approved": []})
        profile["approved"].append({
            "title": title, "link": url,
            "date": datetime.now().isoformat()
        })
        save_json(TASTE_FILE, profile)

    # Approved catalog — structured for content creation
    catalog = load_json(CATALOG_FILE, [])
    # Deduplicate by product identity (www./query/slash-insensitive) — never list a shoe twice
    from product_key import product_key
    existing_keys = {product_key(item.get("url")) for item in catalog}
    if product_key(url) not in existing_keys:
        # At approval time: build the GELEM folder + _LINK.txt, try to fetch image.
        local_asset, image_ok = download_to_gelem(
            url, title, domain=domain, image_url=image_url,
            aff_link=aff_link, commission=commission)
        entry = {
            "title":       title,
            "url":         url,
            "aff_link":    aff_link,
            "earning":     earning,              # False = no active affiliate tracking
            "domain":      domain,
            "image_url":   image_url,
            "commission":  commission,
            "deal":        _deal_for_url(url),   # real price/discount/rating/sold for the overlay
            "date":        datetime.now().isoformat(),
            "local_asset": local_asset,
            "image_ok":    image_ok,
            "downloaded":  datetime.now().strftime("%Y-%m-%d") if image_ok else "",
        }
        with jsonio.locked(CATALOG_FILE):        # reload: the download above can take a while
            catalog = load_json(CATALOG_FILE, [])
            if product_key(url) not in {product_key(i.get("url")) for i in catalog}:
                catalog.append(entry)
                save_json(CATALOG_FILE, catalog)
        # If the image is already in place (non-AliExpress), build the work
        # library (captions) right now — fully automatic, no "done" needed.
        if image_ok:
            _autobuild_worklib(entry)
            # source is in place → hand the lead to the production queue so the
            # runner turns it into ads automatically (no manual kick needed).
            _enqueue_production(url, title, local_asset,
                                image_url=image_url, deal=_deal_for_url(url))
        else:
            # awaiting photos → make this the product the next photos attach to.
            set_photo_target(local_asset)

    _update_scores(url, title, approved=True)
    print(f"[taste] APPROVED: {url[:60]}" + ("" if earning else "  (NOT EARNING)"))
    return {"earning": earning, "warning": warning}

def record_rejection(url, title):
    with jsonio.locked(REJECT_FILE):
        profile = load_json(REJECT_FILE, {"rejected": []})
        profile["rejected"].append({
            "title": title, "link": url,
            "date": datetime.now().isoformat()
        })
        save_json(REJECT_FILE, profile)
    _update_scores(url, title, approved=False)
    print(f"[taste] REJECTED: {url[:60]}")

# ── Summary ───────────────────────────────────────────────────────────

def get_summary():
    scores   = load_json(SCORES_FILE, {"brands": {}, "keywords": {}})
    approved = load_json(TASTE_FILE,  {"approved": []}).get("approved", [])
    rejected = load_json(REJECT_FILE, {"rejected": []}).get("rejected", [])

    top_brands = sorted(scores["brands"].items(), key=lambda x: x[1], reverse=True)[:5]
    top_kw     = sorted(scores["keywords"].items(), key=lambda x: x[1], reverse=True)[:8]
    bad_brands = sorted(scores["brands"].items(), key=lambda x: x[1])[:3]

    lines = [
        f"📊 *פרופיל טעם — {_brand_name()}*",
        f"✅ אושרו: {len(approved)}  |  ❌ נדחו: {len(rejected)}",
        "",
        "👠 *Brands מובילים:*",
    ]
    for brand, sc in top_brands:
        lines.append(f"  {brand}: {sc:+d}")
    lines += ["", "🏷 *מילות מפתח מובילות:*"]
    for kw, sc in top_kw:
        lines.append(f"  #{kw}: {sc:+d}")
    if bad_brands and bad_brands[0][1] < 0:
        lines += ["", "🚫 *Brands חלשים:*"]
        for brand, sc in bad_brands:
            if sc < 0:
                lines.append(f"  {brand}: {sc:+d}")
    return "\n".join(lines)
