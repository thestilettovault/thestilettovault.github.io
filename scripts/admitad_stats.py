# -*- coding: utf-8 -*-
"""
admitad_stats.py — pull real conversions from Admitad, aggregated per subid.

Our site links carry subid=<slug> (build_site.card_html), so each Admitad action
(sale/lead) reports which heel drove it. collect_metrics.sales() imports this;
if anything fails it degrades to the manual fallback there.

Verified 2026-09-02: token scope "statistics" is granted, GET /statistics/actions/
returns 200. Sales attribution starts from links published with a subid onward
(older posts have none).
"""
import os, requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
API = "https://api.admitad.com"


def _token():
    cid = os.getenv("ADMITAD_CLIENT_ID")
    csec = os.getenv("ADMITAD_CLIENT_SECRET")
    if not cid or not csec:
        raise RuntimeError("ADMITAD_CLIENT_ID/SECRET missing")
    r = requests.post(f"{API}/token/", timeout=15, data={
        "grant_type": "client_credentials",
        "client_id": cid, "client_secret": csec, "scope": "statistics"})
    r.raise_for_status()
    return r.json()["access_token"]


def _subid_of(a):
    for k in ("subid", "subid1", "sub_id", "subid2"):
        v = a.get(k)
        if v:
            return v
    return "(untagged)"


# Admitad ad spaces → channel (reference_stiletto_affiliate_accounts: 2984133 IG, 2984134 TikTok, 2984135 site)
WEBSITE_CHANNEL = {"2984133": "instagram", "2984134": "tiktok", "2984135": "site"}


def _channel_of(a):
    w = a.get("website_id")
    if not w and isinstance(a.get("website"), dict):
        w = a["website"].get("id")
    return WEBSITE_CHANNEL.get(str(w or ""), "site")


def fetch_conversions():
    """{total_sales, total_revenue, pending, per_shoe:{subid:{sales,revenue,pending}}}.
    Counts approved+pending actions (revenue from approved); declined ignored."""
    tok = _token()
    hdr = {"Authorization": "Bearer " + tok}
    actions, offset = [], 0
    while True:
        r = requests.get(f"{API}/statistics/actions/", headers=hdr, timeout=20,
                         params={"limit": 500, "offset": offset})
        r.raise_for_status()
        page = r.json().get("results", [])
        actions += page
        if len(page) < 500:
            break
        offset += 500

    per_shoe, total_sales, total_rev, pending = {}, 0, 0.0, 0
    by_channel, commission_all = {}, 0.0
    for a in actions:
        status = (a.get("status") or "").lower()
        if status == "declined":
            continue
        sub = _subid_of(a)
        amt = float(a.get("payment_sum") or a.get("cart") or 0)
        rec = per_shoe.setdefault(sub, {"sales": 0, "revenue": 0.0, "pending": 0})
        rec["sales"] += 1
        if status == "pending":
            rec["pending"] += 1
            pending += 1
        else:
            rec["revenue"] += amt
            total_rev += amt
        total_sales += 1
        commission_all += amt
        ch = by_channel.setdefault(_channel_of(a), {"sales": 0, "commission": 0.0})
        ch["sales"] += 1
        ch["commission"] = round(ch["commission"] + amt, 2)
    for rec in per_shoe.values():
        rec["revenue"] = round(rec["revenue"], 2)
    return {"total_sales": total_sales, "total_revenue": round(total_rev, 2),
            "pending": pending, "per_shoe": per_shoe,
            "by_channel": by_channel, "commission_all": round(commission_all, 2)}


def fetch_clicks(date_start="01.08.2026"):
    """{total_clicks, per_shoe:{subid:clicks}} from /statistics/sub_ids/.
    Clicks with an empty subid (old links / bio) land under "(untagged)"."""
    hdr = {"Authorization": "Bearer " + _token()}
    per_shoe, total, offset = {}, 0, 0
    while True:
        r = requests.get(f"{API}/statistics/sub_ids/", headers=hdr, timeout=20,
                         params={"limit": 500, "offset": offset, "date_start": date_start})
        r.raise_for_status()
        page = r.json().get("results", [])
        for row in page:
            n = int(row.get("clicks") or 0)
            sub = row.get("subid") or "(untagged)"
            per_shoe[sub] = per_shoe.get(sub, 0) + n
            total += n
        if len(page) < 500:
            break
        offset += 500
    return {"total_clicks": total, "per_shoe": per_shoe}


if __name__ == "__main__":
    import json
    print(json.dumps(fetch_conversions(), ensure_ascii=False, indent=2))
    print(json.dumps(fetch_clicks(), ensure_ascii=False, indent=2))
