import json

import pytest

from control import hub as hub_mod
from control import niche as niche_mod


@pytest.fixture(autouse=True)
def isolated_root(tmp_path, monkeypatch):
    monkeypatch.setattr(hub_mod, "ROOT", tmp_path)
    monkeypatch.setattr(hub_mod, "ENV_PATH", tmp_path / "scripts" / ".env")
    monkeypatch.setattr(niche_mod, "ROOT", tmp_path)
    (tmp_path / "niches").mkdir()
    (tmp_path / "scripts").mkdir()
    return tmp_path


def _write_env(root, text):
    (root / "scripts" / ".env").write_text(text, encoding="utf-8")


# ---- mask() ----

def test_mask_short_value():
    assert hub_mod.mask("abc") == "•••"
    assert hub_mod.mask("1234567") == "•••"  # 7 chars, still short


def test_mask_long_value():
    assert hub_mod.mask("sk-ABCDEFGHIJKL123") == "sk-A…123"


def test_mask_exactly_8_chars():
    # 8 chars is not < 8, so it should mask normally
    v = "ABCDEFGH"
    assert hub_mod.mask(v) == "ABCD…FGH"


def test_mask_none():
    assert hub_mod.mask(None) == ""


# ---- keys() ----

def test_keys_no_env_file(isolated_root):
    assert hub_mod.keys() == []


def test_keys_never_contains_raw_values(isolated_root):
    _write_env(isolated_root, "SECRET_TOKEN=verylongsecretvalue1234\nSHORT=ab\n")
    ks = hub_mod.keys()
    names = {k["name"] for k in ks}
    assert names == {"SECRET_TOKEN", "SHORT"}
    for k in ks:
        assert "verylongsecretvalue1234" not in json.dumps(k)
        assert k["set"] is True
        assert "masked" in k and "updated" in k
    secret = next(k for k in ks if k["name"] == "SECRET_TOKEN")
    assert secret["masked"] == "very…234"


def test_keys_skips_comments_and_blank_lines(isolated_root):
    _write_env(isolated_root, "# comment\n\nFOO=bar1234567\n")
    ks = hub_mod.keys()
    assert len(ks) == 1
    assert ks[0]["name"] == "FOO"


def test_keys_empty_value_not_set(isolated_root):
    _write_env(isolated_root, "EMPTY=\n")
    ks = hub_mod.keys()
    assert ks[0]["set"] is False
    assert ks[0]["masked"] == ""


# ---- reveal() ----

def test_reveal_returns_value(isolated_root):
    _write_env(isolated_root, "FOO=barbazqux\n")
    assert hub_mod.reveal("FOO") == "barbazqux"


def test_reveal_missing_returns_none(isolated_root):
    _write_env(isolated_root, "FOO=barbazqux\n")
    assert hub_mod.reveal("NOPE") is None


def test_reveal_no_env_file_returns_none(isolated_root):
    assert hub_mod.reveal("FOO") is None


# ---- load_hub / save_hub / accounts / links ----

def test_load_hub_missing_returns_empty(isolated_root):
    assert hub_mod.load_hub("stiletto") == {"accounts": [], "links": []}


def test_save_and_load_hub_roundtrip(isolated_root):
    data = {"accounts": [{"service": "Gmail", "login": "a@b.com"}], "links": [{"label": "Site", "url": "https://x.com"}]}
    hub_mod.save_hub(data, "stiletto")
    assert hub_mod.load_hub("stiletto") == data


def test_accounts_and_links_helpers(isolated_root):
    data = {"accounts": [{"service": "Gmail"}], "links": [{"label": "Site"}]}
    hub_mod.save_hub(data, "stiletto")
    assert hub_mod.accounts("stiletto") == [{"service": "Gmail"}]
    assert hub_mod.links("stiletto") == [{"label": "Site"}]


def test_load_hub_uses_active_niche_when_nid_omitted(isolated_root):
    (isolated_root / "niches" / "active.txt").write_text("stiletto", encoding="utf-8")
    data = {"accounts": [{"service": "Gmail"}], "links": []}
    hub_mod.save_hub(data)
    assert hub_mod.load_hub() == data


def test_save_hub_no_active_niche_raises(isolated_root):
    with pytest.raises(ValueError):
        hub_mod.save_hub({"accounts": [], "links": []})
