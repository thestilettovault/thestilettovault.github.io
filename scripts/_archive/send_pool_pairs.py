# -*- coding: utf-8 -*-
"""
send_pool_pairs.py — send N AliExpress heels from the pool to Telegram for review.
Picks products not sent recently, prefers a sane price band, and marks them sent.

Usage:  py -3 send_pool_pairs.py [N]     (default N=2)
"""
import os, sys, json, datetime
from pathlib import Path

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))
import telegram_sender as ts

DATA = Path(__file__).resolve().parent.parent / "data"
POOL = DATA / "aliexpress_pool.json"
SENT = DATA / "pool_sent_log.json"


def _load(p, d):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else d


def main(n=2):
    pool = _load(POOL, {}).get("products", [])
    sent = _load(SENT, {})
    def price_ok(x):
        try:
            return 25 <= float(x.get("price") or 0) <= 110      # sane heel band
        except Exception:
            return True
    fresh = [p for p in pool if p["url"] not in sent and price_ok(p)]
    if len(fresh) < n:
        fresh = [p for p in pool if p["url"] not in sent]        # relax if thin
    batch = fresh[:n]
    if not batch:
        ts.send_text("🤖 אין נעליים חדשות במאגר AliExpress לשליחה.")
        return
    ts.send_text(f"👠 *{len(batch)} זוגות נעליים חדשות* (AliExpress 6.9%). אשר ✅ והעלה תמונות.")
    for p in batch:
        ts.send_product(url=p["url"], title=p["title"],
                        commission=p.get("commission", "6.9%"),
                        image_url=p.get("image_url", ""), domain="aliexpress.com")
        sent[p["url"]] = datetime.datetime.now().isoformat()
    SENT.write_text(json.dumps(sent, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"sent {len(batch)} pairs")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
