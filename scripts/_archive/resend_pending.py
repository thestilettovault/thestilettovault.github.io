"""
resend_pending.py — Resend all pending products to Telegram for approval
Skips products that were already rejected multiple times.
"""
import sys, os, json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from telegram_sender import send_product, send_text
import taste_engine

DATA_DIR     = Path(__file__).parent.parent / "data"
PENDING_FILE = DATA_DIR / "pending_reviews.json"
REJECT_FILE  = DATA_DIR / "rejected_profile.json"

def get_rejected_urls():
    if not REJECT_FILE.exists():
        return set()
    data = json.loads(REJECT_FILE.read_text(encoding="utf-8"))
    return {r["link"] for r in data.get("rejected", [])}

def main():
    if not PENDING_FILE.exists():
        print("No pending file found.")
        return

    pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    rejected_urls = get_rejected_urls()

    to_send = []
    for pid, item in pending.items():
        url = item.get("url", "")
        title = item.get("title", url)

        # Skip if rejected before
        if url in rejected_urls:
            print(f"SKIP (rejected): {title[:60]}")
            continue

        to_send.append((pid, item))

    if not to_send:
        print("Nothing to resend.")
        return

    send_text(f"🔄 *שולח מחדש {len(to_send)} מוצרים שממתינים לאישורך*\nלחץ ✅ כן / ❌ לא על כל מוצר")

    import time
    sent = 0
    for pid, item in to_send:
        url        = item.get("url", "")
        title      = item.get("title", url)
        image_url  = item.get("image_url", "")
        commission = item.get("commission", "")
        domain     = taste_engine.get_domain(url)

        print(f"Sending: {title[:70]}")
        ok = send_product(
            url=url,
            title=title,
            commission=commission,
            image_url=image_url,
            domain=domain,
        )
        if ok:
            sent += 1
            print(f"  ✅ sent")
        else:
            print(f"  ❌ failed")
        time.sleep(1.5)

    print(f"\nסיום. {sent}/{len(to_send)} נשלחו.")

if __name__ == "__main__":
    main()
