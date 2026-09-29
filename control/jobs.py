# -*- coding: utf-8 -*-
"""In-process background job runner for the control center's one-click
workflows.

A job is a named sequence of steps, each either:
  {"type": "subprocess", "title": "...", "cmd": [...], "cwd": optional, "timeout": optional}
  {"type": "python", "title": "...", "fn": callable(log)}   # log(line) appends to the job log

Runs in a daemon thread so the Flask dev server stays responsive. Only one
job per workflow `name` may be active (queued/running) at a time. Finished
jobs are appended to data/jobs_history.json (last 100), with any line
containing a value from scripts/.env redacted.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HISTORY_FILE = DATA / "jobs_history.json"
ENV_FILE = ROOT / "scripts" / ".env"

PY = sys.executable or "py"

_LOCK = threading.RLock()
_JOBS: dict[str, dict] = {}          # job_id -> job dict
_ACTIVE_BY_NAME: dict[str, str] = {}  # workflow name -> job_id (queued/running only)

MAX_LOG_LINES = 500
MAX_HISTORY = 100


# ── secret redaction ────────────────────────────────────────────────

def _secret_values() -> list[str]:
    vals = []
    try:
        for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            _, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            if v:
                vals.append(v)
    except Exception:
        pass
    return vals


def _redact(line: str) -> str:
    for v in _secret_values():
        if v and v in line:
            line = line.replace(v, "***REDACTED***")
    return line


# ── job dict helpers ────────────────────────────────────────────────

def _new_job(name: str, steps: list[dict], params: dict) -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "params": params or {},
        "status": "queued",
        "created_at": time.time(),
        "started_at": None,
        "finished_at": None,
        "steps": [
            {"index": i, "title": s.get("title", f"step {i+1}"), "status": "pending"}
            for i, s in enumerate(steps)
        ],
        "log": [],
        "error": None,
    }


def _append_log(job: dict, line: str):
    if line is None:
        return
    for sub in str(line).splitlines() or [str(line)]:
        job["log"].append(_redact(sub))
    if len(job["log"]) > MAX_LOG_LINES:
        job["log"] = job["log"][-MAX_LOG_LINES:]


def _run_subprocess_step(job: dict, step: dict):
    cmd = step["cmd"]
    cwd = step.get("cwd") or str(ROOT)
    timeout = step.get("timeout", 1800)
    _append_log(job, f"$ {' '.join(str(c) for c in cmd)}")
    proc = subprocess.Popen(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    start = time.time()
    try:
        for raw_line in proc.stdout:  # type: ignore[union-attr]
            with _LOCK:
                _append_log(job, raw_line.rstrip("\n"))
            if time.time() - start > timeout:
                proc.kill()
                raise TimeoutError(f"step timed out after {timeout}s")
            if job.get("_cancel"):
                proc.kill()
                raise InterruptedError("cancelled")
    finally:
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
    if proc.returncode != 0 and not job.get("_cancel"):
        raise RuntimeError(f"exit code {proc.returncode}")


def _run_python_step(job: dict, step: dict):
    def log(line):
        with _LOCK:
            _append_log(job, line)
    step["fn"](log)


def _worker(job_id: str, steps: list[dict]):
    with _LOCK:
        job = _JOBS[job_id]
        job["status"] = "running"
        job["started_at"] = time.time()

    failed = False
    cancelled = False
    for i, step in enumerate(steps):
        with _LOCK:
            job = _JOBS[job_id]
            if job.get("_cancel"):
                cancelled = True
                job["steps"][i]["status"] = "cancelled"
                continue
            job["steps"][i]["status"] = "running"
        try:
            if step.get("type") == "subprocess":
                _run_subprocess_step(job, step)
            else:
                _run_python_step(job, step)
            with _LOCK:
                job["steps"][i]["status"] = "done"
        except InterruptedError:
            with _LOCK:
                job["steps"][i]["status"] = "cancelled"
            cancelled = True
        except Exception as e:
            with _LOCK:
                job["steps"][i]["status"] = "failed"
                job["error"] = str(e)
                _append_log(job, f"! step failed: {e}")
            failed = True
            break

    with _LOCK:
        job = _JOBS[job_id]
        job["finished_at"] = time.time()
        if job.get("_cancel") or cancelled:
            job["status"] = "cancelled"
        elif failed:
            job["status"] = "failed"
        else:
            job["status"] = "done"
        _ACTIVE_BY_NAME.pop(job["name"], None)
        _persist_history(job)


def _persist_history(job: dict):
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        hist = []
        if HISTORY_FILE.exists():
            try:
                hist = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                hist = []
        summary = {
            "id": job["id"], "name": job["name"], "status": job["status"],
            "started_at": job["started_at"], "finished_at": job["finished_at"],
            "error": job["error"],
        }
        hist.append(summary)
        hist = hist[-MAX_HISTORY:]
        HISTORY_FILE.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ── public API ───────────────────────────────────────────────────────

def start(name: str, steps: list[dict], params: dict | None = None) -> str:
    """Start a job for workflow `name`. Raises ValueError if one is already
    active for that name."""
    with _LOCK:
        existing_id = _ACTIVE_BY_NAME.get(name)
        if existing_id and _JOBS.get(existing_id, {}).get("status") in ("queued", "running"):
            raise ValueError(f"workflow '{name}' is already running (job {existing_id})")
        job = _new_job(name, steps, params or {})
        _JOBS[job["id"]] = job
        _ACTIVE_BY_NAME[name] = job["id"]
    t = threading.Thread(target=_worker, args=(job["id"], steps), daemon=True)
    t.start()
    return job["id"]


def get(job_id: str) -> dict | None:
    with _LOCK:
        return _JOBS.get(job_id)


def cancel(job_id: str) -> bool:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return False
        if job["status"] not in ("queued", "running"):
            return False
        job["_cancel"] = True
        return True


def list_jobs() -> dict:
    """Active jobs (queued/running) + recent finished history."""
    with _LOCK:
        active = [j for j in _JOBS.values() if j["status"] in ("queued", "running")]
        recent = sorted(
            [j for j in _JOBS.values() if j["status"] not in ("queued", "running")],
            key=lambda j: j.get("finished_at") or 0, reverse=True,
        )[:20]
        return {"active": active, "recent": recent}


def last_run(name: str) -> dict | None:
    """Most recent finished (or active) job for a workflow name — in-memory first, then
    data/jobs_history.json so "last run" survives a server restart."""
    with _LOCK:
        candidates = [j for j in _JOBS.values() if j["name"] == name]
    if not candidates:
        try:
            hist = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            candidates = [j for j in (hist if isinstance(hist, list) else []) if j.get("name") == name]
        except Exception:
            candidates = []
    with _LOCK:
        if not candidates:
            return None
        candidates.sort(key=lambda j: j.get("finished_at") or j.get("started_at") or j.get("created_at") or 0,
                         reverse=True)
        return candidates[0]


def is_active(name: str) -> bool:
    with _LOCK:
        jid = _ACTIVE_BY_NAME.get(name)
        return bool(jid and _JOBS.get(jid, {}).get("status") in ("queued", "running"))
