# -*- coding: utf-8 -*-
"""
space_runner.py — drive the Magnific Space that generates heel variations.

ARCHITECTURE NOTE
-----------------
The Magnific Space is operated through the *MCP* tools (spaces_add_creations,
spaces_run, spaces_run_status, spaces_show) — those are invoked by the Claude
agent, NOT callable from plain Python. So this module owns the parts that ARE
plain Python:

  • queue     — pick approved products that still need variations
  • stage     — resolve each product's source image → GELEM/<slug>/source.jpg
  • download  — given result URLs from the Space, save them to GELEM/<slug>/
  • mark      — flag catalog items variations_ready = true

The agent glue (run once MCP `spaces_*` is reconnected) is:

    for item in space_runner.queue():
        img = space_runner.stage(item)                      # local file
        # --- MCP calls (agent) ---
        spaces_add_creations(space_id=SPACE_ID, creation_ids=[upload(img)])
        run = spaces_run(space_id=SPACE_ID)
        poll spaces_run_status(run_id=run.id) until complete
        urls = [c.url for c in spaces_show(space_id=SPACE_ID).new_creations]
        # --- back to Python ---
        space_runner.download(item, urls)
        space_runner.mark_ready(item)

Usage (plain-Python parts, runnable now):
    python space_runner.py queue                 # list products needing art
    python space_runner.py stage <slug>          # stage source image
    python space_runner.py download <slug> <url> [<url> ...]
"""
import sys, os, re, json, argparse, urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8") if sys.stdout else None

ROOT         = Path(__file__).resolve().parent.parent
CATALOG_FILE = ROOT / "data" / "approved_catalog.json"
GELEM_DIR    = ROOT / "GELEM"

# The Smart-Heel sales Space we upgraded: "thestilettovault Ad campaign".
# Full pipeline: product photo in → 4 hook shot-concepts → photoshoot angles →
# static ads (with clean negative-space for the deal overlay) → format
# adaptation (1:1 / 4:5 / 9:16) → 9:16 Veo video ad out.
SPACE_ID = "a2796464-3570-4e02-aa77-65f3f4322d9f"
# Entry: the heel source image is uploaded (creations_upload_image) and wired as
# the `reference` of the Campaign image generator via the MCP glue below.
SPACE_INPUT_IMAGE_NODE = "93b85932-6752-4bfa-a801-28fd3c0c097c"  # Campaign image generator
# Outputs we download: the static-ad list (for the deal overlay) and the two
# Veo video-generator nodes (INSTA + TikTok).
SPACE_OUTPUT_ADS_LIST   = "9a64a219-35fa-4dc5-a8d7-c0c67164f134"
SPACE_OUTPUT_VIDEO_INSTA   = "1ecb7df2-1a63-47d2-b4f3-09a75894816c"
SPACE_OUTPUT_VIDEO_TIKTOK  = "bd04349b-fdde-4306-a8d8-cb262b322e96"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def load_catalog():
    if not CATALOG_FILE.exists():
        return []
    with open(CATALOG_FILE, encoding="utf-8-sig") as f:
        return json.load(f)


def save_catalog(catalog):
    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)


def slugify(item):
    url = item.get("url", "")
    # AliExpress /item/<id>.html — id keeps each heel unique (many share the title
    # "Stiletto Heels"); prefix a short label so the GELEM folder stays readable.
    m = re.search(r"/item/(\d+)", url)
    if m:
        label = re.sub(r"[^a-z0-9]+", "-", item.get("title", "heel").lower()).strip("-")[:30]
        slug = f"{label}-{m.group(1)}".strip("-")
        return slug[:60] or m.group(1)
    m = re.search(r"/products/([^/?#]+)", url)   # Shopify (GTHIC / darkinlove / Public Desire / Simmi)
    base = m.group(1) if m else item.get("title", "item")
    # Cap at 45 so the Telegram A/B/C/D pick's callback_data ("adpick|<slug>|A")
    # stays under Telegram's 64-byte limit (long brand handles overflowed it).
    return (re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:45]).strip("-") or "item"


def queue():
    """Approved products that don't yet have generated variations."""
    return [it for it in load_catalog() if not it.get("variations_ready")]


def stage(item):
    """
    Ensure the product's source image sits at GELEM/<slug>/source.jpg so the
    Space (or magnific_producer fallback) can pick it up. Downloads image_url.
    Returns the local path, or None if no source image is available.
    """
    slug = slugify(item)
    folder = GELEM_DIR / slug
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / "source.jpg"
    if dest.exists():
        return dest
    url = item.get("image_url", "")
    if not url:
        print(f"  ! {slug}: no image_url to stage")
        return None
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as r:
            dest.write_bytes(r.read())
        print(f"  staged {slug} → {dest}")
        return dest
    except Exception as e:
        print(f"  ! stage failed for {slug}: {e}")
        return None


def download(item, urls):
    """Save Space result URLs into GELEM/<slug>/var_N.<ext>."""
    slug = slugify(item)
    folder = GELEM_DIR / slug
    folder.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, url in enumerate(urls, 1):
        ext = next((e for e in IMG_EXTS if e in url.lower()), ".jpg")
        dest = folder / f"var_{i}{ext}"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as r:
                dest.write_bytes(r.read())
            saved.append(dest)
            print(f"  saved {dest.name}")
        except Exception as e:
            print(f"  ! download failed ({url[:60]}): {e}")
    return saved


def mark_ready(item):
    catalog = load_catalog()
    for it in catalog:
        if it.get("url") == item.get("url"):
            it["variations_ready"] = True
    save_catalog(catalog)
    print(f"  marked ready: {slugify(item)}")


def _find(slug):
    for it in load_catalog():
        if slugify(it) == slug:
            return it
    return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["queue", "stage", "download"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()

    if a.cmd == "queue":
        q = queue()
        print(f"{len(q)} product(s) need variations:")
        for it in q:
            print(f"  - {slugify(it):40} {it.get('title','')[:40]}")
    elif a.cmd == "stage":
        it = _find(a.args[0]) if a.args else None
        print(stage(it) if it else "slug not found in catalog")
    elif a.cmd == "download":
        it = _find(a.args[0]) if a.args else None
        if it and len(a.args) > 1:
            download(it, a.args[1:]); mark_ready(it)
        else:
            print("usage: download <slug> <url> [<url> ...]")
