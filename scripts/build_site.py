# -*- coding: utf-8 -*-
"""
build_site.py — inject approved heel products into index.html.

Reads data/approved_catalog.json (written by taste_engine.record_approval when
you press the Telegram OK button) and renders product cards between the
<!-- HEELS:START --> / <!-- HEELS:END --> markers in index.html.

Image priority per product:
  1. A generated variation in GELEM/<slug>/  → copied into img/heels/<slug>.jpg
     and referenced locally (served by GitHub Pages after push).
  2. The catalog image_url (a hosted CDN URL) → referenced directly.

Usage:
    python build_site.py           # rebuild index.html (no push)
    python build_site.py --push    # rebuild + git commit + push live
    python build_site.py --limit 12   # (default = all)
"""
import sys, os, re, json, shutil, subprocess, argparse
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8") if sys.stdout else None
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import space_runner      # single source of truth for slugify (AliExpress /item ids)
import affiliate_links   # subid-tagged deeplinks for per-shoe sale attribution

ROOT         = Path(__file__).resolve().parent.parent      # E:\PROJECTS\thegothicvault
CATALOG_FILE = ROOT / "data" / "approved_catalog.json"
INDEX_FILE   = ROOT / "index.html"
GELEM_DIR    = ROOT / "GELEM"
IMG_DIR      = ROOT / "img" / "heels"

START_MARK = "<!-- HEELS:START -->"
END_MARK   = "<!-- HEELS:END -->"

IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")


# ── Helpers ───────────────────────────────────────────────────────────

def load_catalog():
    if not CATALOG_FILE.exists():
        return []
    with open(CATALOG_FILE, encoding="utf-8-sig") as f:  # tolerate a stray BOM
        return json.load(f)


def save_catalog(catalog):
    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)


# Reuse space_runner.slugify so each AliExpress heel gets a UNIQUE slug (it
# appends the /item id). The old Shopify-only version collapsed every generic
# "Stiletto Heels" to one slug → all shared a single image on the site.
slugify = space_runner.slugify


def find_variation_image(slug):
    """OUR produced image for this heel — never the AliExpress source/scrape.
    Only the ad Ofer CHOSE in Telegram: un-picked AI candidates can be broken
    (2026-10-09: an un-picked ad_A with three legs went live). Returns None until
    he picks → the heel stays off the site until then."""
    # A heel's folder is GELEM/<slug> or, for older drops, GELEM/<date>/<slug>.
    folders = [GELEM_DIR / slug] + sorted(GELEM_DIR.glob(f"*/{slug}"), reverse=True) \
        if GELEM_DIR.is_dir() else []
    # The site shows the CLEAN shoe photo (no burned-in price/headline) so the
    # catalog looks uniform. post_image.jpg (chosen ad + deal overlay) is for social only.
    try:
        st = json.loads((ROOT / "data" / "orchestrator_state.json").read_text(encoding="utf-8"))
    except Exception:
        st = {}
    for folder in (f for f in folders if f.is_dir()):
        chosen = (st.get(slug) or {}).get("chosen")
        if chosen and (folder / chosen).exists():
            return folder / chosen
        clean = clean_ad_behind_post(folder)
        if clean:
            return clean
    return None


def clean_ad_behind_post(folder):
    """Older drops recorded no choice, but post_image.jpg IS the chosen ad with a
    price band burned on top. The ad whose lower part matches it is the clean pick."""
    post = folder / "post_image.jpg"
    ads = sorted(p for p in folder.glob("ad_*") if p.suffix.lower() in IMG_EXTS)
    if not post.exists() or not ads:
        return None
    try:
        from PIL import Image, ImageChops, ImageStat
        def lower(p):
            im = Image.open(p).convert("L").resize((128, 128))
            return im.crop((0, 48, 128, 128))          # skip the overlay band at the top
        ref = lower(post)
        scored = sorted((ImageStat.Stat(ImageChops.difference(ref, lower(a))).mean[0], a) for a in ads)
        return scored[0][1] if scored[0][0] < 12 else None
    except Exception:
        return None


def resolve_image(item, slug):
    """
    Decide the <img src> for a product.
    Copies a local variation into img/heels/ when available; otherwise uses the
    hosted catalog image_url. Returns a src string or "".
    """
    # Manual override: a clean store photo when we have no clean produced image
    # (older drops whose AI art has headlines burned in). Repo-relative path.
    if item.get("site_image") and (ROOT / item["site_image"]).exists():
        return item["site_image"]
    var = find_variation_image(slug)
    if var:
        IMG_DIR.mkdir(parents=True, exist_ok=True)
        dest = IMG_DIR / f"{slug}.jpg"
        try:
            shutil.copyfile(var, dest)
            return f"img/heels/{slug}.jpg"
        except Exception as e:
            print(f"  ! copy failed for {slug}: {e}")
    hosted = our_hosted_image(item)   # older heels: produced assets already on our Pages
    if hosted:
        return hosted
    return ""   # only AliExpress raw / broken remains → heel is skipped


def our_hosted_image(item):
    """A produced image already hosted on OUR site (thestilettovault) — this is
    ours, not an AliExpress scrape. Covers heels made through the older flow whose
    art lives in the catalog `assets`/`image_url` rather than GELEM."""
    a = item.get("assets", {}) or {}
    for v in [a.get("image_1x1")] + (a.get("images_ig") or []) + [item.get("image_url", "")]:
        if v and "thestilettovault.github.io" in v:
            # Our Pages serves the repo root, so a hosted URL is only real if the
            # file backing it exists in the repo. Otherwise it 404s on the live
            # site (a "phantom" heel) — return None so the heel is skipped.
            rel = v.split("thestilettovault.github.io/", 1)[-1].split("?")[0].lstrip("/")
            if rel and (ROOT / rel).exists():
                return v
    return None


def esc(s):
    return (s or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def short_name(title, n=26):
    t = (title or "").strip()
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


CATS = [("boots", ("boot",)), ("platforms", ("platform",)),
        ("sandals", ("sandal", "slingback", "strappy", "mule")),
        ("pumps", ("pump", "court")), ("stilettos", ("stiletto", "heel"))]
COLORS = ["black", "white", "red", "pink", "nude", "beige", "brown", "silver", "gold",
          "blue", "green", "purple", "clear", "leopard", "burgundy"]


def card_meta(item):
    """Facets for the on-site catalog filters: category, color, store, price, discount."""
    t = (item.get("title", "") + " " + item.get("url", "")).lower()
    cat = next((c for c, keys in CATS if any(k in t for k in keys)), "stilettos")
    color = next((c for c in COLORS if c in t), "")
    deal = item.get("deal", {}) or {}
    try:
        price = float(str(deal.get("sale") or item.get("price") or "").replace("$", "") or 0)
    except ValueError:
        price = 0
    disc = "".join(ch for ch in str(deal.get("discount") or "") if ch.isdigit()) or "0"
    host = (item.get("domain") or "").lower() or \
        (item.get("url", "").split("/")[2].lower() if "://" in item.get("url", "") else "")
    store = {"aliexpress": "AliExpress", "amazon": "Amazon", "nakedwolfe": "Naked Wolfe",
             "publicdesire": "Public Desire", "darkinlove": "Dark In Love", "gthic": "GTHIC"}.get(
        host.replace("www.", "").split(".")[0], host.replace("www.", "").split(".")[0].replace("-", " ").title())
    return {"cat": cat, "color": color, "price": f"{price:.2f}" if price else "",
            "disc": disc, "store": store, "date": (item.get("date") or "")[:10]}


def card_html(item, slug):
    src   = resolve_image(item, slug)
    # Tag the affiliate link with subid=slug so a sale on Admitad is attributable
    # to THIS heel. Visitors reach the site via link-in-bio, so tagging the card
    # here is what makes per-shoe sales measurable.
    href  = esc(affiliate_links.affiliate_link(item, subid=slug))
    alt   = esc(item.get("title", ""))
    # Names/prices come from the real deal (what the bot sent to Telegram), since
    # the raw title is generic ("Stiletto Heels"). Discount differentiates the name;
    # the live sale price replaces the placeholder "Shop".
    deal  = item.get("deal", {}) or {}
    title = short_name(item.get("title", ""))
    disc  = str(deal.get("discount", "") or "").strip()
    name  = f"{title} · {disc} OFF" if disc and disc not in ("0%", "0", "") else title
    sale  = deal.get("sale")
    price = f"${sale}" if sale else (item.get("price", "") or "Shop")
    name  = esc(name)
    price = esc(str(price))
    # GA event on click → we see how many people clicked "buy" per shoe, live,
    # even before a sale lands in Admitad. Guarded so it never breaks if gtag is blocked.
    onclick = (f"if(window.gtag)gtag('event','affiliate_click',"
               f"{{'shoe':'{slug}','discount':'{disc}'}});")
    m = {k: esc(v) for k, v in card_meta(item).items()}
    badge = f'        <span class="card-badge">-{m["disc"]}%</span>\n' if m["disc"] not in ("", "0") else ""
    store = f'          <span class="card-store">{m["store"]}</span>\n' if m["store"] else ""
    return (
        '      <a class="product-card" href="{href}" target="_blank" rel="sponsored noopener" onclick="{onclick}" '
        'data-cat="{m[cat]}" data-color="{m[color]}" data-price="{m[price]}" data-disc="{m[disc]}" '
        'data-store="{m[store]}" data-date="{m[date]}">\n'
        '        <img src="{src}" alt="{alt}" loading="lazy">\n'
        '{badge}'
        '        <div class="card-info">\n'
        '{store}'
        '          <span class="card-name">{name}</span>\n'
        '          <span class="card-price">{price}</span>\n'
        '        </div>\n'
        '      </a>'
    ).format(href=href, src=esc(src), alt=alt, name=name, price=price, onclick=onclick,
             m=m, badge=badge, store=store)


def build_cards(items):
    """Render items in 2-up pair-grids, trailing odd item as single-grid."""
    blocks = []
    i = 0
    while i < len(items):
        pair = items[i:i + 2]
        cards = "\n".join(card_html(it, slugify(it)) for it in pair)
        if len(pair) == 2:
            blocks.append(f'    <div class="pair-grid">\n{cards}\n    </div>')
        else:
            blocks.append(f'    <div class="single-grid">\n{cards}\n    </div>')
        i += 2
    # separators between rows, matching the site style
    return "\n    <div class=\"pair-sep\">· · ·</div>\n".join(blocks)


# ── Main build ────────────────────────────────────────────────────────

def rebuild(limit):
    catalog = load_catalog()
    if not catalog:
        print("Catalog is empty — nothing to inject.")
        return False

    # newest first, one card per shoe (same shoe under www./non-www or a ref param = dup)
    from product_key import dedupe
    items = sorted(catalog, key=lambda x: x.get("date", ""), reverse=True)
    items, dups = dedupe(items)
    for d in dups:
        print(f"  skip duplicate: {d.get('title','')[:50]} ({d.get('url','')})")
    # need a usable affiliate link AND a produced visual of our own (post_image/ad).
    # heels we only approved but never produced are held back until they have art.
    items = [it for it in items
             if (it.get("aff_link") or it.get("url"))
             and (it.get("site_image") or find_variation_image(slugify(it)) or our_hosted_image(it))][:limit]

    inner = build_cards(items)
    injection = f"{START_MARK}\n{inner}\n    {END_MARK}"

    html = INDEX_FILE.read_text(encoding="utf-8")
    if START_MARK not in html or END_MARK not in html:
        print("ERROR: markers not found in index.html — aborting.")
        return False

    # function replacement → no backslash/group-ref interpretation on the HTML
    new_html = re.sub(
        re.escape(START_MARK) + r".*?" + re.escape(END_MARK),
        lambda _m: injection,
        html,
        flags=re.DOTALL,
    )
    INDEX_FILE.write_text(new_html, encoding="utf-8")
    print(f"✅ Injected {len(items)} heel cards into index.html")

    # mark on_site
    on_urls = {it.get("url") for it in items}
    for it in catalog:
        if it.get("url") in on_urls:
            it["on_site"] = True
    save_catalog(catalog)
    return True


def git_push():
    cmds = [
        ["git", "-C", str(ROOT), "add", "index.html", "img"],
        ["git", "-C", str(ROOT), "commit", "-m",
         f"site: heel drops {datetime.now():%Y-%m-%d}"],
        ["git", "-C", str(ROOT), "push", "origin", "main"],
    ]
    for c in cmds:
        r = subprocess.run(c, capture_output=True, text=True)
        print(f"$ {' '.join(c[3:])}\n{(r.stdout or '').strip()}{(r.stderr or '').strip()}")
        if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
            print("  (git step non-zero — stopping push)")
            return
    print("✅ Pushed live")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="git commit + push after build")
    ap.add_argument("--limit", type=int, default=500, help="max cards (default: all — every posted heel must be on the site, the bio link points here)")
    args = ap.parse_args()

    if rebuild(args.limit) and args.push:
        git_push()
