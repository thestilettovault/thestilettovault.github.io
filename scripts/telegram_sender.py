"""
Telegram Sender — The Stiletto Vault
Sends product cards with images to the Taste Bot chat.
Fetches OG image from product page and uploads as file — no CDN blocking.
"""
import sys
import os
import re
import time
import json
import hashlib
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv

if sys.stdout is None:          # pythonw (scheduled task) has no console
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL  = f"https://api.telegram.org/bot{BOT_TOKEN}"

sys.path.insert(0, os.path.dirname(__file__))
import taste_engine

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}


def _short_id(url):
    return hashlib.md5(url.encode()).hexdigest()[:6]


def _make_keyboard(product_id):
    return {
        "inline_keyboard": [[
            {"text": "✅ כן", "callback_data": f"ok|{product_id}"},
            {"text": "❌ לא", "callback_data": f"no|{product_id}"},
            {"text": "🔗 פתח", "callback_data": f"open|{product_id}"}
        ]]
    }


def _download_image(img_url):
    """Download image bytes from URL. Returns bytes or None."""
    try:
        r = requests.get(img_url, headers=HEADERS, timeout=10)
        ct = r.headers.get("content-type", "")
        if r.ok and ct.startswith("image") and len(r.content) > 5000:
            return r.content
    except Exception:
        pass
    return None


def _fetch_og_image(product_url, html=None):
    """
    Fetch the best product image from a product page.
    Tries multiple strategies: Shopify JSON, JSON-LD, OG tags.
    Returns image bytes or None.
    """
    try:
        if html is None:
            r = requests.get(product_url, headers=HEADERS, timeout=10, allow_redirects=True)
            if not r.ok:
                return None
            html = r.text

        domain = taste_engine.get_domain(product_url)

        # ── Strategy 1: Shopify product JSON (most reliable for Shopify stores) ──
        if any(s in domain for s in ["killstar", "restyle", "dollskill", "gthic", "vexclothing"]):
            # Shopify embeds product JSON in the page
            m = re.search(r'"featured_image"\s*:\s*"(https?://[^"]+)"', html)
            if not m:
                m = re.search(r'"images"\s*:\s*\["(https?://[^"]+)"', html)
            if not m:
                # Try CDN pattern: look for first product image in cdn/shop/
                m = re.search(r'(https://cdn\.shopify\.com/s/files/[^\s"\'<>]+\.(?:jpg|jpeg|webp|png))', html)
            if m:
                img = _download_image(m.group(1).split("?")[0])
                if img:
                    return img

            # 1b: Shopify search/suggest.json — works for JS-rendered stores (e.g. Killstar)
            try:
                handle = product_url.split("/products/")[-1].split("?")[0].rstrip("/")
                if handle and "/" not in handle:
                    parsed = urlparse(product_url)
                    base = f"{parsed.scheme}://{parsed.netloc}"
                    search_term = handle.replace("-", " ")
                    r_s = requests.get(
                        f"{base}/search/suggest.json",
                        params={"q": search_term, "resources[type]": "product", "resources[limit]": "5"},
                        headers=HEADERS, timeout=8
                    )
                    if r_s.ok:
                        results = r_s.json().get("resources", {}).get("results", {}).get("products", [])
                        for p in results:
                            if p.get("handle") == handle:
                                fi = p.get("featured_image") or {}
                                img_url = p.get("image") or fi.get("url", "")
                                if img_url:
                                    img = _download_image(img_url.split("?")[0])
                                    if img:
                                        return img
            except Exception:
                pass

        # ── Strategy 2: Amazon ──
        if "amazon" in domain:
            # Amazon puts main image in data-old-hires or in a script tag
            m = re.search(r'data-old-hires="(https?://[^"]+)"', html)
            if not m:
                m = re.search(r'"large"\s*:\s*"(https://m\.media-amazon\.com/images/[^"]+)"', html)
            if not m:
                m = re.search(r'"hiRes"\s*:\s*"(https://[^"]+)"', html)
            if m:
                img = _download_image(m.group(1))
                if img:
                    return img

        # ── Strategy 3: JSON-LD (works on many sites) ──
        m = re.search(r'"image"\s*:\s*["\[](https?://[^">\]\s]+)', html)
        if m:
            img = _download_image(m.group(1))
            if img:
                return img

        # ── Strategy 4: OG image — but skip logos (< 50KB is likely a logo) ──
        for pattern in [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\'>\s]+)["\']',
            r'<meta[^>]+content=["\'](https?://[^"\'>\s]+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\'](https?://[^"\'>\s]+)["\']',
        ]:
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                img = _download_image(m.group(1))
                if img and len(img) > 50_000:   # skip small logos
                    return img

        return None
    except Exception as e:
        print(f"  [img] error: {e}")
        return None


def _escape_md(text: str) -> str:
    """Escape Markdown v1 special characters (_ * ` [) in plain text."""
    return (str(text or "").replace("_", "\\_").replace("*", "\\*")
            .replace("`", "\\`").replace("[", "\\["))


def _shopify_thumb(url: str) -> str:
    """Return a ~800px Shopify CDN thumbnail URL to avoid PHOTO_INVALID_DIMENSIONS."""
    import re as _re
    # Insert _800x before file extension for Shopify CDN
    if "cdn.shopify.com" in url:
        url = url.split("?")[0]
        url = _re.sub(r'\.(jpg|jpeg|png|webp)$', r'_800x.\1', url, flags=_re.IGNORECASE)
    return url


def _post(method, *, data=None, json_body=None, files=None, timeout=15):
    """POST to the Telegram Bot API. Returns the Response, or None on a network
    error. On a 400 (usually a Markdown parse error from odd characters in a
    title) retries ONCE without parse_mode."""
    url = f"{BASE_URL}/{method}"
    try:
        r = requests.post(url, data=data, json=json_body, files=files, timeout=timeout)
        if r.status_code == 400 and "PHOTO_INVALID" not in r.text:
            body = dict(json_body) if json_body is not None else None
            form = dict(data) if data is not None else None
            if (body and body.pop("parse_mode", None)) or (form and form.pop("parse_mode", None)):
                print("  [telegram] 400 - retrying without parse_mode")
                r = requests.post(url, data=form, json=body, files=files, timeout=timeout)
        return r
    except Exception as e:
        print(f"  [telegram] request failed: {e}")
        return None


def _resp_ok(r):
    if r is None or not r.ok:
        return False
    try:
        return bool(r.json().get("ok", True))
    except Exception:
        return True


def send_product(url, title, commission="", image_url="", domain=""):
    """Send a product card with image + approve/reject buttons.
    Returns True only when Telegram accepted the card."""
    try:
        return _send_product(url, title, commission, image_url, domain)
    except Exception as e:
        print(f"  [telegram] send_product failed: {e}")
        return False


def _send_product(url, title, commission, image_url, domain):
    product_id = _short_id(url)
    taste_engine.save_pending(product_id, url, title, image_url, commission, domain)

    score = taste_engine.score_product(url, title)
    score_tag = " 🔥" if score > 3 else (" 🥶" if score < -2 else "")

    domain_str = domain or taste_engine.get_domain(url)
    commission_str = f" — {commission} commission" if commission else ""
    # Escape Markdown specials so the parser doesn't choke on titles / URLs
    safe_url = _escape_md(url)

    is_aliexpress = "aliexpress" in domain_str.lower()
    caption = (
        f"👠 *{_escape_md(title[:80])}*{score_tag}\n"
        f"🏷 {_escape_md(domain_str)}{_escape_md(commission_str)}\n"
        f"🔗 {safe_url}"
    )
    if is_aliexpress:
        # AliExpress images can't be auto-downloaded — Ofer supplies them.
        caption += (
            "\n\n⚠️ *AliExpress* — אחרי ✅:\n"
            "1) העתק את הלינק כאן ↑\n"
            "2) העלה מיד את תמונות הנעל כאן בצ'אט\n"
            "→ אבנה מהן את תיקיית העבודה."
        )

    keyboard = _make_keyboard(product_id)

    # Try to get image: first from passed image_url, then scrape the page
    img_bytes = None
    src_url = _shopify_thumb(image_url) if image_url else ""
    if src_url:
        try:
            r = requests.get(src_url, headers=HEADERS, timeout=8)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                img_bytes = r.content
        except Exception:
            pass

    if not img_bytes and image_url and image_url != src_url:
        # Try original URL if thumb failed
        try:
            r = requests.get(image_url, headers=HEADERS, timeout=8)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                img_bytes = r.content
        except Exception:
            pass

    if not img_bytes:
        print(f"  [img] scraping image from {url[:50]}...")
        img_bytes = _fetch_og_image(url)

    r = None
    # Send with image if we scraped one successfully
    if img_bytes:
        r = _post("sendPhoto",
                  data={
                      "chat_id":      CHAT_ID,
                      "caption":      caption,
                      "parse_mode":   "Markdown",
                      "reply_markup": json.dumps(keyboard)
                  },
                  files={"photo": ("product.jpg", img_bytes, "image/jpeg")},
                  timeout=20)
        # Fallback: if photo rejected (e.g. PHOTO_INVALID_DIMENSIONS), send as text
        if r is not None and not r.ok and "PHOTO_INVALID" in r.text:
            print("  [img] photo rejected, falling back to text+preview")
            img_bytes = None

    if not img_bytes:
        # Fallback: let Telegram fetch the preview image itself
        r = _post("sendMessage", json_body={
            "chat_id":      CHAT_ID,
            "text":         caption,
            "parse_mode":   "Markdown",
            "reply_markup": keyboard,
            "link_preview_options": {
                "is_disabled":        False,
                "prefer_large_media": True,
                "show_above_text":    True
            }
        }, timeout=15)

    if not _resp_ok(r):
        print(f"  [telegram] error {getattr(r, 'status_code', 'no-response')}: "
              f"{(r.text[:120] if r is not None else '')}")
        return False

    time.sleep(0.5)
    return True


def send_text(text, parse_mode="Markdown"):
    """Send a plain/Markdown message. Returns True only if Telegram accepted it."""
    body = {"chat_id": CHAT_ID, "text": text}
    if parse_mode:
        body["parse_mode"] = parse_mode
    r = _post("sendMessage", json_body=body, timeout=10)
    if not _resp_ok(r):
        print(f"  [telegram] send_text failed: "
              f"{getattr(r, 'status_code', 'no-response')} {(r.text[:120] if r is not None else '')}")
        return False
    return True


def send_summary(count_sent):
    if count_sent == 0:
        return send_text("🤖 סריקה הסתיימה — אין מוצרים חדשים להיום.")
    return send_text(f"🤖 סריקה הסתיימה — נשלחו *{count_sent}* מוצרים לבדיקה.")
