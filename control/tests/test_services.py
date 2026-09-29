# -*- coding: utf-8 -*-
import json
import sys
import types
from pathlib import Path

import pytest

from control import services


@pytest.fixture(autouse=True)
def _no_real_scripts_path(monkeypatch):
    # keep scripts/ on sys.path (services adds it at import time already)
    yield


@pytest.fixture(autouse=True)
def _reset_posts_cache(monkeypatch):
    # posts_list() now caches for 60s — each test starts with a clean cache
    monkeypatch.setattr(services, "_POSTS_CACHE", {"ts": 0.0, "data": None})
    yield


def test_overview_reads_dashboard_and_needs_you(tmp_path, monkeypatch):
    dash = tmp_path / "dashboard"
    dash.mkdir()
    (dash / "data.json").write_text(json.dumps({
        "funnel": {"scanned": 1}, "sales": {"total_sales": 2},
        "traffic": {}, "followers": {}, "generated_at": "now",
        "shoes": [{"slug": "a"}],
    }), encoding="utf-8")

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "orchestrator_state.json").write_text(json.dumps({
        "shoe1": {"status": "awaiting_choice"},
        "shoe2": {"status": "finalized"},
    }), encoding="utf-8")
    (data_dir / "affiliate_registry.json").write_text(json.dumps({
        "brands": {"brand.com": {"status": "carded", "value_per_sale": 5}}
    }), encoding="utf-8")

    monkeypatch.setattr(services, "DASH", dash)
    monkeypatch.setattr(services, "DATA", data_dir)
    monkeypatch.setattr(services, "posts_list", lambda: [
        {"id": "1", "status": "failed", "content": "x"},
        {"id": "2", "status": "scheduled", "content": "y"},
    ])

    out = services.overview()
    assert out["funnel"] == {"scanned": 1}
    assert out["shoes_count"] == 1
    assert out["posts"] == {"scheduled": 1, "published": 0, "failed": 1}
    kinds = {n["kind"] for n in out["needs_you"]}
    assert "awaiting_choice" in kinds
    assert "affiliate_carded" in kinds
    assert "post_failed" in kinds


def test_overview_error_is_json_able(monkeypatch):
    def boom():
        raise RuntimeError("kaboom")
    monkeypatch.setattr(services, "_posts_summary", boom)
    out = services.overview()
    assert "error" in out


def test_posts_list_maps_real_zernio_shape(monkeypatch):
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"posts": [{
                "_id": "abc123",
                "content": "hello world " * 20,
                "scheduledFor": "2026-09-30T20:00:00.000Z",
                "status": "scheduled",
                "mediaItems": [{"url": "http://x/video.mp4", "type": "video"}],
                "platforms": [
                    {"platform": "tiktok", "status": "scheduled"},
                    {"platform": "instagram", "status": "scheduled",
                     "platformPostUrl": "https://instagram.com/p/xyz"},
                ],
            }]}

    def fake_get(url, headers=None, params=None, timeout=None):
        assert url.endswith("/posts")
        assert headers["Authorization"].startswith("Bearer ")
        return FakeResp()

    fake_requests = types.SimpleNamespace(get=fake_get)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setattr(services, "_zernio", lambda: ("https://api.zernio.com/v1", "SECRETKEY"))

    out = services.posts_list()
    assert isinstance(out, list) and len(out) == 1
    p = out[0]
    assert p["id"] == "abc123"
    assert len(p["content"]) <= 120
    assert p["status"] == "scheduled"
    assert p["platforms"] == ["tiktok", "instagram"]
    assert p["url"] == "https://instagram.com/p/xyz"
    assert p["media_type"] == "video"


def test_posts_list_error_is_json_able(monkeypatch):
    def fake_get(*a, **k):
        raise ConnectionError("no network")
    fake_requests = types.SimpleNamespace(get=fake_get)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setattr(services, "_zernio", lambda: ("https://api.zernio.com/v1", "K"))
    out = services.posts_list()
    assert "error" in out


def test_move_post_sends_put_to_correct_url(monkeypatch):
    calls = {}

    def fake_put(url, headers=None, json=None, timeout=None):
        calls["url"] = url
        calls["json"] = json
        return types.SimpleNamespace(status_code=200, text="")

    fake_requests = types.SimpleNamespace(put=fake_put)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setattr(services, "_zernio", lambda: ("https://api.zernio.com/v1", "K"))

    out = services.move_post("post1", "2026-10-01T10:00:00.000Z")
    assert out == {"ok": True}
    assert calls["url"] == "https://api.zernio.com/v1/posts/post1"
    assert calls["json"] == {"scheduledFor": "2026-10-01T10:00:00.000Z"}


def test_cancel_post_sends_delete(monkeypatch):
    calls = {}

    def fake_delete(url, headers=None, timeout=None):
        calls["url"] = url
        return types.SimpleNamespace(status_code=204, text="")

    fake_requests = types.SimpleNamespace(delete=fake_delete)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setattr(services, "_zernio", lambda: ("https://api.zernio.com/v1", "K"))

    out = services.cancel_post("post9")
    assert out == {"ok": True}
    assert calls["url"] == "https://api.zernio.com/v1/posts/post9"


def test_registry_activate_sets_fields(monkeypatch):
    fake_heel_hunter = types.SimpleNamespace(
        activate_one=lambda domain, link: {
            "domain": domain, "our_id": link, "status": "active",
            "affiliate_ref": "?ref=abc",
        }
    )
    monkeypatch.setitem(sys.modules, "heel_hunter", fake_heel_hunter)
    out = services.registry_activate("brand.com", "https://x?ref=abc")
    assert out["status"] == "active"
    assert out["our_id"] == "https://x?ref=abc"


def test_registry_error_is_json_able(monkeypatch):
    def boom():
        raise RuntimeError("registry broke")
    fake_heel_hunter = types.SimpleNamespace(load_reg=boom)
    monkeypatch.setitem(sys.modules, "heel_hunter", fake_heel_hunter)
    out = services.registry()
    assert "error" in out


def test_run_rejects_unknown_job():
    out = services.run("delete_everything")
    assert "error" in out


def test_run_metrics_no_push_flag(monkeypatch):
    captured = {}

    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        captured["cmd"] = cmd
        return types.SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(services.subprocess, "run", fake_run)
    out = services.run("metrics")
    assert out["ok"] is True
    assert "--push" not in captured["cmd"]


def test_run_tiktok_retry_uses_apply_flag(monkeypatch):
    captured = {}

    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        captured["cmd"] = cmd
        return types.SimpleNamespace(returncode=0, stdout="done", stderr="")

    monkeypatch.setattr(services.subprocess, "run", fake_run)
    out = services.run("tiktok_retry")
    assert out["ok"] is True
    assert "--apply" in captured["cmd"]


def test_approve_and_reject_call_taste_engine(monkeypatch):
    calls = []
    fake_taste = types.SimpleNamespace(
        record_approval=lambda *a, **k: calls.append(("approve", a, k)),
        record_rejection=lambda *a, **k: calls.append(("reject", a, k)),
    )
    monkeypatch.setitem(sys.modules, "taste_engine", fake_taste)
    out1 = services.approve("http://x", "Title")
    out2 = services.reject("http://x", "Title")
    assert out1 == {"ok": True}
    assert out2 == {"ok": True}
    assert calls[0][0] == "approve"
    assert calls[1][0] == "reject"


def test_approve_error_is_json_able(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("disk full")
    fake_taste = types.SimpleNamespace(record_approval=boom)
    monkeypatch.setitem(sys.modules, "taste_engine", fake_taste)
    out = services.approve("http://x", "Title")
    assert "error" in out


def test_approve_with_pending_id_removes_pending(monkeypatch):
    calls = []
    fake_taste = types.SimpleNamespace(
        record_approval=lambda *a, **k: calls.append(("approve", a, k)),
        remove_pending=lambda pid: calls.append(("remove", pid)),
    )
    monkeypatch.setitem(sys.modules, "taste_engine", fake_taste)
    out = services.approve("http://x", "Title", pending_id="abc123")
    assert out == {"ok": True}
    assert ("remove", "abc123") in calls


def test_reject_with_pending_id_removes_pending(monkeypatch):
    calls = []
    fake_taste = types.SimpleNamespace(
        record_rejection=lambda *a, **k: calls.append(("reject", a, k)),
        remove_pending=lambda pid: calls.append(("remove", pid)),
    )
    monkeypatch.setitem(sys.modules, "taste_engine", fake_taste)
    out = services.reject("http://x", "Title", pending_id="xyz")
    assert out == {"ok": True}
    assert ("remove", "xyz") in calls


def test_undo_reject_removes_matching_entry(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "rejected_profile.json").write_text(json.dumps({
        "rejected": [
            {"title": "Bag", "link": "https://example.com/a?x=1", "date": "2026-01-01"},
            {"title": "Other", "link": "https://example.com/b", "date": "2026-01-02"},
        ]
    }), encoding="utf-8")
    monkeypatch.setattr(services, "DATA", data_dir)

    out = services.undo_reject("https://EXAMPLE.com/a")
    assert out == {"ok": True, "removed": True}
    remaining = json.loads((data_dir / "rejected_profile.json").read_text(encoding="utf-8"))
    assert len(remaining["rejected"]) == 1
    assert remaining["rejected"][0]["link"] == "https://example.com/b"


def test_undo_reject_no_match_is_noop(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "rejected_profile.json").write_text(json.dumps({"rejected": []}), encoding="utf-8")
    monkeypatch.setattr(services, "DATA", data_dir)
    out = services.undo_reject("https://nope.com/x")
    assert out == {"ok": True, "removed": False}


def test_products_merges_all_sources_by_stage(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    dash_dir = tmp_path / "dashboard"
    data_dir.mkdir()
    dash_dir.mkdir()

    (data_dir / "pending_reviews.json").write_text(json.dumps({
        "pid1": {"url": "https://a.com/p1", "title": "Pending One",
                 "image_url": "", "commission": "5%", "domain": "a.com", "ts": "2026-01-01"},
    }), encoding="utf-8")
    (data_dir / "rejected_profile.json").write_text(json.dumps({
        "rejected": [{"title": "Rejected One", "link": "https://b.com/p2", "date": "2026-01-01"}],
    }), encoding="utf-8")
    (data_dir / "approved_catalog.json").write_text(json.dumps([
        {"title": "Approved One", "url": "https://c.com/p3", "aff_link": "https://c.com/p3",
         "domain": "c.com", "image_url": "", "commission": "4%", "date": "2026-01-01"},
    ]), encoding="utf-8")
    (data_dir / "aliexpress_pool.json").write_text(json.dumps({
        "products": [{"title": "Pool One", "url": "https://d.com/p4", "aff_link": "https://d.com/p4",
                      "image_url": "", "price": 20, "deal": {}, "commission": "6%", "domain": "d.com"}],
    }), encoding="utf-8")
    (data_dir / "orchestrator_state.json").write_text("{}", encoding="utf-8")
    (dash_dir / "data.json").write_text(json.dumps({"shoes": []}), encoding="utf-8")

    monkeypatch.setattr(services, "DATA", data_dir)
    monkeypatch.setattr(services, "DASH", dash_dir)

    out = services.products()
    assert isinstance(out, list)
    stages = {row["title"]: row["stage"] for row in out}
    assert stages["Pending One"] == "pending"
    assert "Rejected One" not in stages   # rejected = internal memory only, never listed
    assert stages["Approved One"] == "approved"
    assert stages["Pool One"] == "pool"


def test_products_dedupes_by_normalized_url(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    dash_dir = tmp_path / "dashboard"
    data_dir.mkdir()
    dash_dir.mkdir()

    (data_dir / "pending_reviews.json").write_text("{}", encoding="utf-8")
    (data_dir / "rejected_profile.json").write_text(json.dumps({"rejected": []}), encoding="utf-8")
    (data_dir / "approved_catalog.json").write_text(json.dumps([
        {"title": "Same Item", "url": "https://www.example.com/item?x=1", "aff_link": "",
         "domain": "example.com", "image_url": "", "commission": "", "date": ""},
    ]), encoding="utf-8")
    (data_dir / "aliexpress_pool.json").write_text(json.dumps({
        "products": [{"title": "Same Item", "url": "https://example.com/item/", "aff_link": "",
                      "image_url": "", "price": 10, "deal": {}, "commission": "", "domain": ""}],
    }), encoding="utf-8")
    (data_dir / "orchestrator_state.json").write_text("{}", encoding="utf-8")
    (dash_dir / "data.json").write_text(json.dumps({"shoes": []}), encoding="utf-8")

    monkeypatch.setattr(services, "DATA", data_dir)
    monkeypatch.setattr(services, "DASH", dash_dir)

    out = services.products()
    assert len(out) == 1
    assert out[0]["stage"] == "approved"  # approved wins over pool for the same URL


def test_posts_list_caches_within_ttl(monkeypatch):
    calls = {"n": 0}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            calls["n"] += 1
            return {"posts": []}

    def fake_get(*a, **k):
        return FakeResp()

    fake_requests = types.SimpleNamespace(get=fake_get)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setattr(services, "_zernio", lambda: ("https://api.zernio.com/v1", "K"))

    services.posts_list()
    services.posts_list()
    assert calls["n"] == 1  # second call served from cache

    services.posts_list(fresh=True)
    assert calls["n"] == 2  # fresh=True bypasses the cache
