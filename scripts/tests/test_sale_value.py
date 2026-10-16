import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sale_value as sv  # noqa: E402


def test_value_from_price_and_commission():
    assert sv.value_per_sale("aliexpress.com", 18, "6.9%") == 1.24
    assert sv.value_per_sale("nakedwolfe.com", "300.00", "10%") == 30.0
    assert sv.value_per_sale("www.aliexpress.com", 20, "") == 1.38      # domain default pct
    assert sv.value_per_sale("amazon.com", None, "4%") == 1.8           # estimated price


def test_registry_fallback_when_no_price(tmp_path, monkeypatch):
    reg = tmp_path / "reg.json"
    reg.write_text(json.dumps({"brands": {"nakedwolfe.com": {"value_per_sale": 30.0}}}), encoding="utf-8")
    monkeypatch.setattr(sv, "REGISTRY", reg)
    e = {"url": "https://nakedwolfe.com/products/x?snowball=1", "deal": {}}
    assert sv.value_of_entry(e) == 30.0
    assert sv.value_of_entry({"url": "https://unknown.example/p", "deal": {}}) == 0.0


def test_scout_orders_brand_first():
    import daily_heel_scout as d
    fresh = [{"domain": "aliexpress.com", "price": 18, "commission": "6.9%", "title": f"a{i}"} for i in range(4)]
    fresh += [{"domain": "nakedwolfe.com", "price": 300, "commission": "10%", "title": "nw1"},
              {"domain": "nakedwolfe.com", "price": 450, "commission": "10%", "title": "nw2"}]
    out = d.order_by_value(fresh, brand_slots=2, min_value=5)
    assert out[0]["title"] == "nw2"                      # top value first
    assert {c["title"] for c in out[:3]} >= {"nw1", "nw2"}  # both brand shoes inside the 5-card batch
    assert len(out) == 6


def test_queue_next_prefers_value(tmp_path, monkeypatch):
    import orchestrator as o
    q = tmp_path / "q.json"
    q.write_text(json.dumps([
        {"status": "approved", "local_asset": "GELEM/2026-10-14/cheap", "url": "https://www.aliexpress.com/item/1.html",
         "deal": {"sale": 18}, "approved_ts": "2026-10-14"},
        {"status": "approved", "local_asset": "GELEM/2026-10-09/boot", "url": "https://nakedwolfe.com/products/b",
         "deal": {}, "commission": "10%", "price": 300, "approved_ts": "2026-10-09"},
        {"status": "done", "local_asset": "GELEM/2026-10-01/old", "url": "https://nakedwolfe.com/products/o",
         "price": 900, "commission": "10%"},
    ]), encoding="utf-8")
    monkeypatch.setattr(o, "QUEUE_FILE", q)
    slug, la, v = o.queue_next()
    assert slug == "2026-10-09/boot" and v == 30.0


def test_full_catalogue_filter_rejects_apparel_keeps_boots():
    import heel_filter as h
    assert not h.is_high_heel("Punk Strappy Zipper Design Multi-Pocket Baggy Jeans", ["heels"])
    assert not h.is_high_heel("Stiletto Heel Protector", ["heels"])
    assert not h.is_high_heel("Fishnet Tights", ["heels"])
    assert h.is_high_heel("The Bag Boot Black Leather", [])
    assert h.is_high_heel("Thigh High Stiletto Boots", [])
