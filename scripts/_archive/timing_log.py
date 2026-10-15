"""
Production Timing Logger — TheGothicVault
Records phase timestamps for workflow benchmarking.

Usage:
    from timing_log import phase_start, phase_end, print_summary

    phase_start("T2I")
    ... generate T2I ...
    phase_end("T2I")

    print_summary()
"""
import json
import time
from pathlib import Path
from datetime import datetime

LOG_FILE = Path("E:/PROJECTS/thegothicvault/scripts/timing_data.json")

PHASES = [
    "space_setup",    # Upload nodes, connect pipeline
    "t2i_gen",        # T2I image generation
    "i2v_gen_kling",  # Kling video generation
    "i2v_gen_minimax",# MiniMax video generation (if applicable)
    "download",       # Downloading videos via API
    "assembly",       # Python script assembly (segments + concat + watermark)
    "send_telegram",  # Sending final video
]


def _load() -> dict:
    if LOG_FILE.exists():
        try:
            return json.loads(LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"sessions": []}


def _save(data: dict):
    LOG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def phase_start(phase: str, product: str = ""):
    data = _load()
    sessions = data.setdefault("sessions", [])
    # Find or create active session
    active = next((s for s in sessions if s.get("status") == "active"), None)
    if not active:
        active = {
            "product": product,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "status": "active",
            "phases": {}
        }
        sessions.append(active)
    if product and not active.get("product"):
        active["product"] = product

    active["phases"].setdefault(phase, {})["start"] = time.time()
    active["phases"][phase]["start_str"] = datetime.now().strftime("%H:%M:%S")
    _save(data)
    print(f"[timing] {phase} STARTED at {active['phases'][phase]['start_str']}")


def phase_end(phase: str):
    data = _load()
    active = next((s for s in data.get("sessions", []) if s.get("status") == "active"), None)
    if not active:
        print(f"[timing] no active session — call phase_start first")
        return

    p = active["phases"].get(phase)
    if not p or "start" not in p:
        print(f"[timing] {phase} was never started")
        return

    elapsed = time.time() - p["start"]
    p["end"] = time.time()
    p["end_str"] = datetime.now().strftime("%H:%M:%S")
    p["elapsed_s"] = round(elapsed, 1)
    p["elapsed_str"] = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
    _save(data)
    print(f"[timing] {phase} DONE — {p['elapsed_str']}")


def session_done(product: str = ""):
    data = _load()
    active = next((s for s in data.get("sessions", []) if s.get("status") == "active"), None)
    if not active:
        return
    active["status"] = "done"
    if product:
        active["product"] = product

    total_phases = sum(
        p.get("elapsed_s", 0)
        for p in active.get("phases", {}).values()
    )
    active["total_s"] = round(total_phases, 1)
    active["total_str"] = f"{int(total_phases // 60)}m {int(total_phases % 60)}s"
    _save(data)


def print_summary():
    data = _load()
    sessions = data.get("sessions", [])
    if not sessions:
        print("No timing data yet.")
        return

    print("\n=== Production Timing Summary ===")
    for s in sessions[-5:]:  # last 5 sessions
        print(f"\n{s.get('date','?')} — {s.get('product','unknown')} [{s.get('status','?')}]")
        for phase, p in s.get("phases", {}).items():
            t = p.get("elapsed_str", "in progress")
            print(f"  {phase:<20} {t}")
        if "total_str" in s:
            print(f"  {'TOTAL':<20} {s['total_str']}")
    print()


def get_averages() -> dict:
    data = _load()
    phase_times: dict[str, list[float]] = {}
    for s in data.get("sessions", []):
        if s.get("status") != "done":
            continue
        for phase, p in s.get("phases", {}).items():
            if "elapsed_s" in p:
                phase_times.setdefault(phase, []).append(p["elapsed_s"])

    return {
        phase: {
            "avg_s": round(sum(times) / len(times), 1),
            "min_s": min(times),
            "max_s": max(times),
            "n": len(times)
        }
        for phase, times in phase_times.items()
    }


if __name__ == "__main__":
    print_summary()
    avgs = get_averages()
    if avgs:
        print("=== Phase Averages ===")
        for phase, stats in avgs.items():
            print(f"  {phase:<20} avg {stats['avg_s']}s  (min {stats['min_s']}s / max {stats['max_s']}s)  n={stats['n']}")
