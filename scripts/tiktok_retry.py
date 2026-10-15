# -*- coding: utf-8 -*-
"""
tiktok_retry.py — self-healing for TikTok "at capacity" failures.

TikTok direct posting shares a rate-limited pool on Zernio; clustering several
posts in a short window trips "TikTok direct posting is at capacity" and the post
lands as `status:failed` with attempts:0 (usage refunded — it was never tried).
This is NOT a media/content problem and NOT a reason to switch to draft mode.

The fix that keeps distribution fully automatic: find failed TikTok posts and
re-slot them into future openings, capped per day and spread across the day so
we never cluster again. A revive is just PUT /posts/{id} {scheduledFor} — that
flips a failed post back to `scheduled` (PATCH returns 405; PUT works).

Run it after each publishing window (wired into run_producer.bat) so capacity
failures self-heal the next morning without a human.

Usage:
    py -3 tiktok_retry.py            # dry-run (print the re-slot plan)
    py -3 tiktok_retry.py --apply    # PUT new scheduledFor on each failed post
"""
import os, sys, io, re, argparse, requests
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

K = os.getenv("ZERNIO_API_KEY")
U = os.getenv("ZERNIO_API_URL", "https://zernio.com/api/v1").rstrip("/")   # same env + default as social_publisher
H = {"Authorization": f"Bearer {K}", "Content-Type": "application/json"}

MAX_TT_PER_DAY = 1                     # Ofer 2026-10-15: one TikTok post a day (capacity errors at 2-3)
IL             = ZoneInfo("Asia/Jerusalem")
SLOT_TIMES     = ["16:00"]           # LOCAL Israel time (same slot as the image posts); converted to UTC per day (DST-safe)
REVIVE_MAX_AGE_DAYS = 14             # never resurrect a failed post older than this
TRANSIENT_RE   = re.compile(r"capacity|rate.?limit|too many|throttl|temporar|try again|\b429\b|\b503\b", re.I)


def parse_ts(v):
    """Zernio timestamp -> aware UTC datetime ('...Z', '+00:00' or naive-as-UTC)."""
    dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def slot_utc(d, hhmm):
    """Local Israel day `d` + 'HH:MM' -> aware UTC datetime (13:00Z in summer, 14:00Z in winter for 16:00)."""
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=IL).astimezone(timezone.utc)


def iso_z(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:00.000Z")


def local_key(scheduled_for):
    """(local Israel date iso, 'HH:MM') for a Zernio UTC timestamp - the unit 'taken' slots are compared in."""
    loc = parse_ts(scheduled_for).astimezone(IL)
    return loc.date().isoformat(), loc.strftime("%H:%M")


def _error_text(p):
    bits = [p.get("errorMessage"), p.get("error"), p.get("failureReason")]
    for x in p.get("platforms") or []:
        bits += [x.get("errorMessage"), x.get("error"), x.get("failureReason"), x.get("errorCategory")]
    return " | ".join(str(b) for b in bits if b)


def _attempts(p):
    vals = [p.get("attempts")] + [x.get("attempts") for x in (p.get("platforms") or [])]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return min(vals) if vals else None


def revivable(p, now=None):
    """(ok, reason). Revive only recent failures that look transient (capacity / rate
    limit / never attempted). If the post carries no error info at all we can't tell,
    so we fall back to the age filter alone."""
    now = now or datetime.now(timezone.utc)
    try:
        age = now - parse_ts(p["scheduledFor"])
    except Exception:
        return False, "unreadable scheduledFor"
    if age > timedelta(days=REVIVE_MAX_AGE_DAYS):
        return False, f"older than {REVIVE_MAX_AGE_DAYS} days"
    text, attempts = _error_text(p), _attempts(p)
    if text:
        if TRANSIENT_RE.search(text) or attempts == 0:
            return True, "transient error"
        return False, f"non-transient error: {text[:60]}"
    if attempts == 0:
        return True, "never attempted"
    return True, "no error text; age ok"


def is_tt(p):
    return any(x["platform"] == "tiktok" for x in p["platforms"])


def load_posts():
    out, page = [], 1
    while True:   # all pages: one page is capped at 200 posts
        r = requests.get(f"{U}/posts", headers=H, params={"limit": 200, "page": page}, timeout=30)
        r.raise_for_status()
        j = r.json()
        if not isinstance(j, dict) or "posts" not in j:
            raise RuntimeError(f"Zernio /posts: unexpected response (no 'posts' key): {str(j)[:200]}")
        out += j["posts"]
        if page >= int((j.get("pagination") or {}).get("pages") or 1):
            return out
        page += 1


def next_slots(load, taken, n, start):
    """Yield n (date, time) openings from `start`, skipping Saturday, keeping
    each day <= MAX_TT_PER_DAY and using distinct SLOT_TIMES per day.
    `d` and the returned times are LOCAL (Israel) - see slot_utc() for the UTC instant."""
    out, d = [], start
    while len(out) < n:
        key = d.isoformat()
        if d.weekday() != 5 and load[key] < MAX_TT_PER_DAY:
            for t in SLOT_TIMES:
                if (key, t) in taken[key]:
                    continue
                out.append((d, t)); taken[key].add(t); load[key] += 1
                if load[key] >= MAX_TT_PER_DAY or len(out) >= n:
                    break
        d += timedelta(days=1)
    return out


def main(apply=False):
    posts = load_posts()
    failed_all = sorted([p for p in posts if p["status"] == "failed" and is_tt(p)],
                        key=lambda p: parse_ts(p["scheduledFor"]))
    if not failed_all:
        print("No failed TikTok posts — nothing to heal."); return
    failed = []
    for p in failed_all:
        ok, why = revivable(p)
        if ok:
            failed.append(p)
        else:
            print(f"  skip {p['scheduledFor'][:16]}  ({why})  | {p['content'][:34]}")
    if not failed:
        print("No revivable failed TikTok posts (all skipped)."); return

    # current TikTok load per future LOCAL day (scheduled posts we must not overfill)
    load  = defaultdict(int)
    taken = defaultdict(set)
    for p in posts:
        if p["status"] == "scheduled" and is_tt(p):
            d, t = local_key(p["scheduledFor"]); load[d] += 1; taken[d].add(t)

    start = (datetime.now(IL) + timedelta(days=1)).date()  # from tomorrow (Israel), fresh capacity
    slots = next_slots(load, taken, len(failed), start)

    print(f"Re-slotting {len(failed)} failed TikTok post(s), max {MAX_TT_PER_DAY}/day, "
          f"slots {SLOT_TIMES} Israel time:\n")
    plan = []
    for p, (d, t) in zip(failed, slots):
        newiso = iso_z(slot_utc(d, t))
        plan.append((p["_id"], newiso))
        print(f"  {p['scheduledFor'][:16]}  ->  {d.isoformat()} {t} ({d.strftime('%a')}) = {newiso[:16]}Z  | {p['content'][:34]}")

    if not apply:
        print(f"\nDRY-RUN. Re-run with --apply."); return
    ok = fail = 0
    for pid, newiso in plan:
        r = requests.put(f"{U}/posts/{pid}", headers=H, json={"scheduledFor": newiso}, timeout=30)
        if r.status_code in (200, 201): ok += 1
        else: fail += 1; print(f"  ! {pid} {r.status_code} {r.text[:120]}")
    print(f"\ndone: revived {ok}, fail {fail}")


def spread(apply=False):
    """Prevention pass: re-time ALL scheduled TikTok posts onto a capped, widely
    spread grid (<= MAX_TT_PER_DAY/day at SLOT_TIMES, skip Saturday), preserving
    chronological order and pushing overflow forward. Never clusters -> never
    trips the capacity limit. Only future posts are touched; dates only move when
    a day is over cap. IG posts are left untouched."""
    posts = load_posts()
    now = datetime.now(timezone.utc)
    sched = sorted([p for p in posts if p["status"] == "scheduled" and is_tt(p)
                    and parse_ts(p["scheduledFor"]) > now],
                   key=lambda p: parse_ts(p["scheduledFor"]))
    load, taken = defaultdict(int), defaultdict(set)
    start = (now.astimezone(IL) + timedelta(days=1)).date()
    slots = next_slots(load, taken, len(sched), start)
    moved = plan = 0
    print(f"Spreading {len(sched)} scheduled TikTok post(s), max {MAX_TT_PER_DAY}/day, slots {SLOT_TIMES} Israel time:\n")
    changes = []
    for p, (d, t) in zip(sched, slots):
        new_dt = slot_utc(d, t)
        newiso = iso_z(new_dt)
        if new_dt == parse_ts(p["scheduledFor"]):
            continue
        changes.append((p["_id"], p["scheduledFor"], newiso, p["content"][:30]))
    for _pid, old, new, c in changes:
        print(f"  {old[:16]}  ->  {new[:16]}  | {c}")
    if not changes:
        print("  (already well spread — nothing to do)"); return
    if not apply:
        print(f"\nDRY-RUN. {len(changes)} would move. Re-run with --spread --apply."); return
    ok = fail = 0
    for pid, old, new, c in changes:
        r = requests.put(f"{U}/posts/{pid}", headers=H, json={"scheduledFor": new}, timeout=30)
        if r.status_code in (200, 201): ok += 1
        else: fail += 1; print(f"  ! {pid} {r.status_code} {r.text[:120]}")
    print(f"\ndone: moved {ok}, fail {fail}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--spread", action="store_true",
                    help="prevention: re-time ALL scheduled TikTok posts onto a capped spread grid")
    a = ap.parse_args()
    (spread if a.spread else main)(a.apply)
