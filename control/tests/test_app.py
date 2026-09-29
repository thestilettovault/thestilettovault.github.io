# -*- coding: utf-8 -*-
import json

import pytest

from control import app as control_app


@pytest.fixture()
def client():
    control_app.app.config["TESTING"] = True
    with control_app.app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _stub_services(monkeypatch):
    monkeypatch.setattr(control_app._services, "overview", lambda: {"ok": True})
    monkeypatch.setattr(control_app._services, "health", lambda: {"ok": True})
    monkeypatch.setattr(control_app._services, "products", lambda: [])
    monkeypatch.setattr(control_app._services, "posts", lambda fresh=False: [])
    monkeypatch.setattr(control_app._services, "posts_cache_age", lambda: None)
    monkeypatch.setattr(control_app._services, "registry", lambda: [])
    monkeypatch.setattr(control_app._services, "trends", lambda: [])
    monkeypatch.setattr(control_app._services, "learning", lambda: {"rows": [], "summary": [], "insights": []})
    monkeypatch.setattr(control_app._services, "learning_shoes", lambda: [])
    yield


def test_get_routes_do_not_need_token(client):
    for path in ["/api/overview", "/api/health", "/api/products", "/api/posts",
                 "/api/registry", "/api/trends", "/api/learning"]:
        r = client.get(path)
        assert r.status_code == 200, path


def test_post_without_token_is_403(client):
    r = client.post("/api/products/approve", json={"url": "u", "title": "t"})
    assert r.status_code == 403
    assert "error" in r.get_json()


def test_post_with_wrong_token_is_403(client):
    r = client.post("/api/products/approve", json={"url": "u", "title": "t"},
                     headers={"X-Token": "wrong"})
    assert r.status_code == 403


def test_post_with_correct_token_is_200(client, monkeypatch):
    monkeypatch.setattr(control_app._services, "approve", lambda *a, **k: {"ok": True})
    r = client.post("/api/products/approve", json={"url": "u", "title": "t"},
                     headers={"X-Token": control_app.CONTROL_TOKEN})
    assert r.status_code == 200
    assert r.get_json() == {"ok": True}


def test_undo_reject_requires_token(client):
    r = client.post("/api/products/undo_reject", json={"url": "u"})
    assert r.status_code == 403


def test_undo_reject_with_token(client, monkeypatch):
    monkeypatch.setattr(control_app._services, "undo_reject", lambda url: {"ok": True, "removed": True})
    r = client.post("/api/products/undo_reject", json={"url": "u"},
                     headers={"X-Token": control_app.CONTROL_TOKEN})
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "removed": True}


def test_learning_shoes_route(client):
    r = client.get("/api/learning/shoes")
    assert r.status_code == 200
    assert r.get_json() == []


def test_posts_meta_route(client):
    r = client.get("/api/posts/meta")
    assert r.status_code == 200
    assert r.get_json() == {"cached_seconds_ago": None}


def test_run_unknown_job_rejected(client):
    r = client.post("/api/run/nuke", headers={"X-Token": control_app.CONTROL_TOKEN})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_reveal_requires_token_and_localhost(client, monkeypatch):
    monkeypatch.setattr(control_app._hub, "reveal", lambda name: "secretvalue")
    # no token
    r = client.post("/api/keys/reveal", json={"name": "X"})
    assert r.status_code == 403
    # token but non-localhost host header
    r = client.post("/api/keys/reveal", json={"name": "X"},
                     headers={"X-Token": control_app.CONTROL_TOKEN, "Host": "evil.com"})
    assert r.status_code == 403
    # token + localhost host
    r = client.post("/api/keys/reveal", json={"name": "X"},
                     headers={"X-Token": control_app.CONTROL_TOKEN, "Host": "127.0.0.1:8787"})
    assert r.status_code == 200
    assert r.get_json()["value"] == "secretvalue"


def test_errors_are_json_not_html(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.is_json
    assert "error" in r.get_json()


def test_hub_route_masks_keys(client, monkeypatch):
    monkeypatch.setattr(control_app._hub, "load_hub", lambda: {"accounts": [{"a": 1}], "links": []})
    monkeypatch.setattr(control_app._hub, "keys", lambda: [
        {"name": "SECRET_KEY", "masked": "abcd…xyz", "set": True, "updated": None}
    ])
    r = client.get("/api/hub")
    body = r.get_json()
    assert body["keys"][0]["masked"] == "abcd…xyz"
    body_text = json.dumps(body)
    assert "SECRETVALUE_RAW" not in body_text


def test_posts_move_and_cancel_require_fields(client):
    r = client.post("/api/posts/move", json={}, headers={"X-Token": control_app.CONTROL_TOKEN})
    assert r.status_code == 400
    r = client.post("/api/posts/cancel", json={}, headers={"X-Token": control_app.CONTROL_TOKEN})
    assert r.status_code == 400


def test_niche_get_and_put(client, monkeypatch):
    monkeypatch.setattr(control_app._niche, "load", lambda: {"a": 1})
    r = client.get("/api/niche")
    assert r.get_json() == {"a": 1}

    monkeypatch.setattr(control_app._niche, "update", lambda body: {"a": 2, **body})
    r = client.put("/api/niche", json={"b": 3},
                    headers={"X-Token": control_app.CONTROL_TOKEN})
    assert r.status_code == 200
    assert r.get_json() == {"a": 2, "b": 3}

    r = client.put("/api/niche", json={"b": 3})
    assert r.status_code == 403


def test_workflows_list_get_no_token(client):
    r = client.get("/api/workflows")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_workflow_run_requires_token(client):
    r = client.post("/api/workflows/refresh_all", json={"dry_run": True})
    assert r.status_code == 403


def test_workflow_dry_run_with_token(client):
    r = client.post("/api/workflows/refresh_all", json={"dry_run": True},
                     headers={"X-Token": control_app.CONTROL_TOKEN})
    assert r.status_code == 200
    data = r.get_json()
    assert data["dry_run"] is True
    assert isinstance(data["plan"], list)


def test_workflow_unknown_name_errors(client):
    r = client.post("/api/workflows/does_not_exist", json={"dry_run": True},
                     headers={"X-Token": control_app.CONTROL_TOKEN})
    assert r.status_code == 400


def test_jobs_list_no_token_needed(client):
    r = client.get("/api/jobs")
    assert r.status_code == 200
    data = r.get_json()
    assert "active" in data and "recent" in data


def test_job_detail_not_found(client):
    r = client.get("/api/jobs/doesnotexist")
    assert r.status_code == 404


def test_job_cancel_requires_token(client):
    r = client.post("/api/jobs/whatever/cancel")
    assert r.status_code == 403


def test_events_summary(client):
    r = client.get("/api/events/summary")
    assert r.status_code == 200
    data = r.get_json()
    assert "needs_you" in data and "running_jobs" in data and "failed_posts" in data
