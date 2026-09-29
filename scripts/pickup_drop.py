# -*- coding: utf-8 -*-
"""
pickup_drop.py — the auto-pickup glue that runs the moment a Magnific Space
finishes. Turns Space output into a live, scheduled 3-post drop, hands-free.

WHERE IT FITS
-------------
  8:00 scout → Telegram approval → (agent runs the Space via spaces_* MCP) →
  ►► pickup_drop ◄◄ → GitHub Pages hosting → catalog → 3 scheduled posts.

The agent, once the Space run completes, has three output URLs:
  • the 1:1 static ad image      (Instagram feed)
  • the 9:16 static ad image     (TikTok / Reels still)
  • the 9:16 6s video ad         (the hero post)
It calls:

  python pickup_drop.py <slug> \
      --img1x1 <url> --img9x16 <url> --video <url> --push --publish

…or, if the assets are already downloaded into the heel's GELEM folder
(insta_1x1.png / tiktok_9x16.png / video_9x16.mp4 — the lishan convention):

  python pickup_drop.py <slug> --from-gelem --push --publish

What it does:
  1. Resolve the heel in the catalog + its GELEM folder (glob *slug*).
  2. Fetch the 3 Space outputs into that GELEM folder (or reuse local files).
  3. Copy them to img/heels/<slug>/ with web names and record hosted URLs on
     the catalog item's "assets" (image_1x1 / image_9x16 / video). Also set
     image_url (1:1) as the site card hero + variations_ready = true.
  4. git add (force the mp4 past .gitignore) → commit → push, so the URLs go
     live on GitHub Pages.
  5. social_publisher.schedule_drop → 2 images + 1 video at 3 times today.

Dry by default: without --push nothing is committed; without --publish nothing
is scheduled. So `python pickup_drop.py <slug> --from-gelem` is a safe preview.
"""
import sys, os, re, json, shutil, argparse, subprocess, urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8") if sys.stdout else None
sys.path.insert(0, os.path.dirname(__file__))
import space_runner   # single source of truth for slugify (AliExpress /item ids)

ROOT         = Path(__file__).resolve().parent.parent
CATALOG_FILE = ROOT / "data" / "approved_catalog.json"
GELEM_DIR    = ROOT / "GELEM"
IMG_DIR      = ROOT / "img" / "heels"
SITE_URL     = "https://thestilettovault.github.io"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# Canonical local names the Space outputs land under, per role.
LOCAL_NAMES = {
    "image_1x1":  ["insta_1x1.png", "insta_1x1.jpg", "1x1.png", "1x1.jpg"],
    "image_9x16": ["tiktok_9x16.png", "tiktok_9x16.jpg", "9x16.png", "9x16.jpg"],
    "video":      ["video_9x16.mp4", "video_tiktok_9x16.mp4", "video.mp4"],
}
# Stable hosted basenames per role — the SOURCE extension is preserved (no format
# conversion), so a PNG stays a PNG.
WEB_BASE = {"image_1x1": "insta_1x1",
            "image_9x16": "tiktok_9x16",
            "video": "video_9x16"}

def web_name(role, src):
    return WEB_BASE[role] + src.suffix.lower()


def load_catalog():
    if not CATALOG_FILE.exists():
        return []
    with open(CATALOG_FILE, encoding="utf-8-sig") as f:
        return json.load(f)


def save_catalog(catalog):
    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)


# slugify lives in space_runner so the folder name that Space output was staged
# under matches exactly here. Its AliExpress branch appends the /item/<id>, which
# keeps the many generic "Stiletto Heels" listings from all collapsing to one slug.
slugify = space_runner.slugify


def find_item(want):
    for it in load_catalog():
        if slugify(it) == want:
            return it
    return None


def gelem_folder(slug, override=None):
    """Resolve the heel's GELEM folder. GELEM folders are named loosely
    (e.g. '2026-08-12_fancyqueen-gladiator') while the slug is the long,
    title-derived form ('fancyqueen-knee-high-…'), so we try, in order:
      1. an explicit --folder override,
      2. an exact GELEM/<slug>,
      3. a glob on the full slug,
      4. a glob on the brand token (first slug component), newest first.
    Falls back to GELEM/<slug> (created on demand) if nothing matches."""
    if override:
        p = Path(override)
        return p if p.is_absolute() else (GELEM_DIR / override)
    exact = GELEM_DIR / slug
    if exact.is_dir():
        return exact
    if not GELEM_DIR.is_dir():
        return exact
    matches = [d for d in GELEM_DIR.glob(f"*{slug}*") if d.is_dir()]
    if not matches:
        brand = slug.split("-", 1)[0]                       # e.g. 'fancyqueen'
        if len(brand) >= 4:
            matches = [d for d in GELEM_DIR.glob(f"*{brand}*") if d.is_dir()]
    if matches:
        return max(matches, key=lambda d: d.stat().st_mtime)  # newest
    return exact


def fetch(url, dest):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as r:
        dest.write_bytes(r.read())
    print(f"  fetched {dest.name}  ({dest.stat().st_size // 1024} KB)")
    return dest


# Current production naming (Higgsfield / manual): "INSTA POST 1.png",
# "TIK TOK POST 1.png", "INSTA.mp4", "TIKTOK VID.mp4" … matched case-insensitively
# by keyword after the canonical names miss. Each entry: (must-contain-all, extensions).
FALLBACK_MATCH = {
    "image_1x1":  [(("insta", "post"), (".png", ".jpg", ".jpeg"))],
    "image_9x16": [(("tik", "post"),   (".png", ".jpg", ".jpeg"))],
    "video":      [(("tik",),  (".mp4",)),      # prefer the TikTok 9:16 video
                   (("insta",), (".mp4",)),
                   ((),        (".mp4",))],       # any video as last resort
}


def local_asset(folder, role):
    for name in LOCAL_NAMES[role]:
        p = folder / name
        if p.exists():
            return p
    # Fallback: keyword match against current production filenames.
    files = sorted(p for p in folder.iterdir() if p.is_file())
    for keywords, exts in FALLBACK_MATCH.get(role, []):
        for p in files:
            low = p.name.lower()
            if low.endswith(exts) and all(k in low for k in keywords):
                return p
    return None


def stage_assets(slug, folder, urls, from_gelem):
    """Return {role: local Path} for whichever of the 3 assets we can resolve."""
    folder.mkdir(parents=True, exist_ok=True)
    staged = {}
    for role in ("image_1x1", "image_9x16", "video"):
        if from_gelem:
            p = local_asset(folder, role)
            if p:
                staged[role] = p
            continue
        url = urls.get(role)
        if not url:
            p = local_asset(folder, role)   # fall back to a local file if present
            if p:
                staged[role] = p
            continue
        ext = ".mp4" if role == "video" else ".jpg"
        dest = folder / (LOCAL_NAMES[role][0].rsplit(".", 1)[0] + ext)
        try:
            staged[role] = fetch(url, dest)
        except Exception as e:
            print(f"  ! fetch failed for {role} ({url[:60]}): {e}")
    return staged


def make_4x5(src, dest):
    """Instagram rejects stills taller than 4:5 (0.8). Derive an IG-valid 4:5
    from the 9:16 still: keep full width, crop height to width/0.8, anchored a
    little above centre so the headline + CTA survive. No-op if PIL is absent."""
    try:
        from PIL import Image
    except Exception:
        print("  ! PIL not available — skipping 4:5 derivation")
        return None
    im = Image.open(src); w, h = im.size          # keep native format (PNG stays PNG)
    th = int(round(w / 0.8))
    if th >= h:                                  # already ≤ 4:5, nothing to crop
        shutil.copyfile(src, dest); return dest
    top = max(0, min(int((h - th) * 0.30), h - th))
    im.crop((0, top, w, top + th)).save(dest)
    return dest


def host_assets(slug, staged):
    """Copy staged files into img/heels/<slug>/ and return {role: hosted URL}.
    Also derives an IG-valid 4:5 still from the 9:16 image (image_4x5)."""
    out_dir = IMG_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    hosted = {}
    names = {}
    for role, src in staged.items():
        name = web_name(role, src)
        names[role] = name
        shutil.copyfile(src, out_dir / name)      # copy AS-IS — no format conversion
        hosted[role] = f"{SITE_URL}/img/heels/{slug}/{name}"
        print(f"  hosted {role} → {hosted[role]}")
    # IG-valid 4:5 companion for the vertical still — same format (a crop, not a conversion)
    if "image_9x16" in staged:
        ext = Path(names["image_9x16"]).suffix.lower()
        fx = out_dir / f"insta_4x5{ext}"
        if make_4x5(out_dir / names["image_9x16"], fx):
            hosted["image_4x5"] = f"{SITE_URL}/img/heels/{slug}/insta_4x5{ext}"
            print(f"  hosted image_4x5 → {hosted['image_4x5']}")
    return hosted


def update_catalog(item, hosted):
    catalog = load_catalog()
    for it in catalog:
        if it.get("url") == item.get("url"):
            it.setdefault("assets", {}).update(hosted)
            if hosted.get("image_1x1"):
                it["image_url"] = hosted["image_1x1"]     # site card hero
            it["variations_ready"] = True
    save_catalog(catalog)
    print("  catalog updated (assets + variations_ready)")


# ── Dynamic media model — post EVERYTHING a folder holds ──────────────
# Content per shoe varies: 1–2 videos and 1–4 images PER PLATFORM. We detect
# all final post media, host each, and store per-platform lists so the whole
# drop goes out — not a fixed 3-post template.
# "ad_" = the A/B/C/D candidate ads the orchestrator downloads for the Telegram
# pick; only the chosen one, rebuilt as post_image / ig_*/tt_*, should ship.
_JUNK_PREFIX = ("source", "img_", "screenshot", "whatsapp", "magnific", "photo_", "ad_")
_VID_EXT = (".mp4", ".mov")
_IMG_EXT = (".png", ".jpg", ".jpeg")

def _norm(name):
    return name.lower().replace("_", " ").replace("-", " ")

def classify_media(folder):
    """{videos_ig, videos_tt, images_ig, images_tt} of local Paths, sorted, junk
    excluded. Platform by filename ('tik'→TikTok, else 'inst'→Instagram)."""
    out = {"videos_ig": [], "videos_tt": [], "images_ig": [], "images_tt": []}
    for p in sorted(folder.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file():
            continue
        low = p.name.lower()
        if low.startswith(_JUNK_PREFIX):
            continue
        n = _norm(p.name)
        is_vid = low.endswith(_VID_EXT)
        is_img = low.endswith(_IMG_EXT)
        if not (is_vid or is_img):
            continue
        # TikTok if named so; otherwise Instagram (default — robust to typos like
        # "INSATA", and only production media reaches here, junk already filtered).
        plat = "tt" if ("tik" in n or "tt " in n or n.startswith("tt")) else "ig"
        out[f"{'videos' if is_vid else 'images'}_{plat}"].append(p)
    return out

def host_all(slug, media):
    """Copy every classified file into img/heels/<slug>/ AS-IS (no conversion),
    with stable ordered names. Returns assets dict of hosted-URL lists."""
    out_dir = IMG_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    assets = {}
    label = {"videos_ig": "ig_video", "videos_tt": "tt_video",
             "images_ig": "ig_image", "images_tt": "tt_image"}
    for bucket, paths in media.items():
        urls = []
        for i, src in enumerate(paths, 1):
            name = f"{label[bucket]}_{i}{src.suffix.lower()}"
            shutil.copyfile(src, out_dir / name)
            urls.append(f"{SITE_URL}/img/heels/{slug}/{name}")
        assets[bucket] = urls
        if urls:
            print(f"  hosted {bucket}: {len(urls)} file(s)")
    # site-card hero = first Instagram image, else first TikTok image
    hero = (assets.get("images_ig") or assets.get("images_tt") or [None])[0]
    if hero:
        assets["image_1x1"] = hero
    return assets


def wait_for_live(item, slug, timeout=300, every=15):
    """Poll one hosted media URL until GitHub Pages serves it (HTTP 200), so Zernio
    doesn't reject freshly-pushed images with a 404. Returns True once live."""
    a = (find_item(slug) or item).get("assets", {}) or {}
    probe = (a.get("images_ig") or a.get("images_tt")
             or a.get("videos_ig") or a.get("videos_tt") or [None])[0]
    if not probe:
        return True
    import time as _t
    waited = 0
    while waited < timeout:
        try:
            req = urllib.request.Request(probe, method="HEAD", headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status == 200:
                    print(f"  media live after {waited}s")
                    return True
        except Exception:
            pass
        _t.sleep(every); waited += every
        print(f"  waiting for GitHub Pages deploy… {waited}s")
    print("  ! media still not live after timeout — scheduling anyway (may 404)")
    return False


def git_push(slug):
    out_dir = IMG_DIR / slug
    # the site card uses the flat cover img/heels/<slug>.<ext> (NOT inside the folder) —
    # it was never added, so every drop went live with an empty card (fixed 2026-09-29)
    covers = [str(p) for p in IMG_DIR.glob(f"{slug}.*") if p.is_file()]
    cmds = [
        ["git", "-C", str(ROOT), "add", "-f", str(out_dir), *covers, "data/approved_catalog.json", "index.html"],
        ["git", "-C", str(ROOT), "commit", "-m", f"drop: {slug} assets live"],
        ["git", "-C", str(ROOT), "push", "origin", "main"],
    ]
    for c in cmds:
        r = subprocess.run(c, capture_output=True, text=True)
        out = (r.stdout or "") + (r.stderr or "")
        print(f"$ {' '.join(c[3:])}\n{out.strip()}")
        # A clean tree (nothing new to commit) is not a failure — git phrases it
        # several ways depending on whether untracked files exist.
        benign = ("nothing to commit", "nothing added to commit",
                  "working tree clean", "up to date", "up-to-date")
        if r.returncode != 0 and not any(b in out for b in benign):
            print("  (git step non-zero — stopping push)")
            return False
    print("✅ pushed live")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", help="catalog slug of the heel (e.g. fancyqueen-…)")
    ap.add_argument("--img1x1", help="Space output URL: 1:1 static ad image")
    ap.add_argument("--img9x16", help="Space output URL: 9:16 static ad image")
    ap.add_argument("--video", help="Space output URL: 9:16 6s video ad")
    ap.add_argument("--from-gelem", action="store_true",
                    help="reuse assets already downloaded in the GELEM folder")
    ap.add_argument("--folder", help="explicit GELEM folder name/path (overrides auto-resolve)")
    ap.add_argument("--slots", default="14:00,18:00,22:00",
                    help="comma-separated HH:MM times for the 3 posts")
    ap.add_argument("--date", help="pin the drop to a specific day YYYY-MM-DD "
                    "(this heel's every-other-day slot); default = next free day")
    ap.add_argument("--push", action="store_true", help="commit + push assets live")
    ap.add_argument("--publish", action="store_true", help="schedule the 3 posts via Zernio")
    a = ap.parse_args()

    item = find_item(a.slug)
    if not item:
        print(f"slug not found in catalog: {a.slug}")
        sys.exit(1)

    folder = gelem_folder(a.slug, a.folder)
    print(f"Heel: {item.get('title','')[:50]}\n  GELEM: {folder}")

    if a.from_gelem:
        # Dynamic: host EVERY final post file the folder holds (variable counts).
        media = classify_media(folder)
        counts = {k: len(v) for k, v in media.items() if v}
        if not counts:
            print("  ! no post media found in folder (INSTA*/TIKTOK* files)")
            sys.exit(1)
        print(f"  media: {counts}")
        hosted = host_all(a.slug, media)
    else:
        urls = {"image_1x1": a.img1x1, "image_9x16": a.img9x16, "video": a.video}
        staged = stage_assets(a.slug, folder, urls, a.from_gelem)
        if not staged:
            print("  ! no assets resolved — pass --img1x1/--img9x16/--video or --from-gelem")
            sys.exit(1)
        print(f"  staged: {list(staged)}")
        hosted = host_assets(a.slug, staged)
    update_catalog(item, hosted)

    # rebuild the site card (image_url now points at the hosted 1:1)
    subprocess.run([sys.executable, str(Path(__file__).parent / "build_site.py")],
                   capture_output=True, text=True)

    if a.push:
        if not git_push(a.slug):
            print("  ! push failed — not scheduling (media URLs would 404)")
            sys.exit(1)
        # GitHub Pages needs a moment to deploy; Zernio validates image URLs at
        # schedule time, so wait until the media is actually reachable (else 404).
        if a.publish:
            wait_for_live(item, a.slug)
    else:
        print("  (dry: skipping git push — pass --push to host live)")

    # schedule the drop
    import social_publisher as sp
    slots = [s.strip() for s in a.slots.split(",") if s.strip()]
    fresh = find_item(a.slug)                     # reload with assets attached
    print(f"\nScheduling drop → {len(sp.drop_assets(fresh))} posts @ {slots}"
          f"{' (DRY RUN — pass --publish)' if not a.publish else ''}")
    sp.schedule_drop(fresh, slots, a.publish, date=a.date)

    print("\n✅ pickup_drop complete")


if __name__ == "__main__":
    main()
