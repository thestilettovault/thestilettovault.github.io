# -*- coding: utf-8 -*-
"""Tests for the sourcing pipeline: jsonio, heel filter, AliExpress scout helpers,
Telegram sender, earning gate, heel_hunter registry safety. No network."""
import json
import os
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
for p in (str(SCRIPTS), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import jsonio  # noqa: E402
import heel_filter  # noqa: E402


# ── jsonio ───────────────────────────────────────────────────────────
def test_load_missing_returns_default(tmp_path):
    assert jsonio.load(tmp_path / "nope.json", {"a": 1}) == {"a": 1}


def test_load_corrupt_raises_and_backs_up(tmp_path):
    f = tmp_path / "reg.json"
    f.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        jsonio.load(f, {})
    backups = [x for x in tmp_path.iterdir() if ".corrupt-" in x.name]
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{not json"
    assert f.read_text(encoding="utf-8") == "{not json"      # original untouched


def test_load_reads_bom(tmp_path):
    f = tmp_path / "bom.json"
    f.write_bytes(b"\xef\xbb\xbf" + json.dumps({"x": 1}).encode())
    assert jsonio.load(f, None) == {"x": 1}


def test_save_roundtrip_atomic_no_leftovers(tmp_path):
    f = tmp_path / "d.json"
    jsonio.save(f, {"שלום": [1, 2]}, ensure_ascii=False, indent=2)
    assert jsonio.load(f, None) == {"שלום": [1, 2]}
    assert "שלום" in f.read_text(encoding="utf-8")           # ensure_ascii=False honoured
    assert sorted(x.name for x in tmp_path.iterdir()) == ["d.json"]   # no tmp / lock left


def test_locked_is_reentrant_and_save_inside_lock(tmp_path):
    f = tmp_path / "d.json"
    with jsonio.locked(f):
        d = jsonio.load(f, {})
        d["k"] = 1
        jsonio.save(f, d)
        with jsonio.locked(f):
            jsonio.save(f, {**d, "k2": 2})
    assert jsonio.load(f, None) == {"k": 1, "k2": 2}
    assert not (tmp_path / "d.json.lock").exists()


def test_stale_lock_is_removed(tmp_path):
    f = tmp_path / "d.json"
    lock = tmp_path / "d.json.lock"
    lock.write_text("123")
    old = time.time() - 3600
    os.utime(lock, (old, old))
    jsonio.save(f, {"ok": True})
    assert jsonio.load(f, None) == {"ok": True}


def test_fresh_foreign_lock_times_out(tmp_path, monkeypatch):
    f = tmp_path / "d.json"
    (tmp_path / "d.json.lock").write_text("999")
    monkeypatch.setattr(jsonio, "LOCK_TIMEOUT", 0.3)
    with pytest.raises(TimeoutError):
        jsonio.save(f, {})


# ── heel filter ──────────────────────────────────────────────────────
@pytest.mark.parametrize("title", [
    "Platform Sneaker", "Wedge Sneakers", "Flat Mule", "Studio Pump Trainers",
    "Running Shoes", "Canvas Oxford", "Ballet Flats",
])
def test_filter_rejects_non_heels(title):
    assert not heel_filter.is_high_heel(title)


@pytest.mark.parametrize("title", [
    "Black Stiletto Pump", "Pointed Toe Pumps", "Block Heel Sandal",
    "Platform Heels", "Knee High Boots", "Strappy Sandal", "Peacock Stiletto",
    "Cocktail Heel", "Slingback Kitten",
])
def test_filter_accepts_heels(title):
    assert heel_filter.is_high_heel(title)
    assert heel_filter.passes(title)


def test_is_excluded_whole_word():
    assert not heel_filter.is_excluded("Peacock Stiletto")
    assert not heel_filter.is_excluded("Cocktail Heel")
    assert not heel_filter.is_excluded("Analog Heel")
    assert heel_filter.is_excluded("Vibrating Toy")
    assert heel_filter.is_excluded("Adult sex toy")
    assert heel_filter.is_excluded("cock ring")


def test_tags_only_add_positive_signal():
    assert heel_filter.is_high_heel("Mystery Shoe", tags=["Category_Heels"])
    assert heel_filter.is_high_heel("Mystery Shoe", tags="heels, new")      # str tags
    assert not heel_filter.is_high_heel("Canvas Sneaker", tags=["heels"])


def test_product_scout_reexports_filter():
    import product_scout
    assert product_scout.is_high_heel is heel_filter.is_high_heel
    assert product_scout.is_excluded is heel_filter.is_excluded


def test_scout_shopify_uses_first_available_variant(monkeypatch):
    import product_scout

    class R:
        ok = True

        def json(self):
            return {"products": [
                {"title": "Sold Out Stiletto", "handle": "so", "images": [{"src": "i"}],
                 "variants": [{"price": "10", "available": False}]},
                {"title": "Good Stiletto", "handle": "g", "images": [{"src": "i"}],
                 "variants": [{"price": "99", "available": False},
                              {"price": "120", "available": True}]},
            ]}

    monkeypatch.setattr(product_scout.requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(product_scout.time, "sleep", lambda *_: None)
    out = product_scout.scout_shopify({"domain": "x.com", "collections": ["heels"],
                                       "affiliate": {}, "max_per_collection": 5})
    assert [p["title"] for p in out] == ["Good Stiletto"]
    assert out[0]["price"] == "120"


# ── aliexpress_scout ─────────────────────────────────────────────────
def test_sold_n():
    import aliexpress_scout as a
    assert a._sold_n("Sold out.") == 0
    assert a._sold_n("") == 0
    assert a._sold_n(None) == 0
    assert a._sold_n("286 sold") == 286
    assert a._sold_n("1,234 sold") == 1234
    assert a._sold_n("1.2k+ sold") == 1200
    assert a._sold_n("5K sold") == 5000


def test_title_ok_rejects_sneaker_but_not_unreadable():
    import aliexpress_scout as a
    assert not a._title_ok("Women Platform Sneakers Casual")
    assert a._title_ok("Women Sexy Pointed Toe Stiletto Pumps")
    assert a._title_ok("נעלי עקב")           # nothing readable to judge → not filtered


def _fake_html_items(items):
    return "x"


def test_scout_survives_bad_item_and_does_not_write_empty(tmp_path, monkeypatch):
    import aliexpress_scout as a
    pool = tmp_path / "pool.json"
    pool.write_text(json.dumps({"products": [{"keep": "me"}]}), encoding="utf-8")
    monkeypatch.setattr(a, "POOL", pool)
    monkeypatch.setattr(a, "SEARCHES", [("stiletto heels", "Stiletto Heels")])
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setattr(a, "_fetch", lambda term: "html")
    good = {"productId": "111", "title": {"displayTitle": "Black Stiletto Heels Pumps"},
            "prices": {"salePrice": {"minPrice": "29.9"}},
            "evaluation": {"starRating": "4.8"}, "trade": {"tradeDesc": "900 sold"},
            "image": {"imgUrl": "//img/x.jpg"}}
    bad = {"productId": "222", "title": None, "prices": "boom"}         # AttributeError
    sneaker = dict(good, productId="333",
                   title={"displayTitle": "Platform Sneakers for Women"})
    soldout = dict(good, productId="444", trade={"tradeDesc": "Sold out."})
    monkeypatch.setattr(a, "_items", lambda html: [bad, sneaker, soldout, good])
    found = a.scout(write=True)
    assert [f["url"].split("/")[-1] for f in found] == ["111.html"]
    assert found[0]["raw_title"] == "Black Stiletto Heels Pumps"
    assert found[0]["title"] == "Stiletto Heels"                        # display label kept
    assert json.loads(pool.read_text(encoding="utf-8"))["products"][0]["url"].endswith("111.html")

    # empty result must NOT clobber the pool
    before = pool.read_text(encoding="utf-8")
    monkeypatch.setattr(a, "_items", lambda html: [])
    assert a.scout(write=True) == []
    assert pool.read_text(encoding="utf-8") == before


# ── telegram_sender ──────────────────────────────────────────────────
def test_escape_md():
    import telegram_sender as ts
    assert ts._escape_md("a_b*c`d[e") == "a\\_b\\*c\\`d\\[e"
    assert ts._escape_md(None) == ""


class _Resp:
    def __init__(self, status=200, text="{}", js=None):
        self.status_code, self.text, self._js = status, text, js
        self.ok = status < 400

    def json(self):
        if self._js is None:
            raise ValueError
        return self._js


def test_post_retries_without_parse_mode_on_400(monkeypatch):
    import telegram_sender as ts
    calls = []

    def fake_post(url, data=None, json=None, files=None, timeout=None):
        calls.append(dict(json or {}))
        return _Resp(400, "can't parse entities") if len(calls) == 1 else _Resp(200)

    monkeypatch.setattr(ts.requests, "post", fake_post)
    assert ts.send_text("hello_world *", parse_mode="Markdown") is True
    assert len(calls) == 2
    assert "parse_mode" in calls[0] and "parse_mode" not in calls[1]


def test_send_text_false_on_network_error_and_api_not_ok(monkeypatch):
    import telegram_sender as ts

    def boom(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr(ts.requests, "post", boom)
    assert ts.send_text("x") is False
    monkeypatch.setattr(ts.requests, "post",
                        lambda *a, **k: _Resp(200, "{}", {"ok": False}))
    assert ts.send_text("x") is False


def test_send_product_returns_false_never_raises(monkeypatch):
    import telegram_sender as ts
    monkeypatch.setattr(ts.taste_engine, "save_pending", lambda *a, **k: 1 / 0)
    assert ts.send_product("https://x.com/p", "t") is False


# ── affiliate_links.is_earning ───────────────────────────────────────
@pytest.fixture
def registry(tmp_path, monkeypatch):
    import affiliate_links as al
    reg = tmp_path / "reg.json"
    reg.write_text(json.dumps({"brands": {
        "darkinlove.com": {"status": "active", "our_id": "ll1"},
        "gthic.com": {"status": "active", "our_id": ""},
        "simmi.com": {"status": "to_register", "our_id": None},
    }}), encoding="utf-8")
    monkeypatch.setattr(al, "REGISTRY_PATH", str(reg))
    return al


def test_is_earning_cases(registry):
    al = registry
    assert al.is_earning(al.aliexpress("https://www.aliexpress.com/item/1.html"))
    assert not al.is_earning("https://www.aliexpress.com/item/1.html")        # raw URL
    assert al.is_earning(f"https://www.amazon.com/dp/B000000000?tag={al.AMAZON_TAG}")
    assert not al.is_earning("https://www.amazon.com/dp/B000000000?tag=other-20")
    assert not al.is_earning("https://www.amazon.com/dp/B000000000")
    assert al.is_earning("https://www.darkinlove.com/products/x")             # active + our_id
    assert not al.is_earning("https://gthic.com/products/x")                  # active, no our_id
    assert not al.is_earning("https://www.simmi.com/products/x")              # to_register
    assert not al.is_earning("https://unknown-shop.com/p")
    assert not al.is_earning("")


def test_affiliate_link_logs_when_not_earning(registry, caplog):
    al = registry
    with caplog.at_level("WARNING", logger="affiliate_links"):
        link = al.affiliate_link({"url": "https://unknown-shop.com/p", "domain": "unknown-shop.com"})
    assert link == "https://unknown-shop.com/p"                               # type/value unchanged
    assert "no earning link" in caplog.text


# ── taste_engine ─────────────────────────────────────────────────────
def test_get_domain_strips_only_leading_www():
    import taste_engine as te
    assert te.get_domain("https://www.example.com/x") == "example.com"
    assert te.get_domain("https://shop.www.example.com/x") == "shop.www.example.com"
    assert te.get_domain("https://eu.brand.com/x") == "eu.brand.com"


def test_inject_amazon_tag():
    import taste_engine as te
    ours = "thegothicvaul-20"
    assert te.inject_affiliate_link("https://www.amazon.com/dp/B1") == f"https://www.amazon.com/dp/B1?tag={ours}"
    assert te.inject_affiliate_link(f"https://www.amazon.com/dp/B1?tag={ours}&a=1") == \
        f"https://www.amazon.com/dp/B1?tag={ours}&a=1"
    assert te.inject_affiliate_link("https://www.amazon.com/dp/B1?tag=foreign-20&a=1") == \
        f"https://www.amazon.com/dp/B1?tag={ours}&a=1"
    # a param that merely CONTAINS "tag=" must not count as an existing tag
    assert te.inject_affiliate_link("https://www.amazon.com/dp/B1?vtag=zzz") == \
        f"https://www.amazon.com/dp/B1?vtag=zzz&tag={ours}"


def test_fetch_image_rejects_non_image_and_deletes_partial(tmp_path, monkeypatch):
    import taste_engine as te

    class R:
        content = b"<html>blocked</html>"

        def raise_for_status(self):
            pass

    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: R())
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: type("P", (), {"returncode": 1})())
    dest = tmp_path / "source.jpg"
    assert te._fetch_image("http://x/y.jpg", str(dest)) is False
    assert not dest.exists()


def test_fetch_image_accepts_real_image(tmp_path, monkeypatch):
    import io
    import taste_engine as te
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "JPEG")

    class R:
        content = buf.getvalue()

        def raise_for_status(self):
            pass

    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: R())
    dest = tmp_path / "source.jpg"
    assert te._fetch_image("http://x/y.jpg", str(dest)) is True
    assert dest.exists()


def test_corrupt_json_not_treated_as_empty_in_taste_engine(tmp_path):
    import taste_engine as te
    f = tmp_path / "pending.json"
    f.write_text("{{{", encoding="utf-8")
    with pytest.raises(ValueError):
        te.load_json(str(f), {})
    assert f.read_text(encoding="utf-8") == "{{{"


# ── heel_hunter ──────────────────────────────────────────────────────
@pytest.fixture
def hh(tmp_path, monkeypatch):
    import heel_hunter
    reg = tmp_path / "affiliate_registry.json"
    monkeypatch.setattr(heel_hunter, "REG", reg)
    monkeypatch.setattr(heel_hunter, "TRENDS", tmp_path / "trends.json")
    monkeypatch.setattr(heel_hunter, "INBOX", tmp_path / "inbox.jsonl")
    return heel_hunter


def test_corrupt_registry_is_not_wiped(hh):
    hh.REG.write_text("{ corrupt", encoding="utf-8")
    with pytest.raises(ValueError):
        hh.activate_one("brand.com", "https://brand.com/?ref=1")
    with pytest.raises(ValueError):
        hh.load_reg()
    assert hh.REG.read_text(encoding="utf-8") == "{ corrupt"
    assert any(".corrupt-" in x.name for x in hh.REG.parent.iterdir())


def test_activate_one_tracking_kinds(hh):
    q = hh.activate_one("a.com", "https://a.com/?ref=XYZ")
    assert q["tracking"] == "query" and q["affiliate_ref"] == "?ref=XYZ" and "warning" not in q
    n = hh.activate_one("b.com", "https://www.awin1.com/cread.php?awinmid=1&awinaffid=2&ued=x")
    assert n["tracking"] == "network" and n["affiliate_ref"] == "" and "awin1.com" in n["our_id"]
    p = hh.activate_one("c.com", "https://c.com/OFER123")
    assert p["tracking"] == "path" and p["affiliate_ref"] == "" and p["warning"]
    z = hh.activate_one("d.com", "https://d.com")
    assert z["tracking"] == "none" and z["warning"]
    assert hh.load_reg()["brands"]["a.com"]["status"] == "active"


def test_activate_does_not_replay_inbox(hh):
    line = json.dumps({"text": "aff e.com https://e.com/?ref=1"})
    hh.INBOX.write_text(line + "\n", encoding="utf-8")
    assert hh.activate() == ["e.com"]
    # owner later edits the entry by hand
    reg = hh.load_reg()
    reg["brands"]["e.com"]["our_id"] = "https://e.com/?ref=MANUAL"
    hh.save_reg(reg)
    assert hh.activate() == []                                   # same inbox line → not replayed
    assert hh.load_reg()["brands"]["e.com"]["our_id"] == "https://e.com/?ref=MANUAL"
    hh.INBOX.write_text(line + "\n" + json.dumps({"text": "aff f.com https://f.com/?ref=2"}) + "\n",
                        encoding="utf-8")
    assert hh.activate() == ["f.com"]                            # only the new line


def test_cards_marks_carded_only_when_send_succeeds(hh, monkeypatch):
    hh.save_reg({"brands": {
        "ok.com": {"domain": "ok.com", "status": "to_register", "value_per_sale": 50,
                   "program": "Direct", "avg_price": 100},
        "bad.com": {"domain": "bad.com", "status": "to_register", "value_per_sale": 40,
                    "program": "Direct", "avg_price": 100},
    }})
    monkeypatch.setattr(hh, "_send", lambda text: "ok.com" in text)
    assert hh.cards() == 1
    b = hh.load_reg()["brands"]
    assert b["ok.com"]["status"] == "carded"
    assert b["bad.com"]["status"] == "to_register"


def test_cards_does_not_overwrite_concurrent_registry_change(hh, monkeypatch):
    hh.save_reg({"brands": {
        "one.com": {"domain": "one.com", "status": "to_register", "value_per_sale": 50,
                    "program": "Direct", "avg_price": 100},
        "two.com": {"domain": "two.com", "status": "to_register", "value_per_sale": 40,
                    "program": "Direct", "avg_price": 100},
    }})

    def send(text):
        if "one.com" in text:                   # owner activates two.com mid-run
            hh.activate_one("two.com", "https://two.com/?ref=Z")
        return True

    monkeypatch.setattr(hh, "_send", send)
    hh.cards()
    b = hh.load_reg()["brands"]
    assert b["one.com"]["status"] == "carded"
    assert b["two.com"]["status"] == "active"                    # not reverted by a stale copy


# ── daily_heel_scout ─────────────────────────────────────────────────
def test_mark_sent_persists_each_send(tmp_path, monkeypatch):
    import daily_heel_scout as d
    monkeypatch.setattr(d, "SENT_LOG", tmp_path / "sent.json")
    d.mark_sent("k1")
    d.mark_sent("k2")
    assert set(d.load_sent()) == {"k1", "k2"}


def test_skip_weekdays_default_is_saturday():
    import daily_heel_scout as d
    assert 5 in list(d.SKIP_WEEKDAYS)
    assert len(d.HEEL_SHOPS) >= 1


# ── build_work_library ───────────────────────────────────────────────
def test_captions_have_no_gothic_words_or_urls(tmp_path):
    import re
    import build_work_library as b
    for title in ("Black Gladiator Stiletto", "Red Satin Pump", "Knee High Boot", "Plain Pump",
                  "Clear Platform", "Glitter Heel"):
        txt = b.captions_text(title, "https://aff.example/x", "6.9%", str(tmp_path))
        low = txt.lower()
        for bad in ("goth", "darkstyle", "dangerous", "blood on", "armour", "\U0001F5A4", "\U0001F480"):
            assert bad not in low and bad not in txt, (title, bad)
        captions = txt.split("## \U0001F4F8", 1)[1]               # everything after the link header
        assert "http" not in captions
        assert "#ad #affiliate" in captions
        assert "#stilettos" in captions and "#highheels" in captions
        assert re.search(r"Link in bio", captions)
