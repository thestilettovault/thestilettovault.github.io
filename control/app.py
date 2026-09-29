# -*- coding: utf-8 -*-
"""Control center Flask app — local-only dashboard/control panel for the
Stiletto Vault affiliate engine.

Run: py -3 -m control.app   (binds 127.0.0.1:8787, single-instance guarded)
"""
from __future__ import annotations

import os
import hmac
import secrets
import socket
import sys
from pathlib import Path

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from flask import Flask, Response, jsonify, redirect, request, send_file

from . import hub as _hub
from . import thumbs as _thumbs
from . import niche as _niche
from . import services as _services
from . import jobs as _jobs
from . import workflows as _workflows

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"

_SINGLE_INSTANCE_PORT = 8788  # lock port, distinct from the app's own 8787
_instance_lock_sock = None

CONTROL_TOKEN = secrets.token_urlsafe(24)

app = Flask(__name__)


# ── auth helpers ─────────────────────────────────────────────────────

def _require_token():
    token = request.headers.get("X-Token", "")
    if not hmac.compare_digest(token, CONTROL_TOKEN):
        return jsonify({"error": "invalid or missing X-Token"}), 403
    return None


def _require_localhost():
    host = (request.host or "").split(":")[0]
    if host not in ("127.0.0.1", "localhost"):
        return jsonify({"error": "reveal is only allowed from localhost"}), 403
    return None


def _err(msg, code=400):
    return jsonify({"error": str(msg)}), code


@app.errorhandler(404)
def _not_found(e):
    return jsonify({"error": "not found"}), 404


@app.errorhandler(405)
def _method_not_allowed(e):
    return jsonify({"error": "method not allowed"}), 405


@app.errorhandler(500)
def _server_error(e):
    return jsonify({"error": "internal error"}), 500


# ── static ───────────────────────────────────────────────────────────

_PLACEHOLDER_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Control Center</title></head>
<body style="font-family:sans-serif;background:#111;color:#eee;padding:2rem">
<h1>Control Center</h1>
<p>Frontend not built yet — control/static/index.html is missing.</p>
<p>Token: <code>__CONTROL_TOKEN__</code></p>
</body></html>"""


@app.route("/")
def index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        html = index_path.read_text(encoding="utf-8")
    else:
        html = _PLACEHOLDER_HTML
    html = html.replace("__CONTROL_TOKEN__", CONTROL_TOKEN)
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


# ── overview / health ────────────────────────────────────────────────

@app.route("/api/overview")
def api_overview():
    return jsonify(_services.overview())


@app.route("/api/health")
def api_health():
    return jsonify(_services.health())


# ── products ─────────────────────────────────────────────────────────

@app.route("/api/products")
def api_products():
    return jsonify(_services.products())


@app.route("/api/products/approve", methods=["POST"])
def api_products_approve():
    guard = _require_token()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    url = body.get("url")
    title = body.get("title")
    if not url or not title:
        return _err("url and title are required")
    result = _services.approve(
        url, title,
        image_url=body.get("image_url", ""),
        domain=body.get("domain", ""),
        commission=body.get("commission", ""),
        pending_id=body.get("pending_id", ""),
    )
    if isinstance(result, dict) and result.get("error"):
        return _err(result["error"], 500)
    return jsonify(result)


@app.route("/api/products/reject", methods=["POST"])
def api_products_reject():
    guard = _require_token()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    url = body.get("url")
    title = body.get("title")
    if not url or not title:
        return _err("url and title are required")
    result = _services.reject(url, title, pending_id=body.get("pending_id", ""))
    if isinstance(result, dict) and result.get("error"):
        return _err(result["error"], 500)
    return jsonify(result)


@app.route("/api/products/undo_reject", methods=["POST"])
def api_products_undo_reject():
    guard = _require_token()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    url = body.get("url")
    if not url:
        return _err("url is required")
    result = _services.undo_reject(url)
    if isinstance(result, dict) and result.get("error"):
        return _err(result["error"], 500)
    return jsonify(result)


@app.route("/api/products/add", methods=["POST"])
def api_products_add():
    guard = _require_token()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    url = body.get("url")
    if not url:
        return _err("url is required")
    result = _services.add_product(url)
    if isinstance(result, dict) and result.get("error"):
        return _err(result["error"], 500)
    return jsonify(result)


# ── posts / schedule ─────────────────────────────────────────────────

@app.route("/api/posts")
def api_posts():
    fresh = request.args.get("fresh") == "1"
    result = _services.posts(fresh=fresh)
    if isinstance(result, dict) and result.get("error"):
        return _err(result["error"], 502)
    return jsonify(result)


@app.route("/api/posts/meta")
def api_posts_meta():
    return jsonify({"cached_seconds_ago": _services.posts_cache_age()})


@app.route("/api/posts/move", methods=["POST"])
def api_posts_move():
    guard = _require_token()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    post_id = body.get("id")
    scheduled_for = body.get("scheduledFor")
    if not post_id or not scheduled_for:
        return _err("id and scheduledFor are required")
    result = _services.move_post(post_id, scheduled_for)
    if isinstance(result, dict) and result.get("error"):
        return _err(result["error"], 502)
    return jsonify(result)


@app.route("/api/posts/cancel", methods=["POST"])
def api_posts_cancel():
    guard = _require_token()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    post_id = body.get("id")
    if not post_id:
        return _err("id is required")
    result = _services.cancel_post(post_id)
    if isinstance(result, dict) and result.get("error"):
        return _err(result["error"], 502)
    return jsonify(result)


@app.route("/api/posts/retry", methods=["POST"])
def api_posts_retry():
    guard = _require_token()
    if guard:
        return guard
    result = _services.retry_failed()
    if isinstance(result, dict) and result.get("error"):
        return _err(result["error"], 500)
    return jsonify(result)


# ── affiliates & hub ─────────────────────────────────────────────────

@app.route("/api/registry")
def api_registry():
    result = _services.registry()
    if isinstance(result, dict) and result.get("error"):
        return _err(result["error"], 500)
    return jsonify(result)


@app.route("/api/registry/add", methods=["POST"])
def api_registry_add():
    guard = _require_token()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    domain = body.get("domain")
    if not domain:
        return _err("domain is required")
    result = _services.registry_add(domain)
    if isinstance(result, dict) and result.get("error"):
        return _err(result["error"], 500)
    return jsonify(result)


@app.route("/api/registry/activate", methods=["POST"])
def api_registry_activate():
    guard = _require_token()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    domain = body.get("domain")
    link = body.get("link")
    if not domain or not link:
        return _err("domain and link are required")
    result = _services.registry_activate(domain, link)
    if isinstance(result, dict) and result.get("error"):
        return _err(result["error"], 500)
    return jsonify(result)


@app.route("/api/hub")
def api_hub():
    try:
        hub_data = _hub.load_hub()
        return jsonify({
            "accounts": hub_data.get("accounts", []),
            "links": hub_data.get("links", []),
            "keys": _hub.keys(),
        })
    except Exception as e:
        return _err(e, 500)


@app.route("/api/keys/reveal", methods=["POST"])
def api_keys_reveal():
    guard = _require_token()
    if guard:
        return guard
    guard = _require_localhost()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    name = body.get("name")
    if not name:
        return _err("name is required")
    value = _hub.reveal(name)
    if value is None:
        return _err("not found", 404)
    return jsonify({"name": name, "value": value})


# ── research ─────────────────────────────────────────────────────────

@app.route("/api/trends")
def api_trends():
    result = _services.trends()
    if isinstance(result, dict) and result.get("error"):
        return _err(result["error"], 500)
    return jsonify(result)


@app.route("/api/learning")
def api_learning():
    result = _services.learning()
    if isinstance(result, dict) and result.get("error"):
        return _err(result["error"], 500)
    return jsonify(result)


@app.route("/api/learning/shoes")
def api_learning_shoes():
    result = _services.learning_shoes()
    if isinstance(result, dict) and result.get("error"):
        return _err(result["error"], 500)
    return jsonify(result)


# ── niche / tuning ───────────────────────────────────────────────────

@app.route("/api/niche", methods=["GET", "PUT"])
def api_niche():
    if request.method == "GET":
        try:
            return jsonify(_niche.load())
        except Exception as e:
            return _err(e, 500)
    guard = _require_token()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    try:
        merged = _niche.update(body)
        return jsonify(merged)
    except Exception as e:
        return _err(e, 500)


@app.route("/api/niche/clone", methods=["POST"])
def api_niche_clone():
    guard = _require_token()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    src = body.get("from")
    dst = body.get("to")
    name = body.get("name")
    if not src or not dst or not name:
        return _err("from, to and name are required")
    try:
        result = _niche.clone(src, dst, name)
        return jsonify(result)
    except Exception as e:
        return _err(e, 500)


# ── run jobs ─────────────────────────────────────────────────────────

@app.route("/api/run/<job>", methods=["POST"])
def api_run(job):
    guard = _require_token()
    if guard:
        return guard
    result = _services.run(job)
    if isinstance(result, dict) and result.get("error"):
        return _err(result["error"], 400)
    return jsonify(result)


# ── jobs / workflows ─────────────────────────────────────────────────

@app.route("/api/jobs")
def api_jobs():
    return jsonify(_jobs.list_jobs())


@app.route("/api/jobs/<job_id>")
def api_job_detail(job_id):
    job = _jobs.get(job_id)
    if not job:
        return _err("job not found", 404)
    since = request.args.get("since")
    out = dict(job)
    log = out.get("log", [])
    if since is not None:
        try:
            since_i = max(0, int(since))
        except ValueError:
            since_i = 0
        out["log"] = log[since_i:]
        out["log_offset"] = since_i
    out["log_total"] = len(log)
    out.pop("_cancel", None)
    return jsonify(out)


@app.route("/api/jobs/<job_id>/cancel", methods=["POST"])
def api_job_cancel(job_id):
    guard = _require_token()
    if guard:
        return guard
    ok = _jobs.cancel(job_id)
    if not ok:
        return _err("job not found or not cancellable", 404)
    return jsonify({"ok": True})


@app.route("/api/workflows")
def api_workflows():
    return jsonify(_workflows.list_meta())


@app.route("/api/workflows/<name>", methods=["POST"])
def api_workflow_run(name):
    guard = _require_token()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    dry_run = bool(body.get("dry_run"))
    params = body.get("params") or {}
    result = _workflows.run(name, dry_run=dry_run, params=params)
    if isinstance(result, dict) and result.get("error"):
        return _err(result["error"], 400)
    return jsonify(result)


@app.route("/api/events/summary")
def api_events_summary():
    try:
        ov = _services.overview()
        needs_you = len(ov.get("needs_you", [])) if isinstance(ov, dict) else 0
        posts = ov.get("posts", {}) if isinstance(ov, dict) else {}
        failed_posts = posts.get("failed", 0)
        jl = _jobs.list_jobs()
        running_jobs = len(jl.get("active", []))
        last_metrics_time = ov.get("generated_at") if isinstance(ov, dict) else None
        return jsonify({
            "needs_you": needs_you,
            "running_jobs": running_jobs,
            "failed_posts": failed_posts,
            "last_metrics_time": last_metrics_time,
        })
    except Exception as e:
        return _err(e, 500)


# ── single-instance guard + entrypoint ──────────────────────────────

def acquire_single_instance():
    global _instance_lock_sock
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", _SINGLE_INSTANCE_PORT))
        s.listen(1)
        _instance_lock_sock = s
        return True
    except OSError:
        return False


# ── thumbnails (any product → a picture) ────────────────────────────
@app.route("/api/thumb")
def api_thumb():
    kind, val = _thumbs.resolve(request.args.get("url", ""), request.args.get("slug", ""))
    if kind == "file":
        return send_file(val, max_age=86400)
    if kind == "url":
        return redirect(val, 302)
    return Response(_thumbs.PLACEHOLDER_SVG, mimetype="image/svg+xml")


# ── shutdown (header "סגור" button) ─────────────────────────────────
@app.route("/api/shutdown", methods=["POST"])
def api_shutdown():
    guard = _require_token()
    if guard:
        return guard
    import threading
    threading.Timer(0.5, lambda: os._exit(0)).start()   # let the response flush first
    return jsonify({"ok": True})



def main():
    if not acquire_single_instance():
        # Another instance is already running — exit quietly.
        return
    app.run(host="127.0.0.1", port=8787, debug=False)


if __name__ == "__main__":
    main()
