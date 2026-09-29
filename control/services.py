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
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
DATA = ROOT / "data"
DASH = ROOT / "dashboard"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

def _real_python():
    """Console python.exe next to the running interpreter (pythonw → python), never the
    WindowsApps shim; `py -3` fallback. Subprocess steps need a console-capable exe."""
    exe = Path(sys.executable or "")
    if exe.name.lower() == "pythonw.exe":
        exe = exe.with_name("python.exe")
    return [str(exe)] if exe.name.lower() == "python.exe" and exe.exists() else ["py", "-3"]


PYCMD = _real_python()


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_url(url):
    """Dedupe key: strip query/fragment, lowercase host, strip leading www."""
    if not url:
        return ""
    try:
        parts = urlsplit(str(url).strip())
        host = parts.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        path = (parts.path or "").rstrip("/")
        scheme = (parts.scheme or "https").lower()
        if not host:
            return str(url).strip().lower()
        return urlunsplit((scheme, host, path, "", ""))
    except Exception:
        return str(url).strip().lower()


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
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 49517))   # never connect: the bot doesn't accept() on its lock
    except OSError:
        return True                    # port held → bot running
    finally:
        s.close()
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

def _slugify_fallback(it):
    import re as _re
    m = _re.search(r"/products/([^/?#]+)", it.get("url", "") or "")
    base = m.group(1) if m else it.get("title", "item")
    return (_re.sub(r"[^a-z0-9]+", "-", (base or "item").lower()).strip("-")[:60]) or "item"


def _slugify(it):
    try:
        import space_runner  # slugify, same rule as collect_metrics
        return space_runner.slugify(it)
    except Exception:
        return _slugify_fallback(it)


def products():
    """One list of every product BOLD has ever seen, deduped by URL, with a
    normalized `stage`: pool → pending → approved → producing → produced/
    scheduled/published, or rejected. Stages never overlap; the last writer
    for a given key wins in the order below (approved-catalog state wins
    over rejected — a reversal is handled by /undo_reject removing the
    rejected entry, not by ordering here).
    """
    try:
        pending = _load_json(DATA / "pending_reviews.json", {}) or {}
        rejected = (_load_json(DATA / "rejected_profile.json", {}) or {}).get("rejected", []) or []
        approved = _load_json(DATA / "approved_catalog.json", []) or []
        pool = (_load_json(DATA / "aliexpress_pool.json", {}) or {}).get("products", []) or []
        dash = _load_json(DASH / "data.json", {}) or {}
        shoes_by_slug = {s.get("slug"): s for s in (dash.get("shoes") or [])}
        state = _load_json(DATA / "orchestrator_state.json", {}) or {}

        by_key = {}

        def row_for(key):
            row = by_key.get(key)
            if row is None:
                row = {
                    "key": key, "title": "", "url": "", "aff_link": "",
                    "image_url": "", "price": None, "deal": None,
                    "domain": "", "commission": "", "stage": "pool",
                    "clicks": 0, "sales": 0, "slug": "", "date": "",
                    "pending_id": "",
                }
                by_key[key] = row
            return row

        def upsert(key, patch):
            row = row_for(key)
            for k, v in patch.items():
                if v not in (None, "", []):
                    row[k] = v
            return row

        for r in rejected:
            url = r.get("link") or r.get("title") or ""
            key = _normalize_url(url)
            if not key:
                continue
            upsert(key, {"title": r.get("title", ""), "url": url,
                          "date": r.get("date", ""), "stage": "rejected"})

        for it in pool:
            url = it.get("url", "")
            key = _normalize_url(url)
            if not key or by_key.get(key, {}).get("stage") == "rejected":
                continue
            upsert(key, {
                "title": it.get("title"), "url": url, "aff_link": it.get("aff_link"),
                "image_url": it.get("image_url"), "price": it.get("price"),
                "deal": it.get("deal"), "commission": it.get("commission"),
                "domain": it.get("domain"), "stage": "pool",
            })

        for pid, it in pending.items():
            url = it.get("url", "")
            key = _normalize_url(url)
            if not key or by_key.get(key, {}).get("stage") == "rejected":
                continue
            upsert(key, {
                "title": it.get("title"), "url": url, "image_url": it.get("image_url"),
                "commission": it.get("commission"), "domain": it.get("domain"),
                "date": it.get("ts", ""), "pending_id": pid, "stage": "pending",
            })

        for it in approved:
            url = it.get("url", "") or it.get("aff_link", "")
            key = _normalize_url(url)
            if not key:
                continue
            slug = _slugify(it)
            shoe = shoes_by_slug.get(slug, {})
            st = state.get(slug, {})
            stage = "approved"
            shoe_status = shoe.get("status", "")
            orch_status = st.get("status", "")
            if orch_status in ("awaiting_choice", "chosen"):
                stage = "producing"
            elif shoe.get("on_site") or shoe_status == "published" or it.get("posted"):
                stage = "published"
            elif shoe_status == "scheduled":
                stage = "scheduled"
            elif shoe_status == "produced" or orch_status == "finalized":
                stage = "produced"
            row = upsert(key, {
                "title": it.get("title"), "url": it.get("url"), "aff_link": it.get("aff_link"),
                "image_url": it.get("image_url"), "commission": it.get("commission"),
                "domain": it.get("domain"), "date": it.get("date"), "stage": stage,
                "slug": slug,
            })
            row["clicks"] = shoe.get("clicks_per_shoe") or shoe.get("clicks") or row.get("clicks") or 0
            row["sales"] = shoe.get("sales") or row.get("sales") or 0

        return list(by_key.values())
    except Exception as e:
        return {"error": str(e)}


def approve(url, title, image_url="", domain="", commission="", pending_id=""):
    try:
        import taste_engine
        taste_engine.record_approval(url, title, image_url=image_url,
                                      commission=commission, domain=domain)
        if pending_id:
            try:
                taste_engine.remove_pending(pending_id)
            except Exception:
                pass
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


def reject(url, title, pending_id=""):
    try:
        import taste_engine
        taste_engine.record_rejection(url, title)
        if pending_id:
            try:
                taste_engine.remove_pending(pending_id)
            except Exception:
                pass
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


def undo_reject(url):
    """Remove a URL from rejected_profile.json so it falls back to whatever
    other stage it still qualifies for (pool/pending/approved) on next read."""
    try:
        path = DATA / "rejected_profile.json"
        data = _load_json(path, {"rejected": []}) or {"rejected": []}
        key = _normalize_url(url)
        items = data.get("rejected") or []
        before = len(items)
        items = [r for r in items
                 if _normalize_url(r.get("link") or r.get("title") or "") != key]
        data["rejected"] = items
        if len(items) == before:
            return {"ok": True, "removed": False}
        _save_json(path, data)
        return {"ok": True, "removed": True}
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


_POSTS_CACHE = {"ts": 0.0, "data": None}
_POSTS_TTL = 60


def posts_list(fresh=False):
    now = time.time()
    if not fresh and _POSTS_CACHE["data"] is not None and (now - _POSTS_CACHE["ts"]) < _POSTS_TTL:
        return _POSTS_CACHE["data"]
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
            thumb = media[0].get("url") if media else ""
            out.append({
                "id": p.get("_id"),
                "content": (p.get("content") or "")[:120],
                "scheduledFor": p.get("scheduledFor"),
                "status": p.get("status"),
                "platforms": [pl.get("platform") for pl in platforms],
                "url": live_url,
                "media_type": media_type,
                "thumb": thumb,
            })
        _POSTS_CACHE["data"] = out
        _POSTS_CACHE["ts"] = now
        return out
    except Exception as e:
        return {"error": str(e)}


def posts(fresh=False):
    return posts_list(fresh=fresh)


def posts_cache_age():
    """Seconds since the posts cache was last filled, or None if never filled."""
    if _POSTS_CACHE["data"] is None:
        return None
    return time.time() - _POSTS_CACHE["ts"]


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
            [*PYCMD, "scripts/tiktok_retry.py", "--apply"],
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
        ins = _learning.insights(shoes, states, gelem_root)
        return {"rows": rows, "summary": summ, "insights": ins, "shoes_count": len(shoes)}
    except Exception as e:
        return {"error": str(e)}


def learning_shoes():
    try:
        from . import learning as _learning
        shoes, states = _learning.load_default()
        gelem_root = str(ROOT / "GELEM")
        return _learning.shoes_with_features(shoes, states, gelem_root)
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
        return _run_cmd([*PYCMD, "-c",
                          "import daily_heel_scout as d; d.main(dry=True)"],
                         cwd=str(SCRIPTS))
    if job == "scout":
        return _run_cmd([*PYCMD, "-c",
                          "import daily_heel_scout as d; d.main(dry=False)"],
                         cwd=str(SCRIPTS))
    if job == "metrics":
        return _run_cmd([*PYCMD, "scripts/collect_metrics.py"])
    if job == "tiktok_retry":
        return retry_failed()
    return {"error": f"unknown job: {job}"}
