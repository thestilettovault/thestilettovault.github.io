import sys, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))

import morning_brief as mb
from control import services, engagement

TZ = mb._tz()
NOW = datetime.datetime(2026, 10, 16, 7, 30, tzinfo=TZ)


def _iso(dt):
    return dt.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _setup(monkeypatch, tmp_path, orch=None, queue=None, posts=None, eng=None, alerts=None):
    monkeypatch.setattr(mb, "DATA", tmp_path)
    monkeypatch.setattr(mb, "STATE", tmp_path / "brief_state.json")
    monkeypatch.setattr(mb, "HERE", tmp_path)          # no logs
    import jsonio
    jsonio.save(tmp_path / "orchestrator_state.json", orch or {})
    jsonio.save(tmp_path / "production_queue.json", queue or [])
    jsonio.save(tmp_path / "account_alerts.json", {"alerts": alerts or []})
    monkeypatch.setattr(mb, "ROOT", tmp_path)
    (tmp_path / "dashboard").mkdir(exist_ok=True)
    jsonio.save(tmp_path / "dashboard" / "data.json",
                {"sales": {"total_sales": 2, "total_revenue": 5.0, "total_clicks": 120}})
    monkeypatch.setattr(services, "zernio_all_posts", lambda **k: posts if posts is not None else [])
    monkeypatch.setattr(engagement, "_fetch", lambda: eng or {
        "totals": {"likes": 50}, "followers": {"instagram": {"count": 110}, "tiktok": {"count": 40}},
        "followers_total": 150})


def test_needs_ofer_incl_stuck_collecting(monkeypatch, tmp_path):
    old = NOW.timestamp() - 3600
    orch = {"2026-10-16/a-lead": {"status": "board_ready"},
            "b-lead": {"status": "awaiting_choice"},
            "c-lead": {"status": "collecting", "ts": old},
            "d-lead": {"status": "collecting", "ts": NOW.timestamp() - 60},
            "_meta": {"status": "board_ready"},
            "e-lead": {"status": "finalized"}}
    _setup(monkeypatch, tmp_path, orch=orch)
    text, data = mb.build_brief(NOW, state={})
    slugs = [s for s, _ in data["needs"]]
    assert slugs == ["a-lead", "b-lead", "c-lead"]
    assert "a-lead" in text and "c-lead" in text and "d-lead" not in text


def test_nothing_waiting(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    text, _ = mb.build_brief(NOW, state={})
    assert "אין משהו שמחכה לך" in text


def test_today_posts_local_tz(monkeypatch, tmp_path):
    t16 = NOW.replace(hour=16, minute=0)
    late = NOW.replace(hour=23, minute=30)          # 20:30 UTC, still today locally
    tomorrow = NOW + datetime.timedelta(days=1)
    posts = [{"status": "scheduled", "scheduledFor": _iso(t16), "platforms": [{"platform": "instagram"}]},
             {"status": "scheduled", "scheduledFor": _iso(t16), "platforms": [{"platform": "tiktok"}]},
             {"status": "scheduled", "scheduledFor": _iso(late), "platforms": [{"platform": "tiktok"}]},
             {"status": "scheduled", "scheduledFor": _iso(tomorrow), "platforms": [{"platform": "tiktok"}]}]
    _setup(monkeypatch, tmp_path, posts=posts)
    text, data = mb.build_brief(NOW, state={})
    assert len(data["posts"]["today"]) == 3
    assert "16:00 IG" in text and "16:00 TT" in text and "23:30 TT" in text


def test_failed_and_published_yesterday(monkeypatch, tmp_path):
    y = NOW - datetime.timedelta(days=1)
    posts = [{"status": "published", "publishedAt": _iso(y), "platforms": [{"platform": "instagram"}]},
             {"status": "failed", "updatedAt": _iso(NOW - datetime.timedelta(days=1)),
              "content": "boom", "platforms": [{"platform": "tiktok"}]},
             {"status": "failed", "updatedAt": _iso(NOW - datetime.timedelta(days=9)),
              "platforms": [{"platform": "tiktok"}]}]
    _setup(monkeypatch, tmp_path, posts=posts)
    text, data = mb.build_brief(NOW, state={})
    assert data["posts"]["published_yesterday"] == 1
    assert len(data["posts"]["failed"]) == 1
    assert "תקלות" in text and "פוסט נכשל" in text


def test_deltas_vs_snapshot(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    prev = {"engagement": {"likes": 40, "followers": {"instagram": 100, "tiktok": 38}, "followers_total": 138},
            "sales": {"clicks": 100}}
    text, data = mb.build_brief(NOW, state=prev)
    assert "+10 לייקים" in text
    assert "+12 עוקבים" in text and "IG +10" in text and "TT +2" in text
    assert "קליקים +20" in text
    assert data["deltas"]["likes"] == 10


def test_failing_sources_still_build(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    def boom(**k):
        raise RuntimeError("down")
    monkeypatch.setattr(services, "zernio_all_posts", boom)
    monkeypatch.setattr(engagement, "_fetch", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    text, data = mb.build_brief(NOW, state={})
    assert "Zernio לא זמין" in text and "תקלות" in text
    assert "אנגייג׳מנט לא זמין" in text
    assert "בוקר טוב" in text and data["snapshot"].get("engagement") is None


def test_alerts_due_soon(monkeypatch, tmp_path):
    al = [{"id": "a", "platform": "Instagram", "text": "soon", "until": "2026-10-18"},
          {"id": "b", "platform": "Instagram", "text": "far", "until": "2026-12-01"},
          {"id": "c", "platform": "X", "text": "done", "until": "2026-10-17", "done": True}]
    _setup(monkeypatch, tmp_path, alerts=al)
    text, _ = mb.build_brief(NOW, state={})
    assert "soon" in text and "far" not in text and "done" not in text


def test_snapshot_only_after_successful_send(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    import telegram_sender
    monkeypatch.setattr(telegram_sender, "send_text", lambda t, parse_mode="Markdown": False)
    assert mb.main(["--send"]) == 1
    assert not mb.STATE.exists()
    seen = {}
    monkeypatch.setattr(telegram_sender, "send_text",
                        lambda t, parse_mode="Markdown": seen.update(pm=parse_mode) or True)
    assert mb.main(["--send"]) == 0
    assert seen["pm"] is None and mb.STATE.exists()
