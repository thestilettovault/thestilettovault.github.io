# -*- coding: utf-8 -*-
import datetime
import json

import pytest

from control import workflows as W
from control import jobs as J


@pytest.fixture(autouse=True)
def _reset_jobs(monkeypatch):
    monkeypatch.setattr(J, "_JOBS", {})
    monkeypatch.setattr(J, "_ACTIVE_BY_NAME", {})
    yield


def test_list_meta_has_all_nine_workflows():
    names = {m["name"] for m in W.list_meta()}
    expected = {
        "refresh_all", "scout_now", "schedule_chosen", "fill_gaps",
        "retry_failed", "produce_queue", "publish_dashboard",
        "resend_choices", "activate_brands_from_telegram",
    }
    assert expected.issubset(names)


def test_refresh_all_dry_run_is_side_effect_free(monkeypatch):
    result = W.run("refresh_all", dry_run=True)
    assert result["dry_run"] is True
    assert isinstance(result["plan"], list) and result["plan"]


def test_unknown_workflow_errors():
    result = W.run("does_not_exist", dry_run=True)
    assert "error" in result


def test_next_free_days_skips_busy_and_weekday():
    today = datetime.date(2026, 9, 29)  # a Tuesday
    posts = [
        {"status": "scheduled", "scheduledFor": (today + datetime.timedelta(days=1)).isoformat() + "T16:00:00Z"},
    ]
    days = W._next_free_days(2, posts, skip_weekdays=[5], start=today)
    assert len(days) == 2
    assert (today + datetime.timedelta(days=1)).isoformat() not in days
    for d in days:
        dt = datetime.date.fromisoformat(d)
        assert dt.weekday() != 5


def test_schedule_chosen_plan_lists_slug_to_date(monkeypatch):
    monkeypatch.setattr(W, "_chosen_slugs", lambda: ["shoe-a", "shoe-b"])
    monkeypatch.setattr(W._services, "posts", lambda fresh=False: [])
    monkeypatch.setattr(W._niche, "cfg", lambda path, default=None:
                         [5] if path == "schedule.skip_weekdays" else (["16:00"] if path == "schedule.slots" else default))
    plan = W._schedule_chosen_plan({})
    assert len(plan) == 2
    assert "shoe-a" in plan[0] and "→" in plan[0]
    assert "shoe-b" in plan[1]


def test_schedule_chosen_steps_pairs_finalize_and_pickup_drop(monkeypatch):
    monkeypatch.setattr(W, "_chosen_slugs", lambda: ["shoe-a"])
    monkeypatch.setattr(W._services, "posts", lambda fresh=False: [])
    monkeypatch.setattr(W._niche, "cfg", lambda path, default=None:
                         [5] if path == "schedule.skip_weekdays" else (["16:00"] if path == "schedule.slots" else default))
    steps = W._schedule_chosen_steps({})
    assert len(steps) == 2
    assert "orchestrator.py" in steps[0]["cmd"][2] or "orchestrator.py" in " ".join(steps[0]["cmd"])
    assert "finalize" in steps[0]["cmd"]
    assert "pickup_drop.py" in " ".join(steps[1]["cmd"])
    assert "--push" in steps[1]["cmd"] and "--publish" in steps[1]["cmd"]


def test_schedule_chosen_no_shoes_reports_none(monkeypatch):
    monkeypatch.setattr(W, "_chosen_slugs", lambda: [])
    plan = W._schedule_chosen_plan({})
    assert plan == ["אין נעליים במצב 'נבחר' לשיבוץ כרגע"]
    assert W._schedule_chosen_steps({}) == []


def test_fill_gaps_is_report_only_and_never_runs_a_job():
    result = W.run("fill_gaps", dry_run=False)
    assert result["ran"] is False
    assert "report" in result
    assert not J.list_jobs()["active"]
    assert not J.list_jobs()["recent"]


def test_retry_failed_real_run_requires_apply_flag(monkeypatch):
    captured = {}

    def fake_start(name, steps, params=None):
        captured["steps"] = steps
        return "job123"

    monkeypatch.setattr(J, "start", fake_start)
    result = W.run("retry_failed", dry_run=False)
    assert result["job_id"] == "job123"
    cmd = captured["steps"][0]["cmd"]
    assert "tiktok_retry.py" in " ".join(cmd)
    assert "--apply" in cmd


def test_produce_queue_never_auto_runs_without_explicit_call(monkeypatch):
    meta = {m["name"]: m for m in W.list_meta()}
    assert meta["produce_queue"]["needs_confirm"] is True


def test_duplicate_run_returns_error_not_exception(monkeypatch):
    def slow(log):
        import time
        time.sleep(0.3)

    monkeypatch.setattr(W, "_refresh_all_steps", lambda params: [{"type": "python", "title": "s", "fn": slow}])
    r1 = W.run("refresh_all", dry_run=False)
    assert "job_id" in r1
    r2 = W.run("refresh_all", dry_run=False)
    assert "error" in r2
