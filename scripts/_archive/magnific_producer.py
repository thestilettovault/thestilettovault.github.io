# -*- coding: utf-8 -*-
"""
Magnific Producer — TheGothicVault
Autonomous video/image generator using Magnific AI (magnific.com).

First run:  python magnific_producer.py --login
            Browser opens visibly — log in manually, then close.
            Session saved to magnific-profile\ for all future runs.

Normal run: python magnific_producer.py
            Fully headless. Generates all products, downloads to GELEM\.

Usage:
    python magnific_producer.py            # generate all products
    python magnific_producer.py --login    # first-time login setup
    python magnific_producer.py BW166      # generate single product by folder prefix
"""

import os
import sys
import time
import shutil
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
PROFILE_DIR = SCRIPT_DIR.parent / "magnific-profile"
GELEM_DIR   = SCRIPT_DIR.parent / "GELEM"
DOWNLOAD_DIR = GELEM_DIR  # generated files land here per-product

MAGNIFIC_VIDEO_URL = "https://www.magnific.com/app/ai-video-generator"
MAGNIFIC_IMAGE_URL = "https://www.magnific.com/app/ai-image-generator"

# ── Products ──────────────────────────────────────────────────────────────────
PRODUCTS = [
    # ── BW166 T2I — generate reference frame FIRST, then use best as I2V start image ──
    {
        "id":     "BW166-T2I-A",
        "folder": "BW166-punk-leather-cape",
        "image":  "BW166__001.jpg",           # product-only flat — cleanest silhouette ref
        "image2": "BW166__100.jpg",           # styled 3/4 view — secondary ref
        "type":   "image",
        "model":  "Seedream 5 Lite",
        "prompt": (
            "Gothic fashion product shot matching reference images exactly. 3/4 angle view from cape/sleeve side. "
            "Asymmetric black PU leather shoulder cape — one structured angular shoulder with high standing collar "
            "and lace-through silver eyelets, single long puffed leather sleeve tapering to dramatic pointed cuff "
            "with D-ring hardware, opposite shoulder completely bare. Black woven harness straps cross the chest "
            "in X formation with silver metal buckles. "
            "Garment only — no person, no face, no body — floating on invisible form against pure black background. "
            "Cold blue hard key light from 45 degrees left — rakes across leather folds creating sharp specular "
            "highlights on raised surfaces and deep shadow on opposite side. Right side near-total darkness. "
            "Deep blacks, film grain, gothic dystopian fashion editorial, cinematic depth of field, "
            "shallow focus on hardware detail. "
            "Constraints: Black PU leather stays deep matte black throughout — no warm brown or amber cast. "
            "Silver hardware stays cool chrome. No person. No face. No background elements."
        ),
    },
    {
        "id":     "BW166-T2I-B",
        "folder": "BW166-punk-leather-cape",
        "image":  "BW166__001.jpg",
        "image2": "BW166__100.jpg",
        "type":   "image",
        "model":  "Nano Banana 2",
        "prompt": (
            "Gothic fashion product shot matching reference images exactly. 3/4 angle view from cape/sleeve side. "
            "Asymmetric black PU leather shoulder cape — one structured angular shoulder with high standing collar "
            "and lace-through silver eyelets, single long puffed leather sleeve tapering to dramatic pointed cuff "
            "with D-ring hardware, opposite shoulder completely bare. Black woven harness straps cross the chest "
            "in X formation with silver metal buckles. "
            "Garment only — no person, no face, no body — floating on invisible form against pure black background. "
            "Cold blue hard key light from 45 degrees left — rakes across leather folds creating sharp specular "
            "highlights on raised surfaces and deep shadow on opposite side. Right side near-total darkness. "
            "Deep blacks, film grain, gothic dystopian fashion editorial, cinematic depth of field, "
            "shallow focus on hardware detail. "
            "Constraints: Black PU leather stays deep matte black throughout — no warm brown or amber cast. "
            "Silver hardware stays cool chrome. No person. No face. No background elements."
        ),
    },
    # ── BW166 I2V — run AFTER picking best T2I frame as start image ──
    {
        "id":     "BW166-I2V-SHOT1-A",
        "folder": "BW166-punk-leather-cape",
        "image":  "BW166_t2i_winner.jpg",    # replace with best T2I output
        "type":   "video",
        "model":  "Kling 2.5",
        "prompt": (
            "Starting from the provided reference image as the first frame. "
            "Asymmetric black PU leather shoulder cape floating on invisible form. "
            "Garment holds its architectural shape against pure black background. "
            "Harness straps carry faint sway beginning at 2 seconds. At 2 seconds, camera begins "
            "slow 10 degree arc left — deepening the asymmetric reveal, one-armed side vs completely bare side. "
            "Camera: slow 10 degree arc left, wide shot, smooth rotation. "
            "Style: Cinematic. Cold blue hard key light fixed 45 degrees left. Deep shadow right side. "
            "Pure black background. Film grain. Gothic dystopian fashion editorial. "
            "Constraints: Black PU leather stays deep matte black throughout — no warm color shift, "
            "no brown or amber cast on the leather. Silver hardware stays cool chrome. "
            "No person. No face. No body. Smooth arc movement, no jitter. No flickering textures."
        ),
    },
    {
        "id":     "BW166-I2V-SHOT1-B",
        "folder": "BW166-punk-leather-cape",
        "image":  "BW166_t2i_winner.jpg",    # replace with best T2I output
        "type":   "video",
        "model":  "MiniMax Hailuo 2.3",
        "prompt": (
            "Starting from the provided reference image as the first frame. "
            "Asymmetric black PU leather shoulder cape floating on invisible form. "
            "Garment holds its architectural shape against pure black background. "
            "Harness straps carry faint sway beginning at 2 seconds. At 2 seconds, camera begins "
            "slow 10 degree arc left — deepening the asymmetric reveal, one-armed side vs completely bare side. "
            "Camera: slow 10 degree arc left, wide shot, smooth rotation. "
            "Style: Cinematic. Cold blue hard key light fixed 45 degrees left. Deep shadow right side. "
            "Pure black background. Film grain. Gothic dystopian fashion editorial. "
            "Constraints: Black PU leather stays deep matte black throughout — no warm color shift, "
            "no brown or amber cast on the leather. Silver hardware stays cool chrome. "
            "No person. No face. No body. Smooth arc movement, no jitter. No flickering textures."
        ),
    },
    # ── BW108 — prompts updated per director workflow ──
    {
        "id":     "BW108-T2I-A",
        "folder": "BW108-cat-haunt-zipper-top",
        "image":  "BW108__102.jpg",
        "type":   "image",
        "model":  "Seedream 5 Lite",
        "prompt": (
            "Gothic fashion product shot matching reference image exactly. Front view. "
            "Black alternative zipper crop top with cat ear hood graphic and pink lace fringe trim. "
            "Central metal zipper pull, puff sleeves with lace cuffs. "
            "Garment only — no person, no face, no body — floating on invisible form against pure black background. "
            "Cold blue key light from above. Deep black background. Faint cold mist rising from below. "
            "Deep blacks, film grain, gothic fashion editorial, cinematic depth of field. "
            "Constraints: Black fabric stays deep matte black throughout — no warm color shift. "
            "No person. No face. No background elements not in reference."
        ),
    },
    {
        "id":     "BW108-T2I-B",
        "folder": "BW108-cat-haunt-zipper-top",
        "image":  "BW108__102.jpg",
        "type":   "image",
        "model":  "Nano Banana 2",
        "prompt": (
            "Gothic fashion product shot matching reference image exactly. Front view. "
            "Black alternative zipper crop top with cat ear hood graphic and pink lace fringe trim. "
            "Central metal zipper pull, puff sleeves with lace cuffs. "
            "Garment only — no person, no face, no body — floating on invisible form against pure black background. "
            "Cold blue key light from above. Deep black background. Faint cold mist rising from below. "
            "Deep blacks, film grain, gothic fashion editorial, cinematic depth of field. "
            "Constraints: Black fabric stays deep matte black throughout — no warm color shift. "
            "No person. No face. No background elements not in reference."
        ),
    },
    # ── DW518 — SOLD OUT as of 2026-05-12 — skip until restocked ──
    # {
    #     "id":     "DW518",
    #     "folder": "DW518-angel-wing-doll-dress",
    #     ...
    # },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg):
    print(f"  {msg}", flush=True)


def wait_for_login(page):
    """Wait until user is logged in (checks for user avatar / account menu)."""
    log("Waiting for login...")
    try:
        # Magnific shows a user icon / avatar when logged in
        page.wait_for_selector("img[src*='lh3.googleusercontent'], [data-testid='user-menu'], .user-avatar, [aria-label*='account']", timeout=120_000)
        log("Logged in OK")
        return True
    except PWTimeout:
        log("Login timeout — please log in within 2 minutes")
        return False


def select_model(page, model_name: str):
    """Click the model selector and choose the target model."""
    try:
        # Find the model dropdown button (shows current model name)
        model_btn = page.locator("button").filter(has_text=model_name).first
        if model_btn.count() == 0:
            # Try clicking the current model display to open dropdown
            page.locator("[class*='model'], [class*='Model']").first.click()
            page.wait_for_timeout(800)
            # Then find and click the target model in the list
            page.locator("li, [role='option'], [class*='item']").filter(has_text=model_name).first.click()
        else:
            log(f"Model already set to {model_name}")
        page.wait_for_timeout(500)
    except Exception as e:
        log(f"Model selection warning: {e} — continuing with current model")


def set_prompt(page, prompt_text: str):
    """Clear and fill the prompt textarea."""
    textarea = page.locator("textarea").first
    textarea.click()
    textarea.select_all() if hasattr(textarea, "select_all") else page.keyboard.press("Control+a")
    textarea.fill(prompt_text)
    log(f"Prompt set ({len(prompt_text)} chars)")


def upload_reference_image(page, image_path: str):
    """Upload a product image as reference/start image."""
    if not Path(image_path).exists():
        log(f"Image not found: {image_path} — skipping upload")
        return False

    try:
        # Look for file input or drop zone
        file_input = page.locator("input[type='file']").first
        if file_input.count() > 0:
            file_input.set_input_files(image_path)
            log(f"Uploaded: {Path(image_path).name}")
            page.wait_for_timeout(2000)
            return True

        # Try clicking the "Add media" / references button to reveal input
        add_btn = page.locator("button, label").filter(has_text_re="Add media|Start image|Reference|\\+").first
        add_btn.click()
        page.wait_for_timeout(500)
        file_input = page.locator("input[type='file']").first
        file_input.set_input_files(image_path)
        log(f"Uploaded via Add button: {Path(image_path).name}")
        page.wait_for_timeout(2000)
        return True

    except Exception as e:
        log(f"Upload warning: {e} — continuing without reference image")
        return False


def click_generate(page):
    """Click the Generate button."""
    btn = page.locator("button").filter(has_text="Generate").first
    btn.click()
    log("Generate clicked")


def wait_for_completion(page, timeout_minutes=5):
    """
    Wait for the generation to finish.
    Magnific shows a progress bar then reveals the completed item.
    Returns True when done.
    """
    log(f"Waiting for generation (max {timeout_minutes} min)...")
    timeout_ms = timeout_minutes * 60 * 1000

    try:
        # Wait for the result card to appear in the creation feed
        # Magnific adds items with download buttons or video/image elements
        page.wait_for_selector(
            "video[src], a[download], button[aria-label*='download'], button[aria-label*='Download'], [class*='result'] video, [class*='creation'] video",
            timeout=timeout_ms
        )
        log("Generation complete!")
        page.wait_for_timeout(1500)  # let UI settle
        return True
    except PWTimeout:
        log("Generation timed out — taking screenshot for debug")
        page.screenshot(path=str(SCRIPT_DIR / "debug_timeout.png"))
        return False


def download_result(page, product: dict):
    """Download the most recently generated file."""
    output_dir = GELEM_DIR / product["folder"]
    output_dir.mkdir(parents=True, exist_ok=True)

    ext = "mp4" if product["type"] == "video" else "jpg"
    filename = f"{product['id']}_generated.{ext}"
    output_path = output_dir / filename

    try:
        with page.expect_download(timeout=30_000) as dl_info:
            # Try download button
            dl_btn = page.locator(
                "a[download], button[aria-label*='download'], button[aria-label*='Download'], "
                "[class*='download']"
            ).first
            dl_btn.click()

        download = dl_info.value
        download.save_as(str(output_path))
        log(f"Saved: {output_path}")
        return str(output_path)

    except Exception as e:
        log(f"Download button failed: {e}")

        # Fallback: grab video src directly
        try:
            video_src = page.locator("video").first.get_attribute("src")
            if video_src and video_src.startswith("http"):
                import urllib.request
                urllib.request.urlretrieve(video_src, str(output_path))
                log(f"Saved via src: {output_path}")
                return str(output_path)
        except Exception as e2:
            log(f"Fallback download failed: {e2}")

    return None


# ── Core runner ────────────────────────────────────────────────────────────────

def run_product(page, product: dict):
    print(f"\n{'='*55}")
    print(f"  Product: {product['id']} — {product['folder']}")
    print(f"  Type:    {product['type']} | Model: {product['model']}")
    print(f"{'='*55}")

    url = MAGNIFIC_VIDEO_URL if product["type"] == "video" else MAGNIFIC_IMAGE_URL
    log(f"Navigating to: {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(3000)
    log(f"Page loaded: {page.url}")

    # 1. Select model
    select_model(page, product["model"])

    # 2. Upload reference image
    image_path = str(GELEM_DIR / product["folder"] / product["image"])
    upload_reference_image(page, image_path)

    # 3. Set prompt
    set_prompt(page, product["prompt"])

    # 4. Generate
    click_generate(page)

    # 5. Wait
    done = wait_for_completion(page, timeout_minutes=6)
    if not done:
        log(f"SKIPPED download for {product['id']} (timeout)")
        return None

    # 6. Download
    result = download_result(page, product)
    return result


def main():
    args = sys.argv[1:]
    login_mode = "--login" in args
    filter_id  = next((a for a in args if not a.startswith("--")), None)

    products = PRODUCTS
    if filter_id:
        products = [p for p in PRODUCTS if filter_id.upper() in p["id"].upper()]
        if not products:
            print(f"No product found matching '{filter_id}'")
            sys.exit(1)

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "="*55)
    print("  Magnific Producer — TheGothicVault")
    print("="*55)
    print(f"  Mode:     {'LOGIN SETUP' if login_mode else 'AUTO GENERATE'}")
    print(f"  Products: {len(products)}")
    print(f"  Profile:  {PROFILE_DIR}")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE_DIR),          # dedicated profile — never conflicts with your Chrome
            channel="chrome",          # use real Chrome for Google OAuth compatibility
            headless=False,
            args=[
                "--start-maximized",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
            ],
            viewport={"width": 1400, "height": 900},
            ignore_https_errors=True,
        )

        page = ctx.new_page()

        # Navigate to Magnific home first
        log("Navigating to Magnific...")
        page.goto("https://www.magnific.com/app", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(2000)
        log(f"Current URL: {page.url}")

        # Login mode
        if login_mode:
            print("\n  Browser is open — please log in to Magnific.")
            print("  When logged in and on the main page, press ENTER here to save session.")
            input()
            ctx.close()
            print("  Session saved. Run without --login for automated generation.")
            return

        # Check if logged in
        if "login" in page.url.lower() or "signin" in page.url.lower() or "accounts" in page.url.lower():
            print("\n  Not logged in. Run with --login first:")
            print("  python magnific_producer.py --login")
            ctx.close()
            sys.exit(1)

        log("Session active — starting generation pipeline")

        results = []
        for product in products:
            try:
                result = run_product(page, product)
                results.append({"id": product["id"], "file": result, "ok": result is not None})
            except Exception as e:
                log(f"ERROR on {product['id']}: {e}")
                page.screenshot(path=str(SCRIPT_DIR / f"debug_{product['id']}.png"))
                results.append({"id": product["id"], "file": None, "ok": False})

        ctx.close()

    print(f"\n{'='*55}")
    print("  DONE")
    print(f"{'='*55}")
    for r in results:
        status = "OK " if r["ok"] else "FAIL"
        print(f"  [{status}] {r['id']} — {r['file'] or 'failed'}")


if __name__ == "__main__":
    main()
