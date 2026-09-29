import json

import pytest

from control import niche


@pytest.fixture(autouse=True)
def isolated_root(tmp_path, monkeypatch):
    """Point control.niche at a throwaway niches/ tree for every test."""
    monkeypatch.setattr(niche, "ROOT", tmp_path)
    (tmp_path / "niches").mkdir()
    return tmp_path


def _write_niche(root, nid, data):
    d = root / "niches" / nid
    d.mkdir(parents=True, exist_ok=True)
    (d / "niche.json").write_text(json.dumps(data), encoding="utf-8")
    return d


def test_active_id_missing_file_returns_empty(isolated_root):
    assert niche.active_id() == ""


def test_active_id_reads_file(isolated_root):
    (isolated_root / "niches" / "active.txt").write_text("stiletto\n", encoding="utf-8")
    assert niche.active_id() == "stiletto"


def test_cfg_default_on_missing_niche(isolated_root):
    assert niche.cfg("thresholds.MIN_SOLD", 300) == 300


def test_cfg_default_on_bad_json(isolated_root):
    (isolated_root / "niches" / "active.txt").write_text("bad", encoding="utf-8")
    d = isolated_root / "niches" / "bad"
    d.mkdir()
    (d / "niche.json").write_text("{not valid json", encoding="utf-8")
    assert niche.cfg("thresholds.MIN_SOLD", 300) == 300


def test_cfg_default_on_missing_key(isolated_root):
    (isolated_root / "niches" / "active.txt").write_text("s1", encoding="utf-8")
    _write_niche(isolated_root, "s1", {"thresholds": {"MIN_SOLD": 999}})
    assert niche.cfg("thresholds.MISSING_KEY", "fallback") == "fallback"
    assert niche.cfg("nope.nope", None) is None


def test_cfg_reads_nested_value(isolated_root):
    (isolated_root / "niches" / "active.txt").write_text("s1", encoding="utf-8")
    _write_niche(isolated_root, "s1", {"thresholds": {"MIN_SOLD": 999}})
    assert niche.cfg("thresholds.MIN_SOLD", 0) == 999


def test_cfg_never_raises_on_non_dict_traversal(isolated_root):
    (isolated_root / "niches" / "active.txt").write_text("s1", encoding="utf-8")
    _write_niche(isolated_root, "s1", {"thresholds": 5})
    assert niche.cfg("thresholds.MIN_SOLD", "d") == "d"


def test_save_and_load_roundtrip(isolated_root):
    (isolated_root / "niches" / "active.txt").write_text("s1", encoding="utf-8")
    (isolated_root / "niches" / "s1").mkdir()
    niche.save({"a": 1}, "s1")
    assert niche.load("s1") == {"a": 1}
    # atomic write leaves no .tmp file behind
    assert not (isolated_root / "niches" / "s1" / "niche.json.tmp").exists()


def test_update_deep_merges(isolated_root):
    (isolated_root / "niches" / "active.txt").write_text("s1", encoding="utf-8")
    _write_niche(isolated_root, "s1", {"thresholds": {"MIN_SOLD": 300, "MIN_PRICE": 20}})
    merged = niche.update({"thresholds": {"MIN_SOLD": 500}})
    assert merged["thresholds"]["MIN_SOLD"] == 500
    assert merged["thresholds"]["MIN_PRICE"] == 20
    # persisted
    assert niche.load("s1")["thresholds"]["MIN_SOLD"] == 500


def test_update_no_active_niche_raises(isolated_root):
    with pytest.raises(ValueError):
        niche.update({"a": 1})


def test_list_niches(isolated_root):
    _write_niche(isolated_root, "a", {"identity": {"id": "a"}})
    _write_niche(isolated_root, "b", {"identity": {"id": "b"}})
    (isolated_root / "niches" / "empty_dir").mkdir()
    assert niche.list_niches() == ["a", "b"]


def test_set_active_unknown_raises(isolated_root):
    with pytest.raises(ValueError):
        niche.set_active("ghost")


def test_set_active_writes_file(isolated_root):
    _write_niche(isolated_root, "a", {"identity": {"id": "a"}})
    niche.set_active("a")
    assert niche.active_id() == "a"


def test_clone_blanks_search_fields_and_hub_logins(isolated_root):
    _write_niche(
        isolated_root,
        "stiletto",
        {
            "identity": {"id": "stiletto", "name": "The Stiletto Vault"},
            "sourcing": {"aliexpress_searches": [["a", "b"]], "shops": ["x.com"]},
            "thresholds": {"MIN_SOLD": 300},
            "research": {"trend_queries": ["q1"]},
        },
    )
    hub_data = {
        "accounts": [{"service": "Gmail", "login": "someone@example.com"}],
        "links": [{"label": "Site", "url": "https://example.com"}],
    }
    (isolated_root / "niches" / "stiletto" / "hub.json").write_text(
        json.dumps(hub_data), encoding="utf-8"
    )

    new_cfg = niche.clone("stiletto", "bags", "The Bag Vault")

    assert new_cfg["identity"]["id"] == "bags"
    assert new_cfg["identity"]["name"] == "The Bag Vault"
    assert new_cfg["sourcing"]["aliexpress_searches"] == []
    assert new_cfg["sourcing"]["shops"] == []
    assert new_cfg["research"]["trend_queries"] == []
    # thresholds carried over untouched
    assert new_cfg["thresholds"]["MIN_SOLD"] == 300

    new_hub = json.loads((isolated_root / "niches" / "bags" / "hub.json").read_text(encoding="utf-8"))
    assert new_hub["accounts"][0]["service"] == "Gmail"
    assert new_hub["accounts"][0]["login"] == ""
    assert new_hub["links"] == []


def test_clone_refuses_existing_dst(isolated_root):
    _write_niche(isolated_root, "stiletto", {"identity": {"id": "stiletto"}})
    _write_niche(isolated_root, "bags", {"identity": {"id": "bags"}})
    with pytest.raises(ValueError):
        niche.clone("stiletto", "bags", "The Bag Vault")


def test_clone_missing_src_raises(isolated_root):
    with pytest.raises(ValueError):
        niche.clone("ghost", "bags", "The Bag Vault")
