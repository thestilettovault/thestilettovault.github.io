# -*- coding: utf-8 -*-
"""Offline tests for the distribution scripts (nothing here touches the network)."""
import sys, os, json, threading, time, datetime
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
for p in (str(SCRIPTS), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import catalog_io
import social_publisher as sp
import tiktok_retry as tr


# -- auto_schedule.parse_schedule_result --------------------------------
def test_parse_schedule_result():
    import auto_schedule as au
    assert au.parse_schedule_result("x\nSCHEDULED_OK 6/6\n✅ pickup_drop complete") == (6, 6)
    assert au.parse_schedule_result("SCHEDULED_OK 3/6") == (3, 6)
    assert au.parse_schedule_result("SCHEDULED_OK 0/4\n") == (0, 4)
    # failure lines mention '-> instagram' but carry no machine line
    assert au.parse_schedule_result("  ! slug · image 1 → instagram @ when: 400") == (0, 0)
    assert au.parse_schedule_result("") == (0, 0)
    assert au.parse_schedule_result(None) == (0, 0)
    assert au.parse_schedule_result("SCHEDULED_OK 1/2\nSCHEDULED_OK 2/2") == (2, 2)


# -- caption cleaner ----------------------------------------------------
@pytest.mark.parametrize("raw", [
    "love these https://shop.example.com/x?y=1 so much #ad",
    "get them at stilettos.co.uk today #ad",
    "see www.thestilettovault.com #ad",
    "darkinlove.com/products/abc #ad",
    "HTTP://X.COM #ad",
])
def test_clean_caption_removes_urls_keeps_ad(raw):
    out = sp.clean_caption(raw)
    assert "http" not in out.lower()
    assert ".com" not in out.lower() and ".co.uk" not in out.lower() and "www." not in out.lower()
    assert "#ad" in out


def test_clean_caption_keeps_hashtags_and_link_in_bio():
    out = sp.clean_caption("Link in bio 🔗  #ad #affiliate\n\n#heels #stilettos")
    assert "Link in bio" in out and "#ad #affiliate" in out and "#heels" in out


def test_build_caption_no_url(monkeypatch):
    monkeypatch.setattr(sp, "ina_caption", lambda item: "mine at heels.co.uk http://x.io ok")
    cap = sp.build_caption({"title": "T", "deal": {"discount": "20%", "sale": 40}})
    assert "http" not in cap and ".co.uk" not in cap and "#ad" in cap


def test_tiktok_title_cap_keeps_disclosure():
    t = sp.tiktok_title("x" * 300)
    assert len(t) <= 90 and t.endswith("#ad")


# -- tiktok_retry -------------------------------------------------------
def test_local_slot_to_utc_dst():
    assert tr.iso_z(tr.slot_utc(datetime.date(2026, 10, 24), "16:00")) == "2026-10-24T13:00:00.000Z"
    assert tr.iso_z(tr.slot_utc(datetime.date(2026, 10, 26), "16:00")) == "2026-10-26T14:00:00.000Z"


def test_taken_slots_compare_in_local_time():
    # 13:00Z in summer and 14:00Z in winter are both the 16:00 local slot
    assert tr.local_key("2026-10-24T13:00:00.000Z") == ("2026-10-24", "16:00")
    assert tr.local_key("2026-10-26T14:00:00Z") == ("2026-10-26", "16:00")
    from collections import defaultdict
    load, taken = defaultdict(int), defaultdict(set)
    d, t = tr.local_key("2026-10-26T14:00:00.000Z")
    load[d] += 1
    taken[d].add(t)
    slots = tr.next_slots(load, taken, 1, datetime.date(2026, 10, 26))
    assert slots[0][0] == datetime.date(2026, 10, 27)          # the 26th is taken


NOW = datetime.datetime(2026, 10, 15, 12, 0, tzinfo=datetime.timezone.utc)


def _post(days_ago, **kw):
    when = NOW - datetime.timedelta(days=days_ago)
    p = {"scheduledFor": when.strftime("%Y-%m-%dT%H:%M:00.000Z"),
         "platforms": [{"platform": "tiktok"}], "content": "c"}
    p.update(kw)
    return p


def test_revive_filter():
    assert tr.revivable(_post(2, errorMessage="TikTok direct posting is at capacity"), NOW)[0]
    assert tr.revivable(_post(2, attempts=0), NOW)[0]
    assert tr.revivable(_post(2), NOW)[0]                                    # no info: age only
    ok, why = tr.revivable(_post(20, errorMessage="at capacity"), NOW)
    assert not ok and "14" in why
    ok, why = tr.revivable(_post(2, errorMessage="video codec rejected", attempts=2), NOW)
    assert not ok and "non-transient" in why
    p = _post(2)
    p["platforms"][0]["error"] = "rate limit exceeded"
    assert tr.revivable(p, NOW)[0]


def test_load_posts_requires_posts_key(monkeypatch):
    class R:
        def __init__(self, j): self.j = j
        def raise_for_status(self): pass
        def json(self): return self.j
    monkeypatch.setattr(tr.requests, "get", lambda *a, **k: R({"error": "nope"}))
    with pytest.raises(RuntimeError):
        tr.load_posts()
    seen = {}

    def fake(*a, **k):
        seen.update(k)
        return R({"posts": [{"_id": 1}], "pagination": {"pages": 1}})
    monkeypatch.setattr(tr.requests, "get", fake)
    assert tr.load_posts() == [{"_id": 1}] and seen["timeout"] == 30


# -- catalog_io ---------------------------------------------------------
def test_catalog_roundtrip_and_format(tmp_path):
    f = tmp_path / "cat.json"
    items = [{"title": "Stiletto ✓", "n": 1}]
    catalog_io.save_catalog(items, f)
    assert catalog_io.load_catalog(f) == items
    assert f.read_text(encoding="utf-8") == json.dumps(items, ensure_ascii=False, indent=2)
    assert not Path(str(f) + ".tmp").exists() and not Path(str(f) + ".lock").exists()
    assert catalog_io.load_catalog(tmp_path / "missing.json") == []


def test_catalog_lock_blocks_then_stale_removed(tmp_path, monkeypatch):
    f = tmp_path / "cat.json"
    lock = Path(str(f) + ".lock")
    lock.write_text("123")
    monkeypatch.setattr(catalog_io, "LOCK_WAIT", 0.3)
    with pytest.raises(TimeoutError):                 # fresh lock held by someone else
        catalog_io.save_catalog([1], f)
    assert lock.exists()                              # not ours: left alone
    old = time.time() - 120
    os.utime(lock, (old, old))                        # now stale -> removed, save succeeds
    catalog_io.save_catalog([2], f)
    assert catalog_io.load_catalog(f) == [2] and not lock.exists()


def test_catalog_lock_released_by_other_thread(tmp_path):
    f = tmp_path / "cat.json"
    lock = Path(str(f) + ".lock")
    lock.write_text("1")
    threading.Timer(0.4, lambda: lock.unlink()).start()
    catalog_io.save_catalog(["ok"], f)
    assert catalog_io.load_catalog(f) == ["ok"]


# -- schedule_drop ------------------------------------------------------
def _item(**kw):
    it = {"url": "https://x.example/products/abc-heel", "title": "Heel",
          "assets": {"images_ig": ["https://h/i1.png"], "images_tt": ["https://h/t1.png"]}}
    it.update(kw)
    return it


def _arm(monkeypatch):
    monkeypatch.setattr(sp, "ZERNIO_API_KEY", "k")
    monkeypatch.setattr(sp, "ZERNIO_INSTAGRAM_ID", "ig")
    monkeypatch.setattr(sp, "ZERNIO_TIKTOK_ID", "tt")
    monkeypatch.setattr(sp, "ina_caption", lambda i: "")


def test_schedule_drop_refuses_posted_without_force(monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError("network function must not be called")
    monkeypatch.setattr(sp, "_zernio_post", boom)
    _arm(monkeypatch)
    res = sp.schedule_drop(_item(posted=True), ["14:00"], True)
    assert res["refused"] and res["ok"] == 0 and res["total"] == 0
    assert "SCHEDULED_OK 0/0" in capsys.readouterr().out


def test_schedule_drop_force_and_partial(monkeypatch, tmp_path, capsys):
    cat = tmp_path / "c.json"
    item = _item(posted=True)
    catalog_io.save_catalog([item], cat)
    monkeypatch.setattr(sp, "CATALOG_FILE", cat)
    _arm(monkeypatch)

    def fake(content, platform, *a, **k):
        if platform == "instagram":
            info = sp._PostInfo("201: ok")
            info.post_id = "PID1"
            return True, info
        return False, "500: boom"
    monkeypatch.setattr(sp, "_zernio_post", fake)
    res = sp.schedule_drop(item, ["14:00"], True, force=True)
    assert (res["ok"], res["total"]) == (1, 2) and res["failed"] == ["image 1 → tiktok"]
    assert "SCHEDULED_OK 1/2" in capsys.readouterr().out
    saved = catalog_io.load_catalog(cat)[0]
    assert saved["posted"] is True and saved["post_ids"] == ["PID1"]
