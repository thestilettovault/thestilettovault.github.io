# -*- coding: utf-8 -*-
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent.parent))
import creative_learning as cl

NUM = """1. P02 — stair step: one foot on the step above. OUTFIT: x
2. P04 — seated cross-leg: sitting on a stool
3. P07 — lean on wall: back to wall
4. P10 — heel close-up in hand: hand holding"""
ONE = "SHOTS: P01 crosswalk (white linen mini) | P08 loft chair (black mini) | S03 taxi exit (shirt dress) | S06 choosing a pair (lounge set)"
BOLD = "1. **P02 stair step** — one foot up\n2. **P05 sit** — x\n3. **P01 walk** — y\n4. **P03 car** — z"
NEW = """1. PH03 · CAMERA: PHONE (Ina). POV look-down in a cab
2. ST01 · CAMERA: SET (photographer). seamless
3. BT02 · CAMERA: BTS (stylist). between takes
4. PH01 · mirror check. CAMERA: PHONE (self)"""


def test_parse_numbered():
    r = cl.parse_brief(NUM)
    assert [x["id"] for x in r] == ["P02", "P04", "P07", "P10"]
    assert r[0]["camera"] == "LEGACY" and r[0]["label"] == "stair step"


def test_parse_oneliner():
    r = cl.parse_brief(ONE)
    assert [x["id"] for x in r] == ["P01", "P08", "S03", "S06"]
    assert r[2]["camera"] == "PHONE" and r[0]["camera"] == "LEGACY"
    assert r[2]["label"] == "taxi exit"


def test_parse_bold():
    r = cl.parse_brief(BOLD)
    assert len(r) == 4 and r[0]["label"] == "stair step"


def test_parse_new():
    r = cl.parse_brief(NEW)
    assert [x["camera"] for x in r] == ["PHONE", "SET", "BTS", "PHONE"]
    assert r[3]["id"] == "PH01"


def test_camera_derivation():
    assert cl.derive_camera("C02") == "BTS" and cl.derive_camera("C04") == "PHONE"
    assert cl.derive_camera("C06") == "FRIEND" and cl.derive_camera("FR01") == "FRIEND"


def test_slug():
    assert cl.slug_from_media("https://x.github.io/img/heels/foo-123/ig_image_1.jpg", "img/heels") == "foo-123"
    assert cl.slug_from_media("https://x.github.io/img/heels/foo-123.jpg", "img/heels") == "foo-123"
    assert cl.slug_from_media("https://x.io/other/a.jpg", "img/heels") is None


def test_score_rate():
    r = {"likes": 10, "saves": 2, "shares": 1, "comments": 3, "follows": 1, "views": 100}
    assert cl.score(r) == 10 + 4 + 3 + 3 + 5
    assert cl.rate(r) == 25 / 100
    assert cl.rate({**r, "views": 49}) is None


def _fixture(tmp_path):
    d = tmp_path / "2026-10-16" / "shoe-1"
    d.mkdir(parents=True)
    (d / "_BRIEF.md").write_text(NEW, encoding="utf-8")
    states = {"2026-10-16/shoe-1": {"choice": "B", "chosen": "ad_B.jpg"}, "_meta": {"x": 1}}
    posts = [
        {"_id": "p1", "status": "published", "mediaItems": [{"url": "https://h/img/heels/shoe-1/ig_image_1.jpg"}],
         "platforms": [{"platform": "instagram"}]},
        {"_id": "p2", "status": "scheduled", "mediaItems": [{"url": "https://h/img/heels/shoe-1/ig_image_1.jpg"}]},
        {"_id": "p3", "status": "published", "mediaItems": [{"url": "https://h/img/heels/nobrief/a.jpg"}]},
    ]
    pp = {"p1": {"views": 200, "likes": 10, "saves": 2, "shares": 0, "comments": 1, "follows": 0,
                 "platform": "instagram", "published_at": "2026-10-16"}}
    return posts, pp, states


def test_build_dataset(tmp_path):
    posts, pp, states = _fixture(tmp_path)
    rows = cl.build_dataset(posts, pp, states, tmp_path)
    assert len(rows) == 1
    r = rows[0]
    assert r["shot_id"] == "ST01" and r["camera"] == "SET" and r["choice"] == "B"
    assert r["score"] == 15 and abs(r["rate"] - 0.075) < 1e-9


def _row(sid, cam, score, views=100, plat="instagram"):
    return {"shot_id": sid, "camera": cam, "label": sid, "score": score, "views": views,
            "rate": score / views, "platform": plat}


def test_aggregate_shrinkage():
    rows = [_row("PH01", "PHONE", 50)] + [_row("PH02", "PHONE", 40) for _ in range(10)] + \
           [_row("ST01", "SET", 10) for _ in range(4)]
    a = cl.aggregate(rows)
    assert a["shots"]["PH01"]["mean_score"] == 50
    assert a["ranking"][0] == "PH02"            # one lucky post does not win
    assert a["cameras"]["PHONE"]["n"] == 11
    assert "instagram" in a["shots"]["PH02"]["by_platform"]


def test_section_idempotent_and_isolated():
    rows = [_row("PH01", "PHONE", 30) for _ in range(6)]
    sec = cl.render_section(cl.aggregate(rows), "2026-10-16")
    assert "PH01" in sec
    base = "# Title\n\nkeep this\n"
    once = cl.replace_section(base, sec)
    twice = cl.replace_section(once, sec)
    assert once == twice
    assert once.startswith(base)
    after = cl.replace_section("A\n" + once + "\ntail text\n", sec.replace("PH01", "PH09"))
    assert after.startswith("A\n# Title") and after.endswith("\ntail text\n")
    assert "PH09" in after and after.count(cl.START) == 1


def test_small_sample():
    sec = cl.render_section(cl.aggregate([_row("PH01", "PHONE", 5)]), "2026-10-16")
    assert "too small" in sec


def test_find_brief_bare_key(tmp_path):
    posts, pp, states = _fixture(tmp_path)
    states = {"shoe-1": {"choice": "A"}}
    rows = cl.build_dataset(posts, pp, states, tmp_path)
    assert len(rows) == 1 and rows[0]["shot_id"] == "PH03"


def test_tiktok_post_matched_through_catalog_post_ids(tmp_path):
    import creative_learning as cl
    cat = [{"post_ids": ["tt1"], "assets": {"images_ig": ["https://x.github.io/img/heels/shoe-a/ig_image_1.jpg"]}}]
    ps = cl.post_slugs_from_catalog(cat, "img/heels")
    assert ps == {"tt1": "shoe-a"}
    (tmp_path / "2026-10-20" / "shoe-a").mkdir(parents=True)
    (tmp_path / "2026-10-20" / "shoe-a" / "_BRIEF.md").write_text(
        "1. PH02 · CAMERA: PHONE x\n2. ST01 · CAMERA: SET y\n3. BT01 · CAMERA: BTS z\n4. PH05 · CAMERA: PHONE w\n",
        encoding="utf-8")
    posts = [{"_id": "tt1", "status": "published",
              "mediaItems": [{"url": "https://media.zernio.com/abc.jpg"}]}]
    per_post = {"tt1": {"views": 100, "likes": 5, "saves": 1, "shares": 0, "comments": 0,
                        "follows": 0, "platform": "tiktok"}}
    states = {"2026-10-20/shoe-a": {"status": "finalized", "choice": "B"}}
    rows = cl.build_dataset(posts, per_post, states, tmp_path, ps)
    assert len(rows) == 1 and rows[0]["shot_id"] == "ST01" and rows[0]["camera"] == "SET"
