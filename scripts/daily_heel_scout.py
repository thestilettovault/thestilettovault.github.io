# -*- coding: utf-8 -*-
"""
daily_heel_scout.py — The Stiletto Vault 8am scout.

Clean, reliable replacement for the old Pinterest-coupled gothic_scout.
Every morning: gather thin-stiletto heels (Amazon curated pool = right aesthetic +
optional Shopify affiliates), filter to the niche, dedupe against a 10-day sent
log, and send 5 options to Telegram with ✅/❌ buttons.

Run:  py -3 daily_heel_scout.py            # send today's batch
      py -3 daily_heel_scout.py --dry      # print, don't send
"""
import os, sys, json, time, datetime, argparse
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8") if sys.stdout else None
# pythonw (scheduled task) has no console — guard so it runs headless
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
import telegram_sender as ts
from product_scout import is_high_heel, scout_shopify, SHOPIFY_SOURCES

DATA = Path(__file__).resolve().parent.parent / "data"
SENT_LOG = DATA / "heel_sent_log.json"
TAG = "thegothicvaul-20"
NO_REPEAT_DAYS = 10
BATCH = 5

# ── Curated Amazon HIGH-HEELS pool — MULTI-CATEGORY ──
# The store is "high heels", not "gothic": gothic is ONE category among many.
# Every amazon.com/dp earns on our tag, so the pool spans the whole high-heel
# space. Grow it by live WebSearch (amazon.com blocks WebFetch/browser) and drop
# verified ASINs into the matching category. Keep the mix balanced, not goth-only.
AMAZON_POOL = [
    # — Gothic / alt (one category, not the whole store) —
    ("B088DYDY5T", "LISHAN — Lace-Up Gladiator Stiletto, Knee-High Black"),
    ("B0F7LSL3G1", "FancyQueen — Knee-High Gladiator Stiletto, Suede Fringe"),
    ("B0FT2YGHWR", "Foklysp — Studded Spike Pointed-Toe Stiletto Pumps"),
    ("B0GXV38CD7", "Tracieshoes — Thigh-High Gladiator Stiletto Lace-Up"),
    ("B00775OA34", "Pleaser Adore-1020 — 7\" Stiletto Lace-Up Platform"),
    ("B007ST6JUQ", "Pleaser Seduce-1020 — Black Patent Platform Stiletto"),
    ("B09KCGTZDC", "Hbeylia — Sheer Mesh Rhinestone Stiletto Thigh-High Boots"),
    ("B01GA4U2QQ", "SHOW STORY — Punk X-Strap Platform Stiletto Pump Sandals"),
    # — Classic black pointed-toe pump —
    ("B0C33QC8DP", "MSONLYDN — Classic Pointed-Toe Sparkly Stiletto Pump"),
    ("B08F7G1ZCW", "DREAM PAIRS — 4\" Classic Pointed-Toe Stiletto Pump"),
    ("B0DDPVY6KZ", "DEMOSHINE — Black Patent Pointed-Toe Stiletto Pump"),
    # — Strappy evening sandal —
    ("B0GX5NG64G", "Strappy Open-Toe Ankle-Strap Stiletto Sandal, 4.33\""),
    ("B0DDPM7NVS", "Amazon Essentials — Strappy Stiletto Ankle-Strap Sandal"),
    # — Clear / transparent —
    ("B09KR6BNW8", "DREAM PAIRS — Clear Pointed-Toe Transparent Stiletto Pump"),
    ("B0H5QKXN5W", "XINIUNIU — Clear Pointed-Toe Transparent Stiletto Pump"),
    # — Metallic / glitter / red statement —
    ("B0H29ZB7SK", "VOGEL VERE — Glitter Sparkly Pointed-Toe Stiletto Pump"),
    ("B0CB2F7W3W", "MUCCCUTE — Red Metallic Chrome Pointed Stiletto Thigh-High Boots"),
    ("B0BB1ZHBGX", "Red T-Strap Metal-Heel Pointed-Toe Stiletto, 6.3\""),
]


def load_sent():
    if SENT_LOG.exists():
        return json.load(open(SENT_LOG, encoding="utf-8-sig"))
    return {}


def save_sent(d):
    json.dump(d, open(SENT_LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def recently_sent(sent, key):
    ts_str = sent.get(key)
    if not ts_str:
        return False
    try:
        d = datetime.datetime.fromisoformat(ts_str)
        return (datetime.datetime.now() - d).days < NO_REPEAT_DAYS
    except Exception:
        return False


def load_aliexpress_pool():
    """AliExpress heels curated for the morning batch. Earns 6.9% via the Admitad
    deeplink, so our_id is the sentinel 'admitad' (passes the earning gate)."""
    f = DATA / "aliexpress_pool.json"
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data.get("products", []) if isinstance(data, dict) else data
    except Exception:
        return []


def gather():
    """Return candidate heels {url,title,image_url,commission,domain}, niche-filtered."""
    cands = []
    # AliExpress pool (central source, 6.9%). Images can't be auto-fetched — Ofer
    # uploads them in Telegram after ✅; the card is marked accordingly.
    for it in load_aliexpress_pool():
        title = it.get("title", "")
        url = it.get("url", "")
        if url and is_high_heel(title):
            cands.append({
                "url": url, "title": title, "image_url": it.get("image_url", ""),
                "commission": "6.9%", "domain": "aliexpress.com",
                "our_id": "admitad", "key": url,
            })
    # Amazon curated (right aesthetic)
    for asin, title in AMAZON_POOL:
        if is_high_heel(title):
            cands.append({
                "url": f"https://www.amazon.com/dp/{asin}?tag={TAG}",
                "title": title, "image_url": "", "commission": "4%", "domain": "amazon.com",
                "our_id": TAG, "key": asin,
            })
    # Shopify affiliates (reliable images) — only high heels pass the filter.
    # Every registered/verified heel-carrying store, to keep the pool deep enough
    # for a fresh batch every morning (10-day no-repeat window).
    HEEL_SHOPS = ("caperobbin.com", "www.publicdesire.com", "www.simmi.com",
                  "nakedwolfe.com", "www.killstar.com",
                  "www.darkinlove.com", "tukshoes.co.uk")
    for src in SHOPIFY_SOURCES:
        if src["domain"] not in HEEL_SHOPS:
            continue
        try:
            for p in scout_shopify(src):   # scout_shopify already applies is_high_heel
                cands.append({
                    "url": p["url"], "title": p["title"], "image_url": p.get("image", ""),
                    "commission": p["affiliate"].get("commission", ""), "domain": p["domain"],
                    "our_id": p["affiliate"].get("our_id"), "key": p["url"],
                })
        except Exception as e:
            print(f"  shopify {src['domain']} error: {e}")
    return cands


def main(dry=False):
    print(f"\nDaily Heel Scout — {datetime.datetime.now():%Y-%m-%d %H:%M}")
    # Affiliate runs every day EXCEPT Saturday (Sabbath). weekday(): Sat == 5.
    if not dry and datetime.datetime.now().weekday() == 5:
        print("  Saturday — scout paused, no batch today.")
        return
    sent = load_sent()
    cands = gather()
    # dedupe within run + against recent sends + keep only products we actually
    # earn on. "Earning" = an active tracking id (our_id) is configured for the
    # store; a known commission RATE is not enough — without our_id the click is
    # never attributed and no payout lands. Earning today: AliExpress (Admitad
    # deeplink), Amazon (tag), Dark In Love. Awin stores (Public Desire/Simmi/
    # Cape Robbin/Koi/Lamoda) stay hidden until their our_id is filled in.
    seen, fresh, skipped_track = set(), [], 0
    for c in cands:
        if c["key"] in seen or recently_sent(sent, c["key"]):
            continue
        if not str(c.get("our_id") or "").strip():
            skipped_track += 1
            continue
        seen.add(c["key"]); fresh.append(c)
    if skipped_track:
        print(f"  skipped {skipped_track} product(s) with no active tracking (our_id)")
    # Round-robin across stores — AliExpress is gathered first and used to fill
    # the whole batch, so Amazon/Dark In Love never reached Telegram (2026-09-29).
    by_dom = {}
    for c in fresh:
        by_dom.setdefault(c["domain"], []).append(c)
    mixed = []
    while any(by_dom.values()):
        for dom in list(by_dom):
            if by_dom[dom]:
                mixed.append(by_dom[dom].pop(0))
    fresh = mixed
    batch = fresh[:BATCH]
    print(f"  {len(cands)} candidates → {len(fresh)} fresh → sending {len(batch)}")
    if dry:
        for c in batch:
            print(f"   - {c['title'][:55]}")
        return
    if not batch:
        ts.send_text("🤖 סריקת בוקר — אין נעליים חדשות היום (כולן נשלחו לאחרונה).")
        return

    ts.send_text("👠 *The Stiletto Vault — נעל היום*\nאשר ✅ נעל אחת להפקה:")
    ok = 0
    for i, c in enumerate(batch):
        if ts.send_product(url=c["url"], title=c["title"], commission=c["commission"],
                           image_url=c["image_url"], domain=c["domain"]):
            sent[c["key"]] = datetime.datetime.now().isoformat()
            ok += 1
        if i < len(batch) - 1 and c["domain"] == "amazon.com":
            time.sleep(11)   # gentle — avoid Amazon rate-limit
    save_sent(sent)
    ts.send_summary(ok)
    print(f"  sent {ok}/{len(batch)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    main(dry=ap.parse_args().dry)
