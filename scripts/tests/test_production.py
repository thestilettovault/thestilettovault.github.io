# -*- coding: utf-8 -*-
import os, sys, json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import orchestrator as orch  # noqa: E402

LONG = "2026-10-13/stiletto-heels-with-a-very-long-title-for-testing-3256812471729513-xx"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(orch, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(orch, "QUEUE_FILE", tmp_path / "queue.json")
    monkeypatch.setattr(orch, "GELEM", tmp_path / "GELEM")
    return tmp_path


def test_slug_of():
    assert orch.slug_of("GELEM/2026-10-13/stiletto-heels-1") == "2026-10-13/stiletto-heels-1"
    assert orch.slug_of("GELEM" + chr(92) + "2026-10-13" + chr(92) + "x") == "2026-10-13/x"
    assert orch.slug_of("2026-10-13/x") == "2026-10-13/x"


def test_short_callback_and_resolve(env):
    assert len(LONG.encode()) > 40
    for data in (orch.make_callback("adpick", LONG, "A"), orch.make_callback("boardrun", LONG)):
        assert len(data.encode("utf-8")) <= 64
    ad = orch.make_callback("adpick", LONG, "A")
    action, tok, letter = ad.split("|")
    assert tok != LONG and letter == "A"
    assert orch.resolve_cb(tok) == LONG
    # old-format buttons (full slug) still resolve, and short slugs keep the old format
    assert orch.resolve_cb(LONG) == LONG
    assert orch.make_callback("boardrun", "2026-10-13/a") == "boardrun|2026-10-13/a"


def test_record_choice_guard(env):
    slug = "2026-10-13/x"
    (orch.GELEM / slug).mkdir(parents=True)
    (orch.GELEM / slug / "ad_A.jpg").write_bytes(b"x")
    ok, msg = orch.record_choice(slug, "A")           # no state yet
    assert not ok and "already handled" in msg
    orch.set_state(slug, status="finalized")
    assert not orch.record_choice(slug, "A")[0]
    orch.set_state(slug, status="awaiting_choice")
    assert orch.record_choice(slug, "A") == (True, "ad_A.jpg")
    assert orch.get_state(slug)["status"] == "chosen"
    assert orch.record_choice(slug, "A")[0]            # re-pick allowed while chosen
    assert not orch.record_choice(slug, "D")[0]        # missing file


def test_claim_collect_double(env):
    slug = "2026-10-13/x"
    assert not orch.claim_collect(slug)
    orch.set_state(slug, status="board_ready")
    assert orch.claim_collect(slug) is True
    assert orch.claim_collect(slug) is False
    assert orch.get_state(slug)["status"] == "collecting"
    orch.set_status(slug, "board_ready")
    assert orch.claim_collect(slug) is True


def test_queue_set(env):
    (env / "queue.json").write_text(json.dumps(
        [{"local_asset": "GELEM/2026-10-13/x", "status": "approved"},
         {"local_asset": "GELEM/2026-10-14/y", "status": "approved"}]), encoding="utf-8")
    assert orch.queue_set("2026-10-13/x", "board_ready")
    q = json.loads((env / "queue.json").read_text(encoding="utf-8"))
    assert [e["status"] for e in q] == ["board_ready", "approved"]
    assert not orch.queue_set("nope/none", "x")


def test_atomic_save_roundtrip(env):
    st = {"a/b": {"status": "x", "n": 1}, "heb": {"t": "שלום"}}
    orch._save(st)
    assert orch._load() == st
    assert not list(env.glob("*.tmp")) and not list(env.glob("*.lock"))
    orch.set_state("a/b", n=2)
    assert orch._load()["a/b"] == {"status": "x", "n": 2}


def test_stale_lock_is_broken(env):
    lock = Path(str(orch.STATE_FILE) + ".lock")
    lock.write_text("")
    old = lock.stat().st_mtime - 120
    os.utime(lock, (old, old))
    orch.set_state("s", status="ok")
    assert orch.get_state("s")["status"] == "ok"


def test_claim_collect_recovers_stale_and_legacy(env):
    slug = "2026-10-13/stale-shoe"
    orch.set_state(slug, status="collecting", collect_ts=0)      # crashed run long ago
    assert orch.claim_collect(slug) is True
    assert orch.claim_collect(slug) is False                     # fresh claim blocks
    orch.set_state(slug, status="run_clicked")                   # legacy status
    assert orch.claim_collect(slug) is True
