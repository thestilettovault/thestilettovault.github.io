# -*- coding: utf-8 -*-
"""Thin wrappers over the existing scripts/ engine for the control center.

Every public function here is JSON-able and never raises: failures come back
as {"error": "..."} so a single broken source never takes the whole app down.
Imports of scripts/ modules are done lazily inside each function so the app
still starts even if one script fails to import (missing dependency etc).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
DATA = ROOT / "data"
DASH = ROOT / "dashboard"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

PY = sys.executable or "py"


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


# ── overview ─────────────────────────────────────────────────────────

def _posts_summary():
    posts = posts_list()
    if isinstance(posts, dict) and posts.get("error"):
        return {"scheduled": 0, "published": 0, "failed": 0, "error": posts["error"]}
    out = {"scheduled": 0, "published": 0, "failed": 0}
    for p in posts:
        st = p.get("status")
        if st in out:
            out[st] += 1
    return out


def _needs_you():
    items = []

    # awaiting_choice in orchestrator_state.json
    try:
        state = _load_json(DATA / "orchestrator_state.json", {})
        for slug, entry in (state or {}).items():
            if isinstance(entry, dict) and entry.get("status") == "awaiting_choice":
                items.append({
                    "kind": "awaiting_choice",
                    "text": f"בחירת מודעה ממתינה: {slug}",
                    "action": slug,
                })
    except Exception as e:
        items.append({"kind": "error", "text": f"orchestrator_state: {e}", "action": ""})

    # carded brands in affiliate registry
    try:
        reg = _load_json(DATA / "affiliate_registry.json", {"brands": {}})
        for domain, e in (reg.get("brands") or {}).items():
            if e.get("status") == "carded":
                items.append({
                    "kind": "affiliate_carded",
                    "text": f"כרטיס הרשמה נשלח: {domain} (${e.get('value_per_sale', 0)}/מכירה)",
                    "action": domain,
                })
    except Exception as e:
        items.append({"kind": "error", "text": f"affiliate_registry: {e}", "action": ""})

    # failed Zernio posts
    try:
        posts = posts_list()
        if isinstance(posts, list):
            for p in posts:
                if p.get("status") == "failed":
                    items.append({
                        "kind": "post_failed",
                        "text": f"פוסט נכשל: {p.get('content', '')[:60]}",
                        "action": p.get("id", ""),
                    })
    except Exception as e:
        items.append({"kind": "error", "text": f"posts: {e}", "action": ""})

    return items


def overview():
    try:
        data = _load_json(DASH / "data.json", {})
        return {
            "funnel": data.get("funnel", {}),
            "sales": data.get("sales", {}),
            "traffic": data.get("traffic", {}),
            "followers": data.get("followers", {}),
            "generated_at": data.get("generated_at"),
            "shoes_count": len(data.get("shoes", []) or []),
            "posts": _posts_summary(),
            "needs_you": _needs_you(),
        }
    except Exception as e:
        return {"error": str(e)}


# ── health ───────────────────────────────────────────────────────────

def _tail(path: Path, n=3):
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-n:]
    except Exception:
        return []


def _log_entry(path: Path):
    if not path.exists():
        return None
    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = None
    return {
        "name": path.name,
        "path": str(path),
        "modified": mtime,
        "last_lines": _tail(path, 3),
    }


def _bot_alive():
    """The bot holds a listening lock socket on 127.0.0.1:49517 (telegram_bot.acquire_single_instance)."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 49517), timeout=1):
            return True
    except OSError:
        return False


def _bot_alive_legacy():
    try:
        try:
            import psutil
        except Exception:
            psutil = None
        if psutil is not None:
            for p in psutil.process_iter(["name", "cmdline"]):
                try:
                    cmdline = " ".join(p.info.get("cmdline") or [])
                except Exception:
                    continue
                if "telegram_bot.py" in cmdline:
                    return True
            return False
        # fallback: tasklist /v (Windows)
        out = subprocess.run(
            ["tasklist", "/v", "/fo", "csv"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        if "telegram_bot" in out or "python" in out.lower():
            # tasklist /v doesn't reliably show full cmdline; can't confirm script name
            return "unknown"
        return False
    except Exception:
        return "unknown"


def health():
    try:
        log_names = ["producer.log", "bot.log", "heel_hunter.log"]
        logs = []
        for name in log_names:
            entry = _log_entry(SCRIPTS / name)
            if entry:
                logs.append(entry)
        # daily scout log — any file matching *scout*.log
        try:
            for p in SCRIPTS.glob("*scout*.log"):
                entry = _log_entry(p)
                if entry:
                    logs.append(entry)
        except Exception:
            pass
        return {"logs": logs, "bot_alive": _bot_alive()}
    except Exception as e:
        return {"error": str(e)}


# ── products ─────────────────────────────────────────────────────────

def products():
    try:
        catalog = _load_json(DATA / "approved_catalog.json", [])
        dash = _load_json(DASH / "data.json", {})
        shoes = {s.get("slug"): s for s in (dash.get("shoes") or [])}
        state = _load_json(DATA / "orchestrator_state.json", {})

        try:
            import space_runner  # slugify, same rule as collect_metrics
            def slugify(it):
                return space_runner.slugify(it)
        except Exception:
            import re as _re
            def slugify(it):
                m = _re.search(r"/products/([^/?#]+)", it.get("url", "") or "")
                base = m.group(1) if m else it.get("title", "item")
                return (_re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:60]) or "item"

        out = []
        for it in catalog:
            slug = slugify(it)
            shoe = shoes.get(slug, {})
            st = state.get(slug, {})
            out.append({
                "title": it.get("title"),
                "url": it.get("url"),
                "aff_link": it.get("aff_link"),
                "domain": it.get("domain"),
                "image_url": it.get("image_url"),
                "commission": it.get("commission"),
                "date": it.get("date"),
                "posted": it.get("posted", False),
                "posted_date": it.get("posted_date", ""),
                "local_asset": it.get("local_asset"),
                "slug": slug,
                "clicks": shoe.get("clicks_per_shoe") or shoe.get("clicks", 0),
                "sales": shoe.get("sales", 0),
                "status": shoe.get("status", ""),
                "orchestrator_status": st.get("status", ""),
                "chosen": st.get("chosen", ""),
            })
        return out
    except Exception as e:
        return {"error": str(e)}


def approve(url, title, image_url="", domain="", commission=""):
    try:
        import taste_engine
        taste_engine.record_approval(url, title, image_url=image_url,
                                      commission=commission, domain=domain)
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


def reject(url, title):
    try:
        import taste_engine
        taste_engine.record_rejection(url, title)
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


def add_product(url):
    try:
        import taste_engine
        title = ""
        try:
            import requests
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
            import re
            m = re.search(r"<title[^>]*>([^<]+)</title>", r.text, re.I)
            if m:
                title = m.group(1).strip()
        except Exception:
            pass
        title = title or url
        product_id = taste_engine._slugify(title)[:40] or "product"
        domain = taste_engine.get_domain(url)
        taste_engine.save_pending(product_id, url, title, domain=domain)
        return {"ok": True, "id": product_id, "url": url, "title": title, "domain": domain}
    except Exception as e:
        return {"error": str(e)}


# ── posts (Zernio) ───────────────────────────────────────────────────

def _zernio():
    import social_publisher as sp
    return sp.ZERNIO_API_URL, sp.ZERNIO_API_KEY


def _zernio_headers():
    _, key = _zernio()
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def posts_list():
    try:
        import requests
        url, _ = _zernio()
        r = requests.get(f"{url}/posts", headers=_zernio_headers(),
                          params={"limit": 200}, timeout=15)
        r.raise_for_status()
        raw = r.json().get("posts", [])
        out = []
        for p in raw:
            platforms = p.get("platforms") or []
            live_url = ""
            for pl in platforms:
                if pl.get("platformPostUrl"):
                    live_url = pl["platformPostUrl"]
                    break
            media = p.get("mediaItems") or []
            media_type = media[0].get("type") if media else ""
            out.append({
                "id": p.get("_id"),
                "content": (p.get("content") or "")[:120],
                "scheduledFor": p.get("scheduledFor"),
                "status": p.get("status"),
                "platforms": [pl.get("platform") for pl in platforms],
                "url": live_url,
                "media_type": media_type,
            })
        return out
    except Exception as e:
        return {"error": str(e)}


def posts():
    return posts_list()


def move_post(post_id, scheduled_for):
    try:
        import requests
        url, _ = _zernio()
        r = requests.put(f"{url}/posts/{post_id}", headers=_zernio_headers(),
                          json={"scheduledFor": scheduled_for}, timeout=15)
        if r.status_code not in (200, 201):
            return {"error": f"{r.status_code} {r.text[:200]}"}
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


def cancel_post(post_id):
    try:
        import requests
        url, _ = _zernio()
        r = requests.delete(f"{url}/posts/{post_id}", headers=_zernio_headers(), timeout=15)
        if r.status_code not in (200, 201, 204):
            return {"error": f"{r.status_code} {r.text[:200]}"}
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


def retry_failed():
    try:
        proc = subprocess.run(
            [PY, "-3", "scripts/tiktok_retry.py", "--apply"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=600,
        )
        tail = (proc.stdout or "")[-4000:] + (("\n" + proc.stderr[-2000:]) if proc.stderr else "")
        return {"ok": proc.returncode == 0, "output_tail": tail}
    except Exception as e:
        return {"error": str(e)}


# ── affiliate registry ──────────────────────────────────────────────

def registry():
    try:
        import heel_hunter
        brands = heel_hunter.load_reg().get("brands", {})
        rows = list(brands.values())
        rows.sort(key=lambda e: -(e.get("value_per_sale") or 0))
        return rows
    except Exception as e:
        return {"error": str(e)}


def registry_add(domain):
    try:
        import heel_hunter
        return heel_hunter.upsert(domain)
    except Exception as e:
        return {"error": str(e)}


def registry_activate(domain, link):
    try:
        import heel_hunter
        return heel_hunter.activate_one(domain, link)
    except Exception as e:
        return {"error": str(e)}


# ── trends / learning ────────────────────────────────────────────────

def trends():
    try:
        return _load_json(DATA / "trends.json", [])
    except Exception as e:
        return {"error": str(e)}


def learning():
    try:
        from . import learning as _learning
        shoes, states = _learning.load_default()
        gelem_root = str(ROOT / "GELEM")
        rows = _learning.table(shoes, states, gelem_root)
        summ = _learning.summary(rows)
        return {"rows": rows, "summary": summ}
    except Exception as e:
        return {"error": str(e)}


# ── run whitelist ────────────────────────────────────────────────────

def _run_cmd(cmd, cwd=None, timeout=600):
    try:
        proc = subprocess.run(cmd, cwd=cwd or str(ROOT), capture_output=True,
                               text=True, timeout=timeout)
        tail = (proc.stdout or "")[-4000:] + (("\n" + proc.stderr[-2000:]) if proc.stderr else "")
        return {"ok": proc.returncode == 0, "output_tail": tail}
    except Exception as e:
        return {"error": str(e)}


def run(job):
    if job == "scout_dry":
        return _run_cmd([PY, "-3", "-c",
                          "import daily_heel_scout as d; d.main(dry=True)"],
                         cwd=str(SCRIPTS))
    if job == "scout":
        return _run_cmd([PY, "-3", "-c",
                          "import daily_heel_scout as d; d.main(dry=False)"],
                         cwd=str(SCRIPTS))
    if job == "metrics":
        return _run_cmd([PY, "-3", "scripts/collect_metrics.py"])
    if job == "tiktok_retry":
        return retry_failed()
    return {"error": f"unknown job: {job}"}
