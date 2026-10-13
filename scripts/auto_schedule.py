"""Close the loop after Ofer picks an ad in Telegram.

Every heel whose orchestrator status is `chosen` is finalized as an IMAGE-ONLY post
(deal overlay when there is a deal, clean ad otherwise; no video = no credits) and
scheduled on the next free day: ONE heel per day, never on Saturday, after anything
already scheduled. Before 2026-10-13 nothing ran this step, so picked heels piled up.

    py -3 auto_schedule.py            # dry run: what would be scheduled, and when
    py -3 auto_schedule.py --apply    # finalize + host + schedule via Zernio

Cost: 0 credits (PIL overlay, GitHub Pages hosting, existing Zernio plan).
"""
import sys, json, datetime, subprocess, argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT))

import orchestrator
from control import services

SLOT = "16:00"            # the slot the image-only posts have been using
QUEUE = ROOT / "data" / "production_queue.json"


def scheduled_days():
    """Dates (YYYY-MM-DD) that already hold a scheduled post."""
    import requests
    url, _ = services._zernio()
    r = requests.get(f"{url}/posts", headers=services._zernio_headers(),
                     params={"limit": 200}, timeout=30)
    r.raise_for_status()
    return {(p.get("scheduledFor") or "")[:10] for p in r.json().get("posts", [])
            if p.get("status") == "scheduled"}


def next_free_day(taken):
    d = max([datetime.date.today()] +
            [datetime.date.fromisoformat(x) for x in taken if x]) + datetime.timedelta(days=1)
    while d.weekday() == 5 or d.isoformat() in taken:      # 5 = Saturday
        d += datetime.timedelta(days=1)
    return d


def mark_queue(slug_tail, status):
    """Keep production_queue.json in step (it used to stay 'awaiting_choice' forever)."""
    try:
        q = json.loads(QUEUE.read_text(encoding="utf-8"))
        items = q if isinstance(q, list) else q.get("queue", q.get("items", []))
        for it in items:
            if Path(str(it.get("local_asset", ""))).name == slug_tail:
                it["status"] = status
        QUEUE.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  ~ queue not updated: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

    chosen = orchestrator.pending_video_jobs()        # every slug with status == chosen
    if not chosen:
        print("auto_schedule: nothing chosen and waiting"); return
    taken = scheduled_days()
    for slug in chosen:
        tail = slug.split("/")[-1]                     # state keys may be '<date>/<slug>'
        day = next_free_day(taken)
        print(f"{tail} -> {day} {SLOT}" + ("" if a.apply else "  (dry run)"))
        if not a.apply:
            taken.add(day.isoformat()); continue
        if not orchestrator.finalize(slug):
            print(f"  ! {tail}: finalize failed, left as chosen"); continue
        r = subprocess.run([sys.executable, str(HERE / "pickup_drop.py"), tail, "--from-gelem",
                            "--folder", f"{slug}/drop", "--slots", SLOT,
                            "--date", day.isoformat(), "--push", "--publish"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        ok = "pickup_drop complete" in r.stdout and "→ instagram" in r.stdout
        print("  ✅ scheduled" if ok else f"  ! scheduling failed:\n{r.stdout[-600:]}{r.stderr[-300:]}")
        if ok:
            taken.add(day.isoformat()); mark_queue(tail, "scheduled")
        else:
            orchestrator.set_state(slug, status="chosen")   # retry on the next run


if __name__ == "__main__":
    main()
