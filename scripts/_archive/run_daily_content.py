# -*- coding: utf-8 -*-
"""
run_daily_content.py — the "after approvals" daily job.

Chains the automatable content steps that follow Telegram approval:

  1. Report the Magnific Space queue (products needing variations).
     The actual Space generation is agent/MCP-driven (spaces_*), so this
     step only *reports* what the agent should generate — it does not call MCP.
  2. build_site  — inject approved products into index.html (optionally push).
  3. social_publisher — schedule ready products to TikTok + IG via Postiz.

Morning scan → Telegram approval stays in gothic_scout.py (08:00 task).
This job is the second half; schedule it ~midday, or run on demand.

Usage:
    python run_daily_content.py                 # safe: build site (no push), dry-run social
    python run_daily_content.py --push --publish # live: push site + schedule posts
"""
import sys, os, argparse, subprocess
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8") if sys.stdout else None
SCRIPTS = Path(__file__).resolve().parent
PY = sys.executable  # same interpreter that launched this


def run(step, args):
    print(f"\n{'='*55}\n  {step}\n{'='*55}")
    r = subprocess.run([PY, str(SCRIPTS / step)] + args,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print((r.stdout or "").strip())
    if r.stderr and r.returncode != 0:
        print("STDERR:", r.stderr.strip()[:800])
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="push site live")
    ap.add_argument("--publish", action="store_true", help="schedule social posts for real")
    a = ap.parse_args()

    # 1. Space queue (informational — agent runs the MCP generation)
    run("space_runner.py", ["queue"])

    # 2. Site
    site_args = ["--push"] if a.push else []
    run("build_site.py", site_args)

    # 3. Social
    social_args = ["--publish"] if a.publish else []
    run("social_publisher.py", social_args)

    print(f"\n{'='*55}\n  Daily content job complete\n{'='*55}")


if __name__ == "__main__":
    main()
