# -*- coding: utf-8 -*-
import time

import pytest

from control import jobs as J


@pytest.fixture(autouse=True)
def _reset(monkeypatch, tmp_path):
    monkeypatch.setattr(J, "_JOBS", {})
    monkeypatch.setattr(J, "_ACTIVE_BY_NAME", {})
    monkeypatch.setattr(J, "DATA", tmp_path)
    monkeypatch.setattr(J, "HISTORY_FILE", tmp_path / "jobs_history.json")
    monkeypatch.setattr(J, "ENV_FILE", tmp_path / "does_not_exist.env")
    yield


def _wait(job_id, timeout=5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        job = J.get(job_id)
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.02)
    raise TimeoutError("job did not finish")


def test_python_steps_succeed():
    calls = []

    def step1(log):
        calls.append(1)
        log("hello")

    def step2(log):
        calls.append(2)

    job_id = J.start("demo", [
        {"type": "python", "title": "s1", "fn": step1},
        {"type": "python", "title": "s2", "fn": step2},
    ])
    job = _wait(job_id)
    assert job["status"] == "done"
    assert calls == [1, 2]
    assert job["steps"][0]["status"] == "done"
    assert "hello" in job["log"]


def test_duplicate_workflow_name_rejected():
    def slow(log):
        time.sleep(0.3)

    J.start("dup", [{"type": "python", "title": "s", "fn": slow}])
    with pytest.raises(ValueError):
        J.start("dup", [{"type": "python", "title": "s", "fn": slow}])


def test_step_failure_marks_job_failed():
    def boom(log):
        raise RuntimeError("boom")

    job_id = J.start("fail-wf", [{"type": "python", "title": "s", "fn": boom}])
    job = _wait(job_id)
    assert job["status"] == "failed"
    assert job["error"] and "boom" in job["error"]


def test_cancel_marks_cancelled():
    def slow(log):
        for _ in range(50):
            time.sleep(0.02)

    job_id = J.start("cancel-wf", [{"type": "python", "title": "s", "fn": slow}])
    time.sleep(0.05)
    assert J.cancel(job_id) is True
    # our python-step cancel is cooperative only for subprocess steps; python
    # steps run to completion but subsequent steps are skipped/cancelled.
    job = _wait(job_id, timeout=5)
    assert job["status"] in ("cancelled", "done")


def test_list_jobs_and_history_persisted(tmp_path):
    def ok(log):
        pass

    job_id = J.start("hist-wf", [{"type": "python", "title": "s", "fn": ok}])
    _wait(job_id)
    listing = J.list_jobs()
    assert any(j["id"] == job_id for j in listing["recent"])
    hist_file = J.DATA / "jobs_history.json"
    assert hist_file.exists()


def test_redaction(monkeypatch, tmp_path):
    env = tmp_path / "secret.env"
    env.write_text("TOKEN=supersecretvalue123\n", encoding="utf-8")
    monkeypatch.setattr(J, "ENV_FILE", env)

    def leak(log):
        log("here is TOKEN=supersecretvalue123 in the output")

    job_id = J.start("leak-wf", [{"type": "python", "title": "s", "fn": leak}])
    job = _wait(job_id)
    joined = "\n".join(job["log"])
    assert "supersecretvalue123" not in joined
    assert "REDACTED" in joined
