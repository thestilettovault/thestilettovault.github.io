# -*- coding: utf-8 -*-
"""
social_publisher.py — publish heel drops to TikTok + Instagram via Zernio.

Zernio (https://zernio.com) is a hosted REST API + MCP server that posts to 16
social platforms. The FIRST 2 CONNECTED ACCOUNTS ARE FREE (no card) — so one
Instagram + one TikTok cost nothing. No TikTok/Meta app review on our side.

ONE-TIME SETUP (Ofer):
  1. Sign up at zernio.com, connect Instagram + TikTok via their OAuth
     (GET /v1/connect/url per platform).
  2. Create an API key.
  3. Note each connected account's id.
  4. Put these in scripts/.env:
       ZERNIO_API_URL=https://api.zernio.com          # or the base shown in your dashboard
       ZERNIO_API_KEY=<key>
       ZERNIO_INSTAGRAM_ID=<instagram account id>
       ZERNIO_TIKTOK_ID=<tiktok account id>

Media: Zernio takes media BY URL (not file upload). The Magnific Space output
is already a hosted URL — store it on the catalog item as `video_url` and it
flows straight through. (A local-only mp4 must first be hosted somewhere public,
e.g. pushed to the GitHub Pages repo.)

Behaviour:
  • Selects catalog items with variations_ready=true and posted!=true
  • Uses item['video_url'] (hosted) as the post media
  • Builds caption + 5-8 hashtags + affiliate CTA
  • Schedules to TikTok + Instagram at the next 22:00 Israel slot
  • Marks the item posted=true

Usage:
    python social_publisher.py            # DRY RUN — prints payloads, no API call
    python social_publisher.py --publish  # actually schedule via Zernio
"""
import sys, os, re, json, argparse, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8") if sys.stdout else None
sys.path.insert(0, os.path.dirname(__file__))
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

ROOT         = Path(__file__).resolve().parent.parent
CATALOG_FILE = ROOT / "data" / "approved_catalog.json"
GELEM_DIR    = ROOT / "GELEM"

ZERNIO_API_URL      = os.getenv("ZERNIO_API_URL", "https://zernio.com/api/v1").rstrip("/")
ZERNIO_API_KEY      = os.getenv("ZERNIO_API_KEY", "")
ZERNIO_TIKTOK_ID    = os.getenv("ZERNIO_TIKTOK_ID", "")
ZERNIO_INSTAGRAM_ID = os.getenv("ZERNIO_INSTAGRAM_ID", "")

SITE_URL = "https://thestilettovault.github.io"   # link-in-bio target

# 5-8 tags per post, mixing niche + reach (per reference_posting_schedule)
HASHTAGS = ["#heels", "#stilettoheels", "#darkfashion", "#gothicfashion",
            "#shoelover", "#heelsaddict", "#altfashion", "#statementheels"]

# A "drop" = 3 posts for one heel, spread across the day at 3 different times.
# 22:00 IL is the proven optimal slot (reference_posting_schedule); the two
# earlier slots build reach ahead of it. Override with --slots HH:MM,HH:MM,HH:MM.
DEFAULT_SLOTS = ["14:00", "18:00", "22:00"]


def load_catalog():
    if not CATALOG_FILE.exists():
        return []
    with open(CATALOG_FILE, encoding="utf-8-sig") as f:
        return json.load(f)


def save_catalog(catalog):
    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)


def slugify(item):
    url = item.get("url", "")
    m = re.search(r"/products/([^/?#]+)", url)
    base = m.group(1) if m else item.get("title", "item")
    return (re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:60]) or "item"


def media_url(item):
    """Hosted video URL for the post (Magnific Space output preferred)."""
    return item.get("video_url") or item.get("media_url") or ""


def build_caption(item):
    title = item.get("title", "").strip()
    # Include the deal so each heel's caption is unique — the raw title is generic
    # ("Stiletto Heels"/"Pointed-Toe Pump") and Zernio rejects duplicate content (409).
    deal = item.get("deal", {}) or {}
    disc = str(deal.get("discount", "") or "").strip()
    sale = deal.get("sale")
    headline = title
    if disc and disc not in ("0%", "0", ""):
        headline += f" · {disc} OFF"
    if sale:
        headline += f" · ${sale}"
    coupon = "OFERRABIN" if "darkinlove.com" in item.get("domain", "") else None
    lines = [f"{headline} 🖤"]
    if coupon:
        lines.append(f"Use code {coupon} for $10 off")
    lines.append(f"Shop the link in bio → {SITE_URL}")
    lines.append("")
    lines.append(" ".join(HASHTAGS[:7]))
    return "\n".join(lines)


def next_2200_israel():
    now = datetime.datetime.now()
    slot = now.replace(hour=22, minute=0, second=0, microsecond=0)
    if now >= slot:
        slot += datetime.timedelta(days=1)
    return slot.isoformat()


def pending():
    return [it for it in load_catalog()
            if it.get("variations_ready") and not it.get("posted")]


def resolve_media(item):
    """(url, type) for the post. Prefer a hosted video, else the hosted image."""
    if item.get("video_url"):
        return item["video_url"], "video"
    if item.get("media_url"):
        return item["media_url"], "video"
    if item.get("image_url", "").startswith("http"):
        return item["image_url"], "image"
    return "", ""


# TikTok requires these to DIRECT-POST (video.publish). Without them Zernio can only
# drop the video into the TikTok inbox as a draft ("awaiting-finalize"), so nothing
# goes live until the user finalises it in the app.
TIKTOK_SETTINGS = {
    "privacy_level": "PUBLIC_TO_EVERYONE",
    "allow_comment": True,
    "allow_duet": True,
    "allow_stitch": True,
    "content_preview_confirmed": True,
    "express_consent_given": True,
}

def _zernio_post(content, platform, account_id, media_url, media_type,
                 scheduled_for=None, platform_data=None):
    """One Zernio post to a single platform. `media_url` may be a single URL or a
    list of URLs. `platform_data` → platformSpecificData (e.g. Instagram Reel feed
    sharing). Returns (ok, info)."""
    urls = media_url if isinstance(media_url, (list, tuple)) else [media_url]
    media_items = [{"type": media_type, "url": u} for u in urls if u]
    target = {"platform": platform, "accountId": account_id}
    if platform_data:
        target["platformSpecificData"] = platform_data
    payload = {
        "content": content,
        "scheduledFor": scheduled_for or SCHEDULE_LOCAL,   # e.g. 2026-08-10T22:00:00
        "timezone": "Asia/Jerusalem",
        "platforms": [target],
        "mediaItems": media_items,
    }
    # TikTok VIDEO direct-posting is chronically throttled ("at capacity" /
    # tiktokUnreachableAttempts) even with a healthy connection — it caused a
    # 10-day publishing gap (2026-09). Deliver video via the Creator Inbox as a
    # draft (a different, un-throttled path); Ofer taps publish in the app. Images
    # go out direct (they are light and reliable). Root-level tiktokSettings must
    # be sent together with `platforms` in the same request (Zernio requirement).
    if platform == "tiktok" and media_type == "video":
        payload["tiktokSettings"] = {"draft": True}
    import requests
    r = requests.post(
        f"{ZERNIO_API_URL}/posts",
        headers={"Authorization": f"Bearer {ZERNIO_API_KEY}", "Content-Type": "application/json"},
        json=payload, timeout=60,
    )
    return r.ok, f"{r.status_code}: {r.text[:160]}"


# next 22:00 Israel as a naive local ISO string (paired with timezone above)
_slot = datetime.datetime.now().replace(hour=22, minute=0, second=0, microsecond=0)
if datetime.datetime.now() >= _slot:
    _slot += datetime.timedelta(days=1)
SCHEDULE_LOCAL = _slot.strftime("%Y-%m-%dT%H:%M:%S")


def publish(item, do_publish):
    slug = slugify(item)
    media_url, media_type = resolve_media(item)
    if not media_url:
        print(f"  ! {slug}: no hosted media (video_url/image_url) — skipping")
        return False

    full_caption = build_caption(item)
    # TikTok PHOTO posts use content as a slideshow title capped at 90 chars.
    tiktok_caption = full_caption if media_type == "video" else \
        f"{item.get('title','').strip()[:60]} 🖤 thestilettovault.github.io"

    targets = []
    if ZERNIO_INSTAGRAM_ID:
        targets.append(("instagram", ZERNIO_INSTAGRAM_ID, full_caption))
    if ZERNIO_TIKTOK_ID:
        targets.append(("tiktok", ZERNIO_TIKTOK_ID, tiktok_caption))
    if not targets:
        print(f"  ! {slug}: no Zernio account IDs configured — skipping")
        return False

    if not do_publish:
        print(f"  [DRY RUN] {slug} ({media_type}) @ {SCHEDULE_LOCAL} → {[t[0] for t in targets]}")
        print("  media: " + media_url[:70])
        return False
    if not ZERNIO_API_KEY:
        print("  ! ZERNIO_API_KEY not set — cannot publish")
        return False

    any_ok = False
    for platform, account_id, content in targets:
        try:
            ok, info = _zernio_post(content, platform, account_id, media_url, media_type)
            print(f"  {'✅' if ok else '!'} {slug} → {platform}: {info}")
            any_ok = any_ok or ok
        except Exception as e:
            print(f"  ! {slug} → {platform} failed: {e}")

    if any_ok:
        catalog = load_catalog()
        for it in catalog:
            if it.get("url") == item.get("url"):
                it["posted"] = True
                it["posted_date"] = datetime.datetime.now().isoformat()
        save_catalog(catalog)
    return any_ok


# ── Drop scheduling (3 posts / day / heel) ────────────────────────────

def slot_iso(hhmm, base=None):
    """Next occurrence of HH:MM as a naive local ISO string (today if still
    ahead, else tomorrow). Paired with timezone Asia/Jerusalem in the payload."""
    base = base or datetime.datetime.now()
    h, m = (int(x) for x in hhmm.split(":"))
    slot = base.replace(hour=h, minute=m, second=0, microsecond=0)
    if base >= slot:
        slot += datetime.timedelta(days=1)
    return slot.strftime("%Y-%m-%dT%H:%M:%S")


def find_by_slug(want):
    for it in load_catalog():
        if slugify(it) == want:
            return it
    return None


def drop_assets(item):
    """Dynamic posts for a heel drop — reflects whatever the folder actually holds
    (variable per shoe). Each VIDEO becomes its own post (IG video[i] paired with
    TikTok video[i]); all images per platform become ONE carousel post.
    Each post: {label, media_type, ig, tk} where ig/tk is a URL (video) or a list
    of URLs (image carousel). Falls back to the legacy single-asset keys."""
    a = item.get("assets", {}) or {}
    ig_v = a.get("videos_ig") or ([a["video"]] if a.get("video") else [])
    tt_v = a.get("videos_tt") or ([a["video"]] if a.get("video") else [])
    ig_i = a.get("images_ig") or [x for x in (a.get("image_1x1"),) if x]
    tt_i = a.get("images_tt") or [x for x in (a.get("image_9x16"),) if x]

    posts = []
    for i in range(max(len(ig_v), len(tt_v))):        # each video = its own post
        posts.append({
            "label": f"video {i+1}", "media_type": "video",
            "ig": ig_v[i] if i < len(ig_v) else None,
            "tk": tt_v[i] if i < len(tt_v) else None,
        })
    for i in range(max(len(ig_i), len(tt_i))):        # each image = its own post
        posts.append({
            "label": f"image {i+1}", "media_type": "image",
            "ig": ig_i[i] if i < len(ig_i) else None,
            "tk": tt_i[i] if i < len(tt_i) else None,
        })
    return [p for p in posts if p["ig"] or p["tk"]]


def schedule_drop(item, slots=None, do_publish=False, date=None):
    """Schedule one heel as 3 posts across the day (IG + TikTok each).
    `date` (a datetime.date or 'YYYY-MM-DD') pins the posts to a specific day —
    e.g. this heel's every-other-day slot — instead of the next free day."""
    slug  = slugify(item)
    slots = slots or DEFAULT_SLOTS
    posts = drop_assets(item)
    if not posts:
        print(f"  ! {slug}: no hosted assets (item['assets']) — run pickup_drop first")
        return False
    # Fit the number of time-slots to the number of posts (content varies per shoe).
    SLOT_POOL = ["12:00", "14:00", "16:00", "18:00", "20:00", "22:00"]
    if len(posts) <= len(slots):
        slots = slots[:len(posts)]
    else:
        pool = list(dict.fromkeys(list(slots) + SLOT_POOL))   # given slots first, then fill
        slots = pool[:len(posts)]
        if len(slots) < len(posts):                           # still short → space hourly
            slots = [f"{10 + i}:00" for i in range(len(posts))]

    base = None
    if date:
        if isinstance(date, str):
            date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        base = datetime.datetime.combine(date, datetime.time(0, 0))

    full_caption = build_caption(item)
    tiktok_img_caption = f"{item.get('title','').strip()[:60]} 🖤 thestilettovault.github.io"

    any_ok = False
    for post, hhmm in zip(posts, slots):
        when       = slot_iso(hhmm, base)
        label      = post["label"]
        media_type = post["media_type"]
        ig_caption = full_caption
        tk_caption = full_caption if media_type == "video" else tiktok_img_caption

        targets = []
        if ZERNIO_INSTAGRAM_ID and post["ig"]:
            targets.append(("instagram", ZERNIO_INSTAGRAM_ID, ig_caption, post["ig"]))
        if ZERNIO_TIKTOK_ID and post["tk"]:
            targets.append(("tiktok", ZERNIO_TIKTOK_ID, tk_caption, post["tk"]))

        if not do_publish:
            print(f"  [DRY RUN] {slug} · {label} @ {when} → {[t[0] for t in targets]}")
            for platform, _, _, murl in targets:
                print(f"            {platform}: {murl[:66]}")
            continue
        if not ZERNIO_API_KEY:
            print("  ! ZERNIO_API_KEY not set — cannot publish")
            return False
        for platform, account_id, content, media_url in targets:
            # Instagram video → Reel that also lands in the feed (post + reel).
            pdata = ({"shareToFeed": True}
                     if platform == "instagram" and media_type == "video" else None)
            try:
                ok, info = _zernio_post(content, platform, account_id,
                                        media_url, media_type, scheduled_for=when,
                                        platform_data=pdata)
                print(f"  {'✅' if ok else '!'} {slug} · {label} → {platform} @ {when}: {info}")
                any_ok = any_ok or ok
            except Exception as e:
                print(f"  ! {slug} · {label} → {platform} failed: {e}")

    if any_ok:
        catalog = load_catalog()
        for it in catalog:
            if it.get("url") == item.get("url"):
                it["posted"] = True
                it["posted_date"] = datetime.datetime.now().isoformat()
        save_catalog(catalog)
    return any_ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true", help="actually schedule via Zernio")
    ap.add_argument("--drop", metavar="SLUG",
                    help="schedule ONE heel as 3 posts across the day (2 images + 1 video)")
    ap.add_argument("--slots", default=",".join(DEFAULT_SLOTS),
                    help="comma-separated HH:MM times for the 3 drop posts")
    args = ap.parse_args()

    if args.drop:
        it = find_by_slug(args.drop)
        if not it:
            print(f"slug not found in catalog: {args.drop}")
            sys.exit(1)
        slots = [s.strip() for s in args.slots.split(",") if s.strip()]
        print(f"Scheduling drop '{args.drop}' → 3 posts @ {slots}"
              f"{' (DRY RUN — use --publish to send)' if not args.publish else ''}")
        schedule_drop(it, slots, args.publish)
    else:
        todo = pending()
        print(f"{len(todo)} product(s) ready to post"
              f"{' (DRY RUN — use --publish to send)' if not args.publish else ''}")
        for it in todo:
            publish(it, args.publish)
