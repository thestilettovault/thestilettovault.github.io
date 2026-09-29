# -*- coding: utf-8 -*-
"""engagement.py — likes / views / followers from Zernio analytics (Control Center).

Zernio syncs platform analytics roughly hourly and follower counts ~daily, so this is
"near real time": we cache 5 min and the UI diffs against the last seen totals to fire
a toast + sound on new likes / followers.

Shapes (verified 2026-09-29):
  GET /analytics?page=N&limit=50 → {posts:[{_id, latePostId, publishedAt, platforms:[{platform}],
       analytics:{views,likes,comments,shares,saves,follows,...}}], pagination:{pages}}
  GET /accounts → {accounts:[{platform, username, followersCount, followersLastUpdated}]}
latePostId == the post _id returned by GET /posts (used to join onto the schedule).
"""
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
TTL = 300
METRICS = ("views", "likes", "comments", "shares", "saves", "follows")

_LOCK = threading.Lock()
_CACHE = {"at": 0.0, "data": None}


def _client():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import social_publisher as sp
    return sp.ZERNIO_API_URL, {"Authorization": "Bearer " + sp.ZERNIO_API_KEY}


def _fetch():
    import requests
    base, hdr = _client()
    posts, page = [], 1
    while page <= 20:
        r = requests.get(base + "/analytics", headers=hdr, params={"page": page, "limit": 50}, timeout=30)
        r.raise_for_status()
        j = r.json()
        batch = j.get("posts") or []
        posts += batch
        pages = (j.get("pagination") or {}).get("pages") or 1
        if not batch or page >= pages:
            break
        page += 1
    acc = requests.get(base + "/accounts", headers=hdr, timeout=30)
    acc.raise_for_status()
    accounts = acc.json().get("accounts") or []

    totals = {m: 0 for m in METRICS}
    by_platform, per_post = {}, {}
    for p in posts:
        a = p.get("analytics") or {}
        plat = ((p.get("platforms") or [{}])[0] or {}).get("platform", "")
        row = {m: int(a.get(m) or 0) for m in METRICS}
        for m in METRICS:
            totals[m] += row[m]
            by_platform.setdefault(plat, {k: 0 for k in METRICS})[m] += row[m]
        row["platform"] = plat
        row["published_at"] = p.get("publishedAt")
        row["updated"] = a.get("lastUpdated")
        for key in {p.get("latePostId"), p.get("_id")} - {None}:
            per_post[key] = row
    try:
        pin = _pinterest()
    except Exception as ex:
        pin = {"connected": False, "error": str(ex)[:120]}
    followers = {a.get("platform"): {"count": a.get("followersCount"),
                                    "updated": a.get("followersLastUpdated"),
                                    "username": a.get("username")} for a in accounts}
    try:
        import admitad_stats
        conv = admitad_stats.fetch_conversions()
        sales = {"total": conv.get("total_sales", 0), "commission": conv.get("commission_all", 0.0),
                 "by_channel": conv.get("by_channel", {}), "source": "admitad"}
    except Exception as ex:
        sales = {"total": None, "error": str(ex)[:120]}
    if pin.get("connected"):
        followers["pinterest"] = {"count": pin.get("followers"), "updated": None, "username": pin.get("username")}
    return {
        "pinterest": pin,
        "sales": sales,
        "totals": totals,
        "by_platform": by_platform,
        "followers": followers,
        "followers_total": sum((f.get("count") or 0) for f in followers.values()),
        "posts_count": len(posts),
        "per_post": per_post,
        "fetched_at": time.time(),
    }


def _pinterest():
    """Pinterest v5 (read-only; the app is on Trial access → reading works, publishing doesn't)."""
    import datetime
    import os
    import requests
    from dotenv import load_dotenv
    load_dotenv(SCRIPTS / ".env")
    tok = os.getenv("PINTEREST_ACCESS_TOKEN")
    if not tok:
        return {"connected": False, "error": "PINTEREST_ACCESS_TOKEN missing"}
    h = {"Authorization": "Bearer " + tok}
    u = requests.get("https://api.pinterest.com/v5/user_account", headers=h, timeout=20)
    if not u.ok:
        return {"connected": False, "error": f"user_account {u.status_code}"}
    u = u.json()
    end = datetime.date.today()
    start = end - datetime.timedelta(days=29)
    m = {}
    a = requests.get("https://api.pinterest.com/v5/user_account/analytics", headers=h, timeout=20,
                     params={"start_date": start.isoformat(), "end_date": end.isoformat(),
                             "metric_types": "IMPRESSION,SAVE,PIN_CLICK,OUTBOUND_CLICK"})
    if a.ok:
        m = ((a.json().get("all") or {}).get("summary_metrics")) or {}
    return {"connected": True, "username": u.get("username"),
            "followers": u.get("follower_count"), "pins": u.get("pin_count"),
            "monthly_views": u.get("monthly_views"), "boards": u.get("board_count"),
            "impressions_30d": m.get("IMPRESSION", 0), "saves_30d": m.get("SAVE", 0),
            "pin_clicks_30d": m.get("PIN_CLICK", 0), "outbound_clicks_30d": m.get("OUTBOUND_CLICK", 0),
            "publishing": "blocked (Trial access)"}


def get(fresh=False):
    with _LOCK:
        if not fresh and _CACHE["data"] and time.time() - _CACHE["at"] < TTL:
            d = dict(_CACHE["data"])
            d["cached_seconds_ago"] = int(time.time() - _CACHE["at"])
            return d
    try:
        data = _fetch()
    except Exception as e:
        with _LOCK:
            if _CACHE["data"]:
                d = dict(_CACHE["data"]); d["stale_error"] = str(e)[:160]
                return d
        return {"error": str(e)[:200]}
    with _LOCK:
        _CACHE.update(at=time.time(), data=data)
    d = dict(data); d["cached_seconds_ago"] = 0
    return d


def summary(fresh=False):
    """Small per-channel counters for the header poll (no per-post payload)."""
    d = get(fresh=fresh)
    if d.get("error"):
        return {}
    bp = d.get("by_platform", {})
    pin = d.get("pinterest") or {}
    ch = {}
    for plat in ("tiktok", "instagram"):
        b = bp.get(plat, {})
        ch[plat] = {"followers": (d["followers"].get(plat) or {}).get("count"),
                    "likes": b.get("likes", 0), "comments": b.get("comments", 0),
                    "views": b.get("views", 0), "shares": b.get("shares", 0)}
    ch["pinterest"] = {"followers": pin.get("followers"), "saves": pin.get("saves_30d", 0),
                       "outbound": pin.get("outbound_clicks_30d", 0), "impressions": pin.get("impressions_30d", 0),
                       "connected": bool(pin.get("connected"))}
    return {"likes": d["totals"]["likes"], "views": d["totals"]["views"],
            "comments": d["totals"]["comments"],
            "followers_total": sum((c.get("followers") or 0) for c in ch.values()),
            "followers": {k: c.get("followers") for k, c in ch.items()},
            "channels": ch, "sales": d.get("sales") or {}, "fetched_at": d.get("fetched_at")}
