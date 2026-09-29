# -*- coding: utf-8 -*-
"""One-click workflows for the control center.

Each workflow exposes:
  meta            -> {name, title_he, description_he, needs_confirm, est_duration}
  plan(params)    -> list[str] human-readable Hebrew steps (dry_run; never has side effects)
  steps(params)   -> list[dict] job steps for jobs.start() (the real run)

`run(name, dry_run, params)` is the single entry point the API calls.
"""
from __future__ import annotations

import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
DATA = ROOT / "data"
PY = "py"

from . import jobs as _jobs
from . import niche as _niche
from . import services as _services


def _sub(title, script_args, timeout=1800):
    return {"type": "subprocess", "title": title,
            "cmd": [PY, "-3"] + script_args, "cwd": str(ROOT), "timeout": timeout}


def _py(title, fn):
    return {"type": "python", "title": title, "fn": fn}


# ── shared: next free posting days ──────────────────────────────────

def _next_free_days(count: int, posts: list, skip_weekdays: list, start: datetime.date | None = None):
    """Return `count` upcoming calendar days (YYYY-MM-DD) that have no
    scheduled/published post, skipping weekdays in skip_weekdays
    (Python weekday(): Mon=0..Sun=6). Starts tomorrow."""
    busy_days = set()
    for p in posts or []:
        if not isinstance(p, dict):
            continue
        if p.get("status") not in ("scheduled", "published"):
            continue
        sf = p.get("scheduledFor") or ""
        day = str(sf)[:10]
        if day:
            busy_days.add(day)

    skip = set(skip_weekdays or [])
    day = (start or datetime.date.today()) + datetime.timedelta(days=1)
    out = []
    guard = 0
    while len(out) < count and guard < 200:
        guard += 1
        iso = day.isoformat()
        if day.weekday() not in skip and iso not in busy_days:
            out.append(iso)
            busy_days.add(iso)  # don't double-book the same day within this run
        day += datetime.timedelta(days=1)
    return out


def _chosen_slugs():
    state = _services._load_json(DATA / "orchestrator_state.json", {}) or {}
    return sorted(s for s, e in state.items() if isinstance(e, dict) and e.get("status") == "chosen")


def _awaiting_slugs():
    state = _services._load_json(DATA / "orchestrator_state.json", {}) or {}
    return sorted(s for s, e in state.items() if isinstance(e, dict) and e.get("status") == "awaiting_choice")


# ── 1. refresh_all ───────────────────────────────────────────────────

def _refresh_all_plan(params):
    return [
        "לרענן מטריקות (collect_metrics, ללא פרסום ציבורי)",
        "לאפס מטמון פוסטים",
        "לחשב מחדש טבלת למידה",
    ]


def _refresh_all_steps(params):
    def invalidate_cache(log):
        _services._POSTS_CACHE["ts"] = 0.0
        _services._POSTS_CACHE["data"] = None
        log("posts cache invalidated")

    def recompute_learning(log):
        res = _services.learning()
        n = len(res.get("rows", [])) if isinstance(res, dict) else 0
        log(f"learning recomputed: {n} rows")

    return [
        _sub("רענון מטריקות", ["scripts/collect_metrics.py"]),
        _py("איפוס מטמון פוסטים", invalidate_cache),
        _py("חישוב למידה מחדש", recompute_learning),
    ]


# ── 2. scout_now ─────────────────────────────────────────────────────

def _scout_now_plan(params):
    return [
        "להריץ aliexpress_scout --write (איסוף מוצרים חדשים)",
        "להריץ daily_heel_scout ריצה אמיתית (שליחת סבב הבוקר לטלגרם)",
    ]


def _scout_now_steps(params):
    return [
        _sub("איסוף מוצרים מאלי אקספרס", ["scripts/aliexpress_scout.py", "--write"]),
        {"type": "subprocess", "title": "סריקת בוקר יומית (אמיתי)",
         "cmd": [PY, "-3", "-c", "import daily_heel_scout as d; d.main(dry=False)"],
         "cwd": str(SCRIPTS), "timeout": 900},
    ]


# ── 3. schedule_chosen ───────────────────────────────────────────────

def _schedule_chosen_plan(params):
    slugs = _chosen_slugs()
    if not slugs:
        return ["אין נעליים במצב 'נבחר' לשיבוץ כרגע"]
    posts = _services.posts(fresh=True)
    if isinstance(posts, dict) and posts.get("error"):
        posts = []
    skip_weekdays = _niche.cfg("schedule.skip_weekdays", [])
    slots = _niche.cfg("schedule.slots", ["16:00"])
    first_slot = slots[0] if slots else "16:00"
    days = _next_free_days(len(slugs), posts, skip_weekdays)
    lines = []
    for slug, day in zip(slugs, days):
        lines.append(f"{slug} → {day} {first_slot}")
    if len(days) < len(slugs):
        lines.append(f"⚠ נמצאו {len(days)} ימים פנויים בלבד עבור {len(slugs)} נעליים")
    return lines


def _schedule_chosen_steps(params):
    slugs = _chosen_slugs()
    posts = _services.posts(fresh=True)
    if isinstance(posts, dict) and posts.get("error"):
        posts = []
    skip_weekdays = _niche.cfg("schedule.skip_weekdays", [])
    slots = _niche.cfg("schedule.slots", ["16:00"])
    first_slot = slots[0] if slots else "16:00"
    days = _next_free_days(len(slugs), posts, skip_weekdays)

    steps = []
    for slug, day in zip(slugs, days):
        steps.append(_sub(f"סיום הפקה: {slug}", ["scripts/orchestrator.py", "finalize", slug]))
        steps.append(_sub(
            f"שיבוץ ופרסום: {slug} → {day}",
            ["scripts/pickup_drop.py", slug, "--from-gelem", "--folder", f"{slug}/drop",
             "--date", day, "--slots", first_slot, "--push", "--publish"],
        ))
    return steps


# ── 4. fill_gaps (report-only) ───────────────────────────────────────

def _fill_gaps_report(params):
    posts = _services.posts(fresh=False)
    if isinstance(posts, dict) and posts.get("error"):
        posts = []
    skip_weekdays = set(_niche.cfg("schedule.skip_weekdays", []))
    busy_days = set()
    for p in posts or []:
        if isinstance(p, dict) and p.get("status") in ("scheduled", "published"):
            day = str(p.get("scheduledFor") or "")[:10]
            if day:
                busy_days.add(day)

    empty_days = []
    day = datetime.date.today() + datetime.timedelta(days=1)
    for _ in range(30):
        if day.weekday() not in skip_weekdays and day.isoformat() not in busy_days:
            empty_days.append(day.isoformat())
        day += datetime.timedelta(days=1)

    ready = len(_chosen_slugs())
    return {"empty_days": empty_days, "empty_days_count": len(empty_days), "ready_shoes": ready}


def _fill_gaps_plan(params):
    r = _fill_gaps_report(params)
    return [f"{r['empty_days_count']} ימים פנויים ב-30 הימים הבאים, {r['ready_shoes']} נעליים מוכנות לשיבוץ"]


def _fill_gaps_steps(params):
    return []  # report-only, nothing to run


# ── 5. retry_failed ──────────────────────────────────────────────────

def _retry_failed_plan(params):
    return ["להריץ tiktok_retry --apply על פוסטים שנכשלו"]


def _retry_failed_steps(params):
    return [_sub("ניסיון חוזר לפוסטים שנכשלו", ["scripts/tiktok_retry.py", "--apply"])]


# ── 6. produce_queue ─────────────────────────────────────────────────

def _produce_queue_plan(params):
    return ["להריץ scripts/run_producer.bat (הפקת תור Magnific, כ-20 דקות, צורך קרדיטים)"]


def _produce_queue_steps(params):
    return [{"type": "subprocess", "title": "הפקת תור (run_producer.bat)",
             "cmd": [str(SCRIPTS / "run_producer.bat")], "cwd": str(SCRIPTS), "timeout": 2400}]


# ── 7. publish_dashboard ─────────────────────────────────────────────

def _publish_dashboard_plan(params):
    return ["להריץ collect_metrics --push (מפרסם דשבורד ציבורי מעודכן)"]


def _publish_dashboard_steps(params):
    return [_sub("פרסום דשבורד", ["scripts/collect_metrics.py", "--push"])]


# ── 8. resend_choices ────────────────────────────────────────────────

def _resend_choices_plan(params):
    slugs = _awaiting_slugs()
    if not slugs:
        return ["אין בחירות ממתינות לשליחה חוזרת"]
    return [f"לשלוח שוב לטלגרם: {s}" for s in slugs]


def _resend_choices_steps(params):
    slugs = _awaiting_slugs()
    return [_sub(f"שליחה חוזרת לטלגרם: {s}", ["scripts/orchestrator.py", "send", s]) for s in slugs]


# ── 9. activate_brands_from_telegram ─────────────────────────────────

def _activate_brands_plan(params):
    return ["לקרוא תיבת טלגרם ולהפעיל מותגים שאושרו (heel_hunter activate)"]


def _activate_brands_steps(params):
    return [_sub("הפעלת מותגים מטלגרם", ["scripts/heel_hunter.py", "activate"])]


# ── registry ─────────────────────────────────────────────────────────

WORKFLOWS = {
    "refresh_all": {
        "title_he": "רענון כללי", "description_he": "מטריקות + מטמון + למידה (ללא פרסום)",
        "needs_confirm": False, "est_duration": "כ-30 שניות",
        "plan": _refresh_all_plan, "steps": _refresh_all_steps,
    },
    "scout_now": {
        "title_he": "סריקת בוקר עכשיו",
        "description_he": "איסוף מוצרים חדשים + שליחת סבב הבוקר לטלגרם",
        "needs_confirm": True, "est_duration": "כ-2-5 דקות",
        "plan": _scout_now_plan, "steps": _scout_now_steps,
    },
    "schedule_chosen": {
        "title_he": "שבץ נעליים נבחרות",
        "description_he": "לכל נעל שנבחרה בטלגרם: סיום הפקה + שיבוץ ליום פנוי + פרסום",
        "needs_confirm": True, "est_duration": "תלוי כמות, כ-1-2 דקות לנעל",
        "plan": _schedule_chosen_plan, "steps": _schedule_chosen_steps,
    },
    "fill_gaps": {
        "title_he": "ימים ריקים בלוח",
        "description_he": "דוח בלבד: ימים ריקים ב-30 הימים הבאים + נעליים מוכנות למלא אותם",
        "needs_confirm": False, "est_duration": "מיידי",
        "plan": _fill_gaps_plan, "steps": _fill_gaps_steps, "report": _fill_gaps_report,
    },
    "retry_failed": {
        "title_he": "נסה שוב פוסטים שנכשלו",
        "description_he": "tiktok_retry --apply",
        "needs_confirm": True, "est_duration": "כ-1 דקה",
        "plan": _retry_failed_plan, "steps": _retry_failed_steps,
    },
    "produce_queue": {
        "title_he": "הפק תור ייצור",
        "description_he": "מריץ את run_producer.bat (Magnific, מונחה Claude)",
        "needs_confirm": True, "est_duration": "~20 דקות, צורך קרדיטים",
        "plan": _produce_queue_plan, "steps": _produce_queue_steps,
    },
    "publish_dashboard": {
        "title_he": "פרסם דשבורד",
        "description_he": "collect_metrics --push",
        "needs_confirm": True, "est_duration": "כ-30 שניות",
        "plan": _publish_dashboard_plan, "steps": _publish_dashboard_steps,
    },
    "resend_choices": {
        "title_he": "שלח בחירות שוב",
        "description_he": "שולח שוב A/B/C/D לטלגרם לכל נעל שממתינה לבחירה",
        "needs_confirm": True, "est_duration": "מיידי",
        "plan": _resend_choices_plan, "steps": _resend_choices_steps,
    },
    "activate_brands_from_telegram": {
        "title_he": "הפעל מותגים מהטלגרם",
        "description_he": "קורא הודעות 'aff domain link' ומפעיל תוכניות שותפים",
        "needs_confirm": False, "est_duration": "מיידי",
        "plan": _activate_brands_plan, "steps": _activate_brands_steps,
    },
}


def list_meta():
    out = []
    for name, wf in WORKFLOWS.items():
        lr = _jobs.last_run(name)
        last = None
        if lr:
            last = {"status": lr["status"], "finished_at": lr.get("finished_at")}
        out.append({
            "name": name, "title_he": wf["title_he"], "description_he": wf["description_he"],
            "needs_confirm": wf["needs_confirm"], "est_duration": wf["est_duration"],
            "last_run": last, "active": _jobs.is_active(name),
        })
    return out


def run(name: str, dry_run: bool, params: dict | None = None):
    wf = WORKFLOWS.get(name)
    if not wf:
        return {"error": f"unknown workflow: {name}"}
    params = params or {}
    if dry_run:
        plan = wf["plan"](params)
        result = {"dry_run": True, "plan": plan}
        if "report" in wf:
            result["report"] = wf["report"](params)
        return result
    steps = wf["steps"](params)
    if not steps:
        # report-only workflow with no side effects: return the report directly
        result = {"dry_run": False, "ran": False}
        if "report" in wf:
            result["report"] = wf["report"](params)
        return result
    try:
        job_id = _jobs.start(name, steps, params)
    except ValueError as e:
        return {"error": str(e)}
    return {"dry_run": False, "job_id": job_id}
