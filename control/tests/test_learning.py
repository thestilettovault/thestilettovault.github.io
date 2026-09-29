import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from control import learning


def make_shoe(**kwargs):
    base = {
        "slug": "shoe-1",
        "title": "Test Shoe",
        "price": "$26.12",
        "was": "$64.25",
        "discount": "59%",
        "rating": "4.7",
        "sold": "500+ sold",
        "status": "produced",
        "aff_link": "https://rzekl.com/g/xyz/?ulp=aliexpress",
        "date": "2026-09-29",
        "clicks": 2,
        "sales": None,
    }
    base.update(kwargs)
    return base


def test_features_price_bands():
    assert learning.features(make_shoe(price="$15"))["price_band"] == "<$20"
    assert learning.features(make_shoe(price="$25"))["price_band"] == "$20-50"
    assert learning.features(make_shoe(price="$75"))["price_band"] == "$50-100"
    assert learning.features(make_shoe(price="$150"))["price_band"] == "$100+"
    assert learning.features(make_shoe(price=None))["price_band"] == "unknown"
    assert learning.features(make_shoe(price="bad"))["price_band"] == "unknown"


def test_features_program_detection():
    assert learning.features(make_shoe(aff_link="https://rzekl.com/g/1/?ulp=x"))["program"] == "aliexpress"
    assert learning.features(make_shoe(aff_link="https://www.amazon.com/dp/123"))["program"] == "amazon"
    assert learning.features(make_shoe(aff_link="https://amzn.to/abc"))["program"] == "amazon"
    assert learning.features(make_shoe(aff_link="https://gthic.com/product/1"))["program"] == "gthic.com"
    assert learning.features(make_shoe(aff_link=None))["program"] == "unknown"


def test_features_discount_bands():
    assert learning.features(make_shoe(discount="0%"))["discount_band"] == "none"
    assert learning.features(make_shoe(discount=None))["discount_band"] == "none"
    assert learning.features(make_shoe(discount="15%"))["discount_band"] == "<30%"
    assert learning.features(make_shoe(discount="45%"))["discount_band"] == "30-60%"
    assert learning.features(make_shoe(discount="75%"))["discount_band"] == "60%+"


def test_features_weekday():
    # 2026-09-29 is a Tuesday -> "שלישי"
    assert learning.features(make_shoe(date="2026-09-29"))["weekday"] == "שלישי"
    assert learning.features(make_shoe(date=None))["weekday"] == "unknown"
    assert learning.features(make_shoe(date="not-a-date"))["weekday"] == "unknown"


def test_features_has_video_from_state():
    shoe = make_shoe(slug="shoe-x")
    state = {"shoe-x": {"video": "E:/PROJECTS/thegothicvault/GELEM/shoe-x/video.mp4"}}
    assert learning.features(shoe, state=state)["has_video"] is True
    assert learning.features(shoe, state={})["has_video"] is False


def test_features_has_video_from_gelem_root(tmp_path):
    shoe = make_shoe(slug="shoe-y")
    gelem_dir = tmp_path / "shoe-y"
    gelem_dir.mkdir()
    (gelem_dir / "video.mp4").write_bytes(b"fake")
    assert learning.features(shoe, gelem_root=str(tmp_path))["has_video"] is True
    assert learning.features(make_shoe(slug="missing"), gelem_root=str(tmp_path))["has_video"] is False


def test_table_none_clicks_treated_as_zero():
    shoes = [make_shoe(slug="a", clicks=None, price="$15"), make_shoe(slug="b", clicks=4, price="$15")]
    rows = learning.table(shoes)
    price_row = next(r for r in rows if r["attribute"] == "price_band" and r["value"] == "<$20")
    assert price_row["shoes"] == 2
    assert price_row["clicks"] == 4
    assert price_row["clicks_per_shoe"] == 2.0


def test_table_sorted_by_attribute_then_clicks_desc():
    shoes = [
        make_shoe(slug="a", price="$15", clicks=1),
        make_shoe(slug="b", price="$25", clicks=10),
    ]
    rows = learning.table(shoes)
    price_rows = [r for r in rows if r["attribute"] == "price_band"]
    assert price_rows[0]["clicks_per_shoe"] >= price_rows[1]["clicks_per_shoe"]
    attrs = [r["attribute"] for r in rows]
    assert attrs == sorted(attrs)


def test_summary_min_shoes_filtering():
    shoes = [make_shoe(slug=f"a{i}", price="$15", clicks=1) for i in range(4)]
    shoes += [make_shoe(slug="rare", price="$150", clicks=100)]
    rows = learning.table(shoes)
    lines = learning.summary(rows, min_shoes=3)
    text = " ".join(lines)
    # the $100+ band only has 1 shoe, below min_shoes=3, so it must be excluded
    assert "$100+" not in text
    assert "<$20" in text


def test_summary_zero_clicks_message():
    shoes = [make_shoe(slug="a", clicks=0), make_shoe(slug="b", clicks=None)]
    rows = learning.table(shoes)
    assert learning.summary(rows) == ["אין עדיין מספיק נתוני קליקים ללמידה."]


def test_load_default_reads_real_files():
    shoes, states = learning.load_default()
    assert isinstance(shoes, list)
    assert isinstance(states, dict)
