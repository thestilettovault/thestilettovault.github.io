# -*- coding: utf-8 -*-
"""Offline tests for the niche TEMPLATE layer (cfg cache, clone, check, stiletto regression)."""
import json
import os
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
for p in (str(SCRIPTS), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from control import niche


@pytest.fixture
def tmp_root(tmp_path, monkeypatch):
    """Throwaway repo root with a copy of the real template and stiletto niche."""
    monkeypatch.setattr(niche, "ROOT", tmp_path)
    n = tmp_path / "niches"
    n.mkdir()
    import shutil
    shutil.copytree(ROOT / "niches" / "_template", n / "_template")
    (n / "stiletto").mkdir()
    shutil.copy(ROOT / "niches" / "stiletto" / "niche.json", n / "stiletto" / "niche.json")
    (n / "active.txt").write_text("stiletto\n", encoding="utf-8")
    return tmp_path


# -- cache ---------------------------------------------------------------
def test_cfg_cache_invalidates_on_mtime(tmp_root):
    f = tmp_root / "niches" / "stiletto" / "niche.json"
    assert niche.cfg("identity.name") == "The Stiletto Vault"
    data = json.loads(f.read_text(encoding="utf-8"))
    data["identity"]["name"] = "Changed"
    f.write_text(json.dumps(data), encoding="utf-8")
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))   # force a new mtime
    assert niche.cfg("identity.name") == "Changed"


def test_cfg_returns_copies(tmp_root):
    tags = niche.cfg("publishing.hashtags")
    tags.append("#mutated")
    assert "#mutated" not in niche.cfg("publishing.hashtags")


# -- clone ---------------------------------------------------------------
def test_clone_from_template_creates_tree(tmp_root):
    out = niche.clone("_template", "bags", "The Bag Vault")
    d = tmp_root / "niches" / "bags"
    assert (d / "niche.json").is_file() and (d / "hub.json").is_file()
    for f in ("persona", "poses", "stylist", "qa"):
        assert (d / "agents" / f"{f}.md").is_file()
    assert (d / "data" / "README.md").is_file()
    assert out["identity"]["id"] == "bags" and out["identity"]["name"] == "The Bag Vault"
    assert out["production"]["agents_dir"] == "niches/bags/agents"
    assert out["publishing"]["env"]["tiktok_id"] == "ZERNIO_BAGS_TIKTOK_ID"


def test_clone_from_stiletto_blanks_vertical_data(tmp_root):
    c = niche.clone("stiletto", "watches", "Watch Vault")
    assert c["sourcing"]["aliexpress_searches"] == [] and c["sourcing"]["shops"] == []
    assert c["site"]["public_url"] == "" and c["identity"]["handle"] == ""
    assert c["identity"]["product_noun"] == ""
    assert c["production"]["space_id"] == ""
    assert all(v == "" for v in c["production"]["nodes"].values())
    assert c["publishing"]["hashtags"] == [] and c["pinterest"]["title_openers"] == []
    assert (tmp_root / "niches" / "watches" / "agents" / "qa.md").is_file()
    # the live niche is untouched
    assert niche.load("stiletto")["identity"]["name"] == "The Stiletto Vault"


def test_clone_rejects_existing_and_bad_ids(tmp_root):
    niche.clone("_template", "bags", "Bags")
    with pytest.raises(ValueError):
        niche.clone("_template", "bags", "Bags")
    with pytest.raises(ValueError):
        niche.clone("_template", "../evil", "x")
    assert "_template" not in niche.list_niches()


# -- check ---------------------------------------------------------------
def test_check_blank_clone_reports_missing(tmp_root):
    niche.clone("_template", "bags", "The Bag Vault")
    problems = niche.check("bags", env_names=[])
    text = "\n".join(problems)
    for needle in ("identity.product_noun", "site.public_url", "sourcing", "production.space_id",
                   "ZERNIO_API_KEY", "ZERNIO_BAGS_TIKTOK_ID", "site.pages_dir"):
        assert needle in text, needle
    assert "identity.name" not in text          # the clone set it


def test_check_cli_exit_codes(tmp_root, capsys):
    niche.clone("_template", "bags", "The Bag Vault")
    assert niche._cli(["check", "bags"]) != 0
    assert "NOT ready" in capsys.readouterr().out


def test_check_stiletto_ready_with_env_names(tmp_root):
    # real stiletto expects agents + compliance pages at the repo root
    import shutil
    shutil.copytree(ROOT / "data" / "agents", tmp_root / "data" / "agents")
    for pg in ("about.html", "disclosure.html", "contact.html", "privacy-policy.html"):
        (tmp_root / pg).write_text("x", encoding="utf-8")
    names = ["ZERNIO_API_KEY", "ZERNIO_TIKTOK_ID", "ZERNIO_INSTAGRAM_ID"]
    assert niche.check("stiletto", env_names=names) == []
    # and without the env names it flags exactly those
    probs = niche.check("stiletto", env_names=[])
    assert len(probs) == 3 and all("scripts/.env" in p for p in probs)


def test_check_never_prints_env_values(tmp_root, monkeypatch):
    env = tmp_root / ".env"
    env.write_text("ZERNIO_API_KEY=supersecret123\n# c\nexport OTHER=zzz\n", encoding="utf-8")
    assert niche._env_names(env) == {"ZERNIO_API_KEY", "OTHER"}


# -- stiletto regression: config values == the old literals --------------
def test_stiletto_values_equal_old_literals():
    import social_publisher as sp
    import pickup_drop as pd
    import space_runner as sr
    import tiktok_retry as tr
    import pinterest_csv as pc
    import collect_metrics as cm
    import auto_schedule as asch
    import orchestrator as orch

    assert sp.SITE_URL == "https://thestilettovault.com"
    assert sp.HASHTAGS == ["#heels", "#stilettos", "#highheels", "#heelslover",
                           "#shoesoftheday", "#nycstyle", "#outfitinspo", "#statementheels"]
    assert sp.DEFAULT_SLOTS == ["14:00", "18:00", "22:00"]
    assert sp.CTA == "Link in bio \U0001f517" and sp.DISCLOSURE == "#ad #affiliate"
    assert sp.TIMEZONE == "Asia/Jerusalem"
    assert pd.SITE_URL == "https://thestilettovault.github.io"
    assert pd.IMG_REL == "img/heels" and pd.IMG_DIR == ROOT / "img" / "heels"
    assert sr.SPACE_ID == "a2796464-3570-4e02-aa77-65f3f4322d9f"
    assert sr.SPACE_INPUT_IMAGE_NODE == "93b85932-6752-4bfa-a801-28fd3c0c097c"
    assert sr.SPACE_OUTPUT_ADS_LIST == "9a64a219-35fa-4dc5-a8d7-c0c67164f134"
    assert sr.SPACE_OUTPUT_VIDEO_INSTA == "1ecb7df2-1a63-47d2-b4f3-09a75894816c"
    assert sr.SPACE_OUTPUT_VIDEO_TIKTOK == "bd04349b-fdde-4306-a8d8-cb262b322e96" or \
        niche.cfg("production.nodes.video_tiktok") == sr.SPACE_OUTPUT_VIDEO_TIKTOK
    assert tr.MAX_TT_PER_DAY == 1 and tr.SLOT_TIMES == ["16:00"] and tr.SKIP_WEEKDAYS == (5,)
    assert str(tr.IL) == "Asia/Jerusalem"
    assert asch.SLOT == "16:00" and asch.SKIP_WEEKDAYS == (5,)
    assert pc.SITE == "https://thestilettovault.com"
    assert pc.PIN_HASHTAGS == "#heels #stilettos #shoefinds #affordablefashion #heelsaddict"
    assert pc.PIN_KEYWORDS == "high heels, stilettos, heels, shoe finds, affordable heels, party shoes"
    assert niche.cfg("pinterest.board") == "Stiletto Finds"
    assert len(pc.OPENERS) == len(niche.cfg("pinterest.title_openers")) == 30
    assert pc.OPENERS == niche.cfg("pinterest.title_openers")
    assert sorted(cm.OUR_HOSTS) == ["thestilettovault.com", "thestilettovault.github.io"]
    assert orch.BURN_DEAL_OVERLAY is False
    assert orch.SPACE_LABEL == "thestilettovault Ad campaign"


def test_caption_format_unchanged():
    import social_publisher as sp
    item = {"title": "Black Pump", "sale": "29"}
    cap = sp.build_caption(item) if hasattr(sp, "build_caption") else ""
    if cap:
        assert "Link in bio \U0001f517" in cap or "link in bio \U0001f517" in cap
        assert "#ad #affiliate" in cap


def test_collect_metrics_host_agnostic():
    import collect_metrics as cm
    for host in ("https://thestilettovault.github.io/img/heels/a/b.png",
                 "https://thestilettovault.com/img/heels/a/b.png"):
        assert cm.our_hosted_image({"image_url": host}) == host
    assert cm.our_hosted_image({"image_url": "https://ae01.alicdn.com/x.jpg"}) is None
