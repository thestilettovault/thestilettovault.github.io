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
import os, sys, io, argparse, requests
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

K = os.getenv("ZERNIO_API_KEY"); U = "https://zernio.com/api/v1"
H = {"Authorization": f"Bearer {K}", "Content-Type": "application/json"}

MAX_TT_PER_DAY = 1                     # Ofer 2026-10-15: one TikTok post a day (capacity errors at 2-3)
SLOT_TIMES     = ["13:00"]           # 16:00 Israel, same slot as the image posts


def is_tt(p):
    return any(x["platform"] == "tiktok" for x in p["platforms"])


def load_posts():
    out, page = [], 1
    while True:   # all pages: one page is capped at 200 posts
        j = requests.get(f"{U}/posts", headers=H, params={"limit": 200, "page": page}).json()
        out += j.get("posts", [])
        if page >= int((j.get("pagination") or {}).get("pages") or 1):
            return out
        page += 1


def next_slots(load, taken, n, start):
    """Yield n (date, time) openings from `start`, skipping Saturday, keeping
    each day <= MAX_TT_PER_DAY and using distinct SLOT_TIMES per day."""
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
    failed = sorted([p for p in posts if p["status"] == "failed" and is_tt(p)],
                    key=lambda p: p["scheduledFor"])
    if not failed:
        print("No failed TikTok posts — nothing to heal."); return

    # current TikTok load per future day (scheduled posts we must not overfill)
    load  = defaultdict(int)
    taken = defaultdict(set)
    for p in posts:
        if p["status"] == "scheduled" and is_tt(p):
            d = p["scheduledFor"][:10]; load[d] += 1; taken[d].add(p["scheduledFor"][11:16])

    start = (datetime.now(timezone.utc) + timedelta(days=1)).date()  # from tomorrow, fresh capacity
    slots = next_slots(load, taken, len(failed), start)

    print(f"Re-slotting {len(failed)} failed TikTok post(s), max {MAX_TT_PER_DAY}/day, "
          f"slots {SLOT_TIMES} UTC:\n")
    plan = []
    for p, (d, t) in zip(failed, slots):
        newiso = f"{d.isoformat()}T{t}:00.000Z"
        plan.append((p["_id"], newiso))
        print(f"  {p['scheduledFor'][:16]}  ->  {d.isoformat()} {t} ({d.strftime('%a')})  | {p['content'][:34]}")

    if not apply:
        print(f"\nDRY-RUN. Re-run with --apply."); return
    ok = fail = 0
    for pid, newiso in plan:
        r = requests.put(f"{U}/posts/{pid}", headers=H, json={"scheduledFor": newiso})
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
                    and p["scheduledFor"] > now.isoformat()],
                   key=lambda p: p["scheduledFor"])
    load, taken = defaultdict(int), defaultdict(set)
    start = (now + timedelta(days=1)).date()
    slots = next_slots(load, taken, len(sched), start)
    moved = plan = 0
    print(f"Spreading {len(sched)} scheduled TikTok post(s), max {MAX_TT_PER_DAY}/day, slots {SLOT_TIMES} UTC:\n")
    changes = []
    for p, (d, t) in zip(sched, slots):
        newiso = f"{d.isoformat()}T{t}:00.000Z"
        if newiso == p["scheduledFor"]:
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
        r = requests.put(f"{U}/posts/{pid}", headers=H, json={"scheduledFor": new})
        if r.status_code in (200, 201): ok += 1
        else: fail += 1; print(f"  ! {pid} {r.status_code} {r.text[:120]}")
    print(f"\ndone: moved {ok}, fail {fail}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--spread", action="store_true",
                    help="prevention: re-time ALL scheduled TikTok posts onto a capped spread grid")
    a = ap.parse_args()
    (spread if a.spread else main)(a.apply)
