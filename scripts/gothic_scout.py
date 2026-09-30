"""
Gothic Scout — TheGothicVault Product Intelligence
Connects to Pinterest API, manages INBOX + DAILY REVIEW boards,
learns taste from user curation decisions.
"""

import sys
import os
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

# ── Config ──────────────────────────────────────────────────────────
APP_ID            = os.getenv("PINTEREST_APP_ID")
ACCESS_TOKEN      = os.getenv("PINTEREST_ACCESS_TOKEN")
WRITE_TOKEN       = os.getenv("PINTEREST_WRITE_TOKEN") or ACCESS_TOKEN
BASE_URL          = "https://api-sandbox.pinterest.com/v5"
DATA_DIR          = os.path.join(os.path.dirname(__file__), "..", "data")
TASTE_FILE        = os.path.join(DATA_DIR, "taste_profile.json")
REJECTED_FILE     = os.path.join(DATA_DIR, "rejected_profile.json")
OUTREACH_LOG_FILE = os.path.join(DATA_DIR, "outreach_log.json")
PINNED_URLS_FILE  = os.path.join(DATA_DIR, "pinned_to_review.json")  # dedup: URLs already sent to DAILY REVIEW

# ── Pinterest Content Policy — BLOCKED DOMAINS ───────────────────────
# These brands sell adult/BDSM/fetish content that violates Pinterest's
# Community Guidelines (sexual fetish content).
# Violation received: May 12, 2026 — Pin ID 522347256805156765 disabled.
# WARNING: Additional violations may result in full account suspension.
# These domains must NEVER be pinned to any Pinterest board.
# Promote these brands via other channels only (blog, email, Instagram).
PINTEREST_BLOCKED_DOMAINS = {
    "skintwo.com",       # BDSM/fetish apparel — caused May 2026 violation
    "libidex.com",       # latex fetishwear
    "bdsmstore.de",      # explicit BDSM products
    "pleasurements.com", # adult sex shop
    "honour.co.uk",      # fetish/BDSM clothing
    "rivithead.com",     # fetish shoes/apparel
    "shwomenstore.com",  # adult lingerie/fetish
}

BOARD_INBOX       = "TheGothicVault INBOX"
BOARD_REVIEW      = "TheGothicVault DAILY REVIEW"
BOARD_ZAMNAI      = "522347325470861868"  # User's real "זמני" board (production)
BOARD_REVIEW_ID   = os.getenv("PINTEREST_REVIEW_BOARD_ID")  # optional: skip board creation

os.makedirs(DATA_DIR, exist_ok=True)

# ── Pinterest API ────────────────────────────────────────────────────

def normalize_url(url):
    """Strip query params and fragment for dedup — same product path = same URL."""
    from urllib.parse import urlparse, urlunparse
    try:
        p = urlparse(url)
        return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
    except Exception:
        return url


def headers(write=False):
    token = WRITE_TOKEN if write else ACCESS_TOKEN
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def api_get(endpoint, params=None):
    r = requests.get(f"{BASE_URL}{endpoint}", headers=headers(), params=params)
    r.raise_for_status()
    return r.json()

def api_post(endpoint, body):
    # Try with WRITE_TOKEN first (production), fallback to ACCESS_TOKEN (sandbox)
    r = requests.post(f"{BASE_URL}{endpoint}", headers=headers(write=True), json=body)
    if not r.ok:
        print(f"    API error {r.status_code}: {r.text[:300]}")
    r.raise_for_status()
    return r.json()

def api_delete(endpoint):
    r = requests.delete(f"{BASE_URL}{endpoint}", headers=headers(write=True))
    if r.status_code not in (200, 204):
        r.raise_for_status()
    return True

# ── Boards ───────────────────────────────────────────────────────────

def get_all_boards():
    """Returns dict of {board_name: board_id}"""
    result = {}
    bookmark = None
    while True:
        params = {"page_size": 25}
        if bookmark:
            params["bookmark"] = bookmark
        data = api_get("/boards", params)
        for board in data.get("items", []):
            result[board["name"]] = board["id"]
        bookmark = data.get("bookmark")
        if not bookmark:
            break
    return result

def get_or_create_board(name):
    boards = get_all_boards()
    if name in boards:
        print(f"  Board found: {name} ({boards[name]})")
        return boards[name]
    print(f"  Creating board: {name}")
    data = api_post("/boards", {"name": name, "privacy": "SECRET"})
    return data["id"]

def setup_boards():
    """Get or create INBOX and DAILY REVIEW boards."""
    print("Setting up boards...")
    if BOARD_REVIEW_ID:
        # Use pre-configured board IDs (no boards:write scope needed)
        inbox_id  = BOARD_ZAMNAI
        review_id = BOARD_REVIEW_ID
        print(f"  INBOX (zamnai): {inbox_id}")
        print(f"  DAILY REVIEW:   {review_id}")
    else:
        inbox_id  = get_or_create_board(BOARD_INBOX)
        review_id = get_or_create_board(BOARD_REVIEW)
        print(f"  INBOX:        {inbox_id}")
        print(f"  DAILY REVIEW: {review_id}")
    return inbox_id, review_id

# ── Pins ─────────────────────────────────────────────────────────────

def get_pins_on_board(board_id):
    """Returns list of pins with id, title, link, media."""
    pins = []
    bookmark = None
    while True:
        params = {"page_size": 25}
        if bookmark:
            params["bookmark"] = bookmark
        data = api_get(f"/boards/{board_id}/pins", params)
        pins.extend(data.get("items", []))
        bookmark = data.get("bookmark")
        if not bookmark:
            break
    return pins

def create_pin(board_id, image_url, title, source_url, description=""):
    """Pin an image to a board. title = source URL for INBOX convention."""
    body = {
        "board_id": board_id,
        "title": title[:100],
        "description": description[:500],
        "link": source_url,
        "media_source": {
            "source_type": "image_url",
            "url": image_url
        }
    }
    result = api_post("/pins", body)
    time.sleep(2)  # rate limit safety
    return result.get("id")

def delete_pin(pin_id):
    return api_delete(f"/pins/{pin_id}")

# ── Taste Engine ─────────────────────────────────────────────────────

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def record_approval(pin):
    """User kept this pin = approved."""
    profile = load_json(TASTE_FILE, {"approved": []})
    profile["approved"].append({
        "title": pin.get("title", ""),
        "link":  pin.get("link", ""),
        "date":  datetime.now().isoformat()
    })
    save_json(TASTE_FILE, profile)

def record_rejection(pin):
    """Pin was deleted by user = rejected."""
    profile = load_json(REJECTED_FILE, {"rejected": []})
    profile["rejected"].append({
        "title": pin.get("title", ""),
        "link":  pin.get("link", ""),
        "date":  datetime.now().isoformat()
    })
    save_json(REJECTED_FILE, profile)

# ── Affiliate Checker ────────────────────────────────────────────────

KNOWN_AFFILIATE_PROGRAMS = {
    # -- Already registered --  (GTHIC removed 2026-08 — jewelry brand, off-niche)
    "amazon.com":             {"program": "Amazon Associates", "commission": "4%",        "our_id": "thegothicvaul-20"},
    "killstar.com":           {"program": "ShareASale",        "commission": "10%",       "our_id": None},
    "restyle.pl":             {"program": "ShareASale",        "commission": "15%",       "our_id": None},
    "darkinlove.com":         {"program": "Direct",            "commission": "15%",       "our_id": None},
    "alchemy.co.uk":          {"program": "Viglink",           "commission": "8%",        "our_id": None},
    "burleska.co.uk":         {"program": "ShareASale",        "commission": "10%",       "our_id": None},
    "skintwo.com":            {"program": "GoAffPro",          "commission": "15%",       "our_id": None},
    "vexclothing.com":        {"program": "Refersion",         "commission": "TBD",       "our_id": None},
    "libidex.com":            {"program": "Direct",            "commission": "TBD",       "our_id": None},
    "dollskill.com":          {"program": "Unknown",           "commission": "TBD",       "our_id": None},

    # -- Found via Wasteland.nl research — REGISTER ASAP --
    "shwomenstore.com":       {"program": "UpPromote",         "commission": "10%",       "our_id": None},  # signup: af.uppromote.com/sh-womenstore/register
    "honour.co.uk":           {"program": "Paid On Results",   "commission": "10-15%",    "our_id": None},  # signup: paidonresults.com/merchants/honour.html
    "cocodemeruk.com":        {"program": "FlexOffers",        "commission": "TBD",       "our_id": None},  # signup: flexoffers.com
    "bdsmstore.de":           {"program": "In-house",          "commission": "10-15%",    "our_id": None},  # tiered, signup: affiliate-marketing.de
    "pleasurements.com":      {"program": "Direct",            "commission": "10%",       "our_id": None},  # signup: pleasurements.com/affiliate

    # -- Gothic Footwear — REGISTER ASAP --
    "tukshoes.co.uk":         {"program": "TradeTracker",      "commission": "TBD",       "our_id": None},  # signup: tukshoes.co.uk/pages/affiliates — gothic/punk/platform heels
    "rivithead.com":          {"program": "Direct",            "commission": "10%",       "our_id": None},  # signup: rivithead.com (check footer) — fetish/gothic shoes
    # Demonia (demoniacult.com) — affiliate program CLOSED
    # Pleaser USA (pleaserusa.com) — wholesale only; sell via Amazon Associates (thegothicvaul-20)
}

def check_affiliate(url):
    """Check if URL domain has a known affiliate program."""
    for domain, info in KNOWN_AFFILIATE_PROGRAMS.items():
        if domain in url:
            return info
    return None

def is_pinterest_safe(url):
    """
    Returns False if the URL belongs to a domain blocked on Pinterest.
    These domains contain adult/fetish content that violates Pinterest policy.
    """
    for domain in PINTEREST_BLOCKED_DOMAINS:
        if domain in url:
            return False
    return True

def generate_outreach_email(brand_name, brand_url, product_url):
    """Generate affiliate outreach email for brands without programs."""
    return f"""Subject: Affiliate Partnership Inquiry — TheGothicVault

Hi {brand_name} team,

I run TheGothicVault, a gothic fashion & jewelry content channel with a highly engaged
dark aesthetic audience. I recently discovered your product ({product_url}) and I love
the aesthetic — it's exactly what my audience looks for.

I'd love to explore an affiliate partnership where I feature your products in my content
and drive qualified traffic to your store. Do you have an affiliate program, or would
you be open to a direct commission arrangement?

Looking forward to hearing from you.

TheGothicVault
{brand_url and 'https://thestilettovault.com' or ''}
affiliatesbybold@gmail.com
"""

# ── Daily Review Sync ─────────────────────────────────────────────────

def sync_daily_review(inbox_id, review_id):
    """
    Compare what Claude pinned to DAILY REVIEW vs what's still there.
    What user deleted = rejected. What remains = approved.
    Updates taste profiles.
    """
    print("\nSyncing taste from DAILY REVIEW...")

    # Load what we pinned yesterday
    log_file = os.path.join(DATA_DIR, "last_review_pins.json")
    last_pins = load_json(log_file, {})

    if not last_pins:
        print("  No previous review session found.")
        return

    # Get what's still on the board
    current_pins = {p["id"]: p for p in get_pins_on_board(review_id)}

    approved_count  = 0
    rejected_count  = 0

    # Load dedup list so we can free up reviewed URLs
    pinned_urls = set(load_json(PINNED_URLS_FILE, []))

    for pin_id, pin_data in last_pins.items():
        url = pin_data.get("link") or pin_data.get("title", "")
        if pin_id in current_pins:
            record_approval(pin_data)
            approved_count += 1
        else:
            record_rejection(pin_data)
            rejected_count += 1
            # Free the URL from dedup so it can resurface after 30+ days
            pinned_urls.discard(url)

    save_json(PINNED_URLS_FILE, list(pinned_urls))
    print(f"  Approved: {approved_count} | Rejected: {rejected_count}")

    # Clear the log
    save_json(log_file, {})

# ── Main Pipeline ────────────────────────────────────────────────────

def run_daily_pipeline():
    """
    Main daily job:
    1. Sync taste signals from yesterday's approved/rejected products
    2. Scout affiliate sites directly → get list of new products
    3. Also pull any manual pins from ZAMNAI Pinterest board (optional bonus)
    4. Score + sort by taste, send to Telegram Taste Bot
    """
    print(f"\n{'='*50}")
    print(f"Gothic Scout — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    # Step 1: Learn from yesterday's taste signals
    try:
        inbox_id, review_id = setup_boards()
        sync_daily_review(inbox_id, review_id)
    except Exception as e:
        print(f"  (Pinterest sync skipped: {e})")

    # Load dedup list — normalize URLs so query-param variants of same product are caught
    pinned_urls = set(normalize_url(u) for u in load_json(PINNED_URLS_FILE, []))

    # ── Step 2: Scout affiliate sites directly (no Pinterest needed) ──
    candidates = []  # list of dicts: {url, title, image_url, commission, domain}

    try:
        from product_scout import run_scout
        scouted = run_scout(max_products=25)
        for p in scouted:
            url = p["url"]
            if normalize_url(url) in pinned_urls:
                print(f"  SKIP  {url[:60]} -> already sent")
                continue
            candidates.append({
                "url":        url,
                "title":      p["title"],
                "image_url":  p["image"],
                "commission": p["affiliate"].get("commission", ""),
                "domain":     p["domain"],
            })
        print(f"\n  Scout added {len(candidates)} new candidates")
    except Exception as e:
        print(f"  Product scout error: {e}")

    # ── Step 3: Also check manual ZAMNAI Pinterest board (optional) ──
    try:
        import requests as _req
        _prod_token = os.getenv("PINTEREST_PROD_TOKEN") or ACCESS_TOKEN
        _r = _req.get(
            f"https://api.pinterest.com/v5/boards/{BOARD_ZAMNAI}/pins",
            headers={"Authorization": f"Bearer {_prod_token}"},
            params={"page_size": 25},
            timeout=10
        )
        if _r.ok:
            inbox_pins = _r.json().get("items", [])
            print(f"\n  ZAMNAI board: {len(inbox_pins)} manual pins")
            for pin in inbox_pins:
                url = pin.get("link") or pin.get("title", "")
                if not url or normalize_url(url) in pinned_urls:
                    continue
                affiliate = check_affiliate(url)
                if not affiliate:
                    continue
                # Avoid duplicates already added by scout
                if any(c["url"] == url for c in candidates):
                    continue
                media = pin.get("media", {})
                image_url = (
                    media.get("images", {}).get("originals", {}).get("url") or
                    media.get("images", {}).get("1200x", {}).get("url") or ""
                )
                candidates.append({
                    "url":        url,
                    "title":      pin.get("title") or url[:80],
                    "image_url":  image_url,
                    "commission": affiliate.get("commission", ""),
                    "domain":     next((d for d in KNOWN_AFFILIATE_PROGRAMS if d in url), ""),
                })
    except Exception as e:
        print(f"  (ZAMNAI board skipped: {e})")

    if not candidates:
        from telegram_sender import send_summary
        send_summary(0)
        print("\nאין מוצרים חדשים להיום.")
        return

    # ── Step 4: Score, sort, send ─────────────────────────────────────
    from taste_engine import score_product
    candidates.sort(
        key=lambda c: score_product(c["url"], c["title"]),
        reverse=True
    )

    print(f"\nשולח {len(candidates)} מוצרים ל-Telegram Taste Bot...")
    from telegram_sender import send_product, send_summary

    sent = 0
    for c in candidates:
        ok = send_product(
            url=c["url"],
            title=c["title"],
            commission=c["commission"],
            image_url=c["image_url"],
            domain=c["domain"],
        )
        if ok:
            pinned_urls.add(normalize_url(c["url"]))
            sent += 1
            print(f"  ✅ {c['url'][:60]}")
        time.sleep(1)

    save_json(PINNED_URLS_FILE, list(pinned_urls))
    send_summary(sent)
    print(f"\nסיום. {sent} מוצרים נשלחו ל-Telegram Taste Bot.")

# ── Test Connection ──────────────────────────────────────────────────

def test_connection():
    """Quick test to verify API credentials work."""
    print("Testing Pinterest API connection...")
    try:
        r = requests.get(f"{BASE_URL}/user_account", headers=headers(write=True))
        r.raise_for_status()
        data = r.json()
        print(f"  Connected as: {data.get('username', 'unknown')}")
        print(f"  Business name: {data.get('business_name', 'unknown')}")
        return True
    except Exception as e:
        print(f"  Connection failed: {e}")
        return False

# ── Entry Point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pipeline"

    if cmd == "test":
        test_connection()
    elif cmd == "setup":
        setup_boards()
    elif cmd == "pipeline":
        run_daily_pipeline()
    else:
        print(f"Usage: python gothic_scout.py [test|setup|pipeline]")
