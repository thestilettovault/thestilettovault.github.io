# -*- coding: utf-8 -*-
"""
collect_metrics.py — aggregate the whole Stiletto Vault into dashboard/data.json.

One snapshot the dashboard reads: funnel (scanned→approved→produced→scheduled→
published), per-shoe status, the schedule, plus sales / traffic / followers.
Every external source (Admitad, GA, Zernio) is wrapped so a failure degrades to
`source_status:"unavailable"` (or a manual-file fallback) without breaking the
local metrics, which always work.

Usage:
    py -3 collect_metrics.py            # write dashboard/data.json
    py -3 collect_metrics.py --push     # + git commit & push (live dashboard)
"""
import sys, os, re, json, subprocess, argparse
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8") if sys.stdout else None
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import space_runner  # slugify (unique per AliExpress /item)

ROOT     = Path(__file__).resolve().parent.parent
DATA     = ROOT / "data"
GELEM    = ROOT / "GELEM"
DASH     = ROOT / "dashboard"
CATALOG  = DATA / "approved_catalog.json"


def _load(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def load_catalog():
    return _load(CATALOG, [])


# ── produced detection (same rule as build_site: our own post_image/ad) ──
def produced_dir(slug):
    d = GELEM / slug
    if not d.is_dir():
        matches = [x for x in GELEM.glob(f"{slug}*") if x.is_dir()] if GELEM.is_dir() else []
        d = matches[0] if matches else d
    if not d.is_dir():
        return None
    if (d / "post_image.jpg").exists():
        return d
    if any(p.name.lower().startswith("ad_") for p in d.iterdir()):
        return d
    return None


def our_hosted_image(it):
    """Produced image already hosted on our own Pages (older flow) — counts as
    produced, same rule as build_site.our_hosted_image."""
    a = it.get("assets", {}) or {}
    for v in [a.get("image_1x1")] + (a.get("images_ig") or []) + [it.get("image_url", "")]:
        if v and "thestilettovault.github.io" in v:
            return v
    return None


def is_produced(it):
    return bool(produced_dir(space_runner.slugify(it)) or our_hosted_image(it))


# ── Funnel ───────────────────────────────────────────────────────────
def funnel(catalog):
    pool = _load(DATA / "aliexpress_pool.json", {})
    pool_products = pool.get("products", pool) if isinstance(pool, dict) else pool
    scanned   = len(pool_products) if isinstance(pool_products, list) else 0
    approved  = len(catalog)
    produced  = sum(1 for it in catalog if is_produced(it))
    published = sum(1 for it in catalog if it.get("posted"))
    scheduled = len(parse_schedule())
    return {"scanned": scanned, "approved": approved, "produced": produced,
            "scheduled": scheduled, "published": published}


# ── Per-shoe ─────────────────────────────────────────────────────────
def shoe_status(it, slug):
    if it.get("posted"):
        return "published"
    if is_produced(it):
        return "produced"
    return "approved"


def shoes(catalog):
    out = []
    for it in catalog:
        slug = space_runner.slugify(it)
        deal = it.get("deal", {}) or {}
        disc = str(deal.get("discount", "") or "").strip()
        title = it.get("title", "")
        name = f"{title} · {disc} OFF" if disc and disc not in ("0%", "0", "") else title
        out.append({
            "slug": slug,
            "title": title,
            "name": name,
            "price": f"${deal.get('sale')}" if deal.get("sale") else "",
            "was": f"${deal.get('was')}" if deal.get("was") else "",
            "discount": disc,
            "rating": deal.get("rating", ""),
            "sold": deal.get("sold", ""),
            "status": shoe_status(it, slug),
            "on_site": is_produced(it),
            "subid": slug,                       # subid == slug (see affiliate_links)
            "aff_link": it.get("aff_link") or it.get("url", ""),
            "date": it.get("date", "")[:10],
            "clicks": None,                      # filled from traffic if GA maps it
            "sales": None,                       # filled from sales.per_shoe
        })
    out.sort(key=lambda s: s["date"], reverse=True)
    return out


# ── Schedule (parse GELEM/_SCHEDULE.md table) ────────────────────────
def parse_schedule():
    p = GELEM / "_SCHEDULE.md"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(\d+)\s*\|\s*([\d-]+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
        if m:
            rows.append({"n": int(m.group(1)), "date": m.group(2).strip(),
                         "day": m.group(3).strip(), "product": m.group(4).strip(),
                         "source": m.group(5).strip(), "status": m.group(6).strip()})
    return rows


# ── Sales (Admitad statistics API → fallback manual) ─────────────────
def sales():
    manual = _load(DATA / "manual_sales.json", {})
    try:
        import admitad_stats  # optional helper; added when Admitad scope is confirmed
        data = admitad_stats.fetch_conversions()
        data["source_status"] = "admitad"
        try:                                     # clicks per subid → conversion rate
            c = admitad_stats.fetch_clicks()
            data["total_clicks"] = c["total_clicks"]
            data["clicks_per_shoe"] = c["per_shoe"]
            data["conversion_rate"] = round(data["total_sales"] / c["total_clicks"], 4) \
                if c["total_clicks"] else None
        except Exception as e:
            data["clicks_note"] = str(e)[:120]
        return data
    except Exception as e:
        base = {"source_status": "manual" if manual else "unavailable",
                "note": str(e)[:120]}
        base.update(manual if isinstance(manual, dict) else {})
        base.setdefault("total_sales", manual.get("total_sales", 0) if isinstance(manual, dict) else 0)
        base.setdefault("total_revenue", manual.get("total_revenue", 0) if isinstance(manual, dict) else 0)
        base.setdefault("per_shoe", manual.get("per_shoe", {}) if isinstance(manual, dict) else {})
        return base


# ── Traffic (GA4 Data API → fallback N/A) ────────────────────────────
def traffic():
    try:
        import ga_stats  # optional helper; added when GA service-account is set up
        data = ga_stats.fetch()
        data["source_status"] = "ga4"
        return data
    except Exception as e:
        return {"source_status": "unavailable", "visitors": None,
                "clicks": None, "note": str(e)[:120]}


# ── Followers (manual file → later Zernio/API) ───────────────────────
def followers():
    manual = _load(DATA / "manual_followers.json", {})
    if manual:
        manual["source_status"] = "manual"
        return manual
    return {"source_status": "unavailable", "instagram": None, "tiktok": None}


def main(push=False):
    catalog = load_catalog()
    sales_data = sales()
    per_shoe = sales_data.get("per_shoe", {}) if isinstance(sales_data, dict) else {}
    traffic_data = traffic()
    clicks_by_shoe = traffic_data.get("per_shoe", {}) if isinstance(traffic_data, dict) else {}
    adm_clicks = sales_data.get("clicks_per_shoe", {}) if isinstance(sales_data, dict) else {}
    sh = shoes(catalog)
    for s in sh:                                 # merge sales + clicks into each shoe
        rec = per_shoe.get(s["subid"])
        if rec:
            s["sales"] = rec.get("sales")
        if s["subid"] in adm_clicks:             # Admitad subids may be truncated slugs
            s["clicks"] = adm_clicks[s["subid"]]
        else:
            m = [v for k, v in adm_clicks.items() if k and (k in s["subid"] or s["subid"] in k)]
            if m:
                s["clicks"] = sum(m)
        crec = clicks_by_shoe.get(s["subid"])
        if crec and s.get("clicks") is None:
            s["clicks"] = crec.get("clicks")
    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "funnel": funnel(catalog),
        "shoes": sh,
        "schedule": parse_schedule(),
        "sales": sales_data,
        "traffic": traffic_data,
        "followers": followers(),
    }
    DASH.mkdir(exist_ok=True)
    (DASH / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    f = data["funnel"]
    print(f"✅ data.json — scanned {f['scanned']} · approved {f['approved']} · "
          f"produced {f['produced']} · scheduled {f['scheduled']} · published {f['published']}")
    print(f"   sales:{data['sales']['source_status']} traffic:{data['traffic']['source_status']} "
          f"followers:{data['followers']['source_status']}")

    if push:
        for c in (["git", "-C", str(ROOT), "add", "dashboard"],
                  ["git", "-C", str(ROOT), "commit", "-m", "chore(dashboard): refresh metrics snapshot"],
                  ["git", "-C", str(ROOT), "push", "origin", "main"]):
            r = subprocess.run(c, capture_output=True, text=True)
            out = (r.stdout or "") + (r.stderr or "")
            if r.returncode and not any(b in out for b in ("nothing to commit", "up to date", "up-to-date")):
                print(out.strip()); break
        else:
            print("✅ pushed live")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    main(ap.parse_args().push)
