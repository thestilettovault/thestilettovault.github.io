# -*- coding: utf-8 -*-
"""
space_ui.py — Playwright driver for the Magnific Space UI (free Unlimited).
Built incrementally from real observed interactions → becomes daily_ad_runner.

Usage:
    py -3 space_ui.py open      # open the Space, screenshot login/board state
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
PROFILE    = SCRIPT_DIR.parent / "magnific-profile"
SHOT_DIR   = Path(r"C:\Users\ofera\AppData\Local\Temp\claude\E--BOLD-vault-BOLD-PRODUCTION-THEGOTHICVAULT\71cfe7dd-7140-4be7-87fb-9eff9376ac1f\scratchpad")
SHOT_DIR.mkdir(parents=True, exist_ok=True)

SPACE_URL = "https://www.magnific.com/app/spaces/a2796464-3570-4e02-aa77-65f3f4322d9f"


def open_space():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE), channel="chrome", headless=False,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check",
                  "--disable-blink-features=AutomationControlled"],
            viewport={"width": 1600, "height": 950}, ignore_https_errors=True,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(SPACE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(7000)
        url = page.url
        title = page.title()
        # logged-in heuristics
        logged_out = any(s in url.lower() for s in ("log-in", "login", "signin", "accounts.google"))
        shot = SHOT_DIR / "space_state.png"
        page.screenshot(path=str(shot))
        print(f"URL: {url}")
        print(f"TITLE: {title}")
        print(f"LOGGED_OUT: {logged_out}")
        print(f"SHOT: {shot}")
        ctx.close()


def login(max_wait=270):
    """Open Magnific login; poll until the user completes login, then save session."""
    import time
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE), channel="chrome", headless=False,
            args=["--start-maximized", "--no-first-run", "--no-default-browser-check",
                  "--disable-blink-features=AutomationControlled"],
            viewport={"width": 1600, "height": 950}, ignore_https_errors=True,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://id.magnific.com/log-in?client_id=magnific&lang=en",
                  wait_until="domcontentloaded", timeout=60000)
        print(">>> LOG IN in the window that opened (Google or email). Waiting up to "
              f"{max_wait}s...", flush=True)
        start = time.time()
        ok = False
        while time.time() - start < max_wait:
            page.wait_for_timeout(3000)
            u = page.url.lower()
            if not any(s in u for s in ("log-in", "login", "signin", "accounts.google", "id.magnific")):
                ok = True
                break
        # try to reach the app to confirm session
        page.goto("https://www.magnific.com/app", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        final = page.url.lower()
        logged_in = ok and not any(s in final for s in ("log-in", "login", "signin"))
        print(f"LOGGED_IN: {logged_in}  (final url: {page.url})")
        ctx.close()  # persists session into the profile
        return logged_in


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "open"
    if cmd == "open":
        open_space()
    elif cmd == "login":
        login()
