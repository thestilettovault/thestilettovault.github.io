# -*- coding: utf-8 -*-
"""
heel_hunter.py — daily brand + affiliate discovery for The Stiletto Vault.

Deterministic half of the /heel-hunter agent (the Claude run in heel_hunter.md
does the web/TikTok research and calls these commands):

    py -3 heel_hunter.py probe <domain>            # detect Shopify, affiliate page, network, %, avg heel $
    py -3 heel_hunter.py add <domain> [--note ..]  # probe + upsert into data/affiliate_registry.json
    py -3 heel_hunter.py trend "<name>" <views> <tiktok_url> [<domain>]   # log today's trend
    py -3 heel_hunter.py activate                  # read "aff <domain> <link>" msgs from tg_inbox → our_id
    py -3 heel_hunter.py cards                     # Telegram signup card per worthwhile unregistered brand
    py -3 heel_hunter.py report                    # one daily summary message
    py -3 heel_hunter.py list

Registration itself is ALWAYS done by Ofer (account creation / payment details
are never automated). The card gives him the link + a pre-written form kit, and
he pastes the approved tracking link back as:  aff nakedwolfe.com https://...?ref=XYZ

Registry entry (data/affiliate_registry.json -> {"brands": {domain: {...}}}):
    status   : active | to_register | carded | no_program | network_blocked
    program  : Direct/SocialSnowball/UpPromote/GoAffPro/Refersion/Awin/TradeTracker/...
    commission (float %), avg_price (USD-ish), value_per_sale, signup_url,
    our_id, affiliate_ref (query suffix appended to product URLs), shopify (bool)
"""
import os, re, sys, json, html, datetime, argparse
from pathlib import Path
from urllib.parse import urlparse

# Niche config (niches/<active>/niche.json, editable in the Control Center → Tuning).
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from control.niche import cfg as _cfg
except Exception:
    def _cfg(_path, default=None):
        return default

import requests

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(__file__))

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REG = DATA / "affiliate_registry.json"
TRENDS = DATA / "trends.json"
INBOX = Path(__file__).resolve().parent / "tg_inbox.jsonl"
KIT = DATA / "affiliate_form_kit.md"

MIN_VALUE = _cfg("thresholds.MIN_VALUE", 5.0)          # $ per sale (commission% × avg heel price) to earn a signup card
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"}

AFF_PATHS = ["pages/affiliate-program", "pages/affiliates", "pages/affiliate",
             "pages/affiliate-programme", "pages/affiliate-page", "pages/ambassador",
             "pages/partners", "pages/collab-with-us"]
NETWORKS = [  # (regex on page html, program name, is_network_with_site_review)
    (r"socialsnowball", "SocialSnowball", False),
    (r"uppromote|secomapp", "UpPromote", False),
    (r"goaffpro", "GoAffPro", False),
    (r"refersion", "Refersion", False),
    (r"collabs\.shopify|shopify collabs", "ShopifyCollabs", False),
    (r"leaddyno|tapfiliate|linkmink|getrewardful", "Direct", False),
    (r"awin\.com|awin1\.com", "Awin", True),
    (r"shareasale", "ShareASale", True),
    (r"tradetracker", "TradeTracker", True),
    (r"rakuten|linksynergy", "Rakuten", True),
    (r"impact\.com|impactradius", "Impact", True),
    (r"cj\.com|commission junction", "CJ", True),
    (r"partnerize|prf\.hn", "Partnerize", True),
]
HEEL_WORDS = re.compile(r"(?i)stiletto|heel|pump|platform|slingback|thigh.high|knee.high")


# ── registry io ──────────────────────────────────────────────────────
def _load(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_reg():
    return _load(REG, {"brands": {}})


def save_reg(reg):
    REG.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def norm(domain):
    d = domain.strip().lower()
    if "://" in d:
        d = urlparse(d).netloc
    return d.removeprefix("www.").strip("/")


# ── probing ──────────────────────────────────────────────────────────
def _get(url, timeout=15):
    try:
        r = requests.get(url, headers=UA, timeout=timeout, allow_redirects=True)
        return r
    except Exception:
        return None


def _text(h):
    h = re.sub(r"(?s)<(script|style).*?</\1>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))


def heel_prices(domain):
    """Median price of heel products via public Shopify products.json. None if not Shopify."""
    for host in (f"https://www.{domain}", f"https://{domain}"):
        r = _get(f"{host}/products.json?limit=250")
        if r is None or r.status_code != 200 or '"products"' not in r.text[:200]:
            continue
        prices = []
        for p in r.json().get("products", []):
            if not HEEL_WORDS.search(f"{p.get('title','')} {p.get('product_type','')} {' '.join(p.get('tags',[]) if isinstance(p.get('tags'), list) else [str(p.get('tags',''))])}"):
                continue
            try:
                prices.append(float((p.get("variants") or [{}])[0].get("price") or 0))
            except ValueError:
                pass
        prices = sorted(x for x in prices if x > 0)
        return (prices[len(prices) // 2] if prices else 0.0), len(prices), host
    return None, 0, f"https://www.{domain}"


def probe(domain):
    domain = norm(domain)
    avg, n_heels, host = heel_prices(domain)
    info = {"domain": domain, "shopify": avg is not None, "avg_price": round(avg or 0, 2),
            "heel_count": n_heels, "program": None, "network": False,
            "commission": None, "signup_url": None, "requirements": ""}
    home = _get(host + "/")
    pages = []
    if home is not None and home.ok:
        for m in re.finditer(r'href="([^"]*(?:affiliat|ambassador|partner)[^"]*)"', home.text, re.I):
            u = m.group(1)
            pages.append(u if u.startswith("http") else host + "/" + u.lstrip("/"))
    pages += [f"{host}/{p}" for p in AFF_PATHS]
    seen = set()
    for url in pages:
        if url in seen:
            continue
        seen.add(url)
        r = _get(url)
        if r is None or r.status_code != 200 or r.url.rstrip("/") == host.rstrip("/"):
            continue
        body = r.text
        txt = _text(body)
        if not re.search(r"(?i)affiliat|commission|ambassador", txt):
            continue
        info["signup_url"] = r.url
        for rx, name, is_net in NETWORKS:
            if re.search(rx, body, re.I):
                info["program"], info["network"] = name, is_net
                break
        info["program"] = info["program"] or "Direct"
        m = re.search(r"(\d{1,2}(?:\.\d)?)\s?%\s*(?:commission|on every|per sale|of every|of each)", txt, re.I) \
            or re.search(r"commission[^.%]{0,60}?(\d{1,2}(?:\.\d)?)\s?%", txt, re.I)
        if m:
            info["commission"] = float(m.group(1))
        req = re.search(r"(?i)[^.]{0,80}(?:must|eligible|require|followers|made a purchase)[^.]{0,120}\.", txt)
        info["requirements"] = req.group(0).strip()[:220] if req else ""
        signup = re.search(r'https?://[^"\'\s<>]*(?:socialsnowball|uppromote|goaffpro|refersion|awin\.com|tradetracker|shareasale)[^"\'\s<>]*', body, re.I)
        if signup:
            info["signup_link"] = signup.group(0)
        break
    return info


def value_per_sale(e):
    c = e.get("commission")
    if c is None:
        c = 8.0 if e.get("program") else 0.0   # unknown rate on a real program → assume typical 8%
    return round((c / 100) * (e.get("avg_price") or 0), 2)


def upsert(domain, note=""):
    reg = load_reg()
    info = probe(domain)
    d = info["domain"]
    old = reg["brands"].get(d, {})
    e = {**old, **{k: v for k, v in info.items() if v not in (None, "")}}
    if old.get("our_id"):
        e["status"] = "active"
    elif not e.get("program"):
        e["status"] = "no_program"
    elif old.get("status") in ("carded",):
        e["status"] = old["status"]
    else:
        e["status"] = "to_register"
    e["value_per_sale"] = value_per_sale(e)
    e["updated"] = datetime.date.today().isoformat()
    if note:
        e["note"] = note
    reg["brands"][d] = e
    save_reg(reg)
    return e


# ── trends ───────────────────────────────────────────────────────────
def add_trend(name, views, url, domain=""):
    t = _load(TRENDS, [])
    reg = load_reg()["brands"]
    d = norm(domain) if domain else ""
    status = reg.get(d, {}).get("status", "unknown") if d else "unknown"
    t.append({"date": datetime.date.today().isoformat(), "name": name, "views": views,
              "url": url, "domain": d, "affiliate_status": status})
    TRENDS.write_text(json.dumps(t[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
    return status


def todays_trends():
    today = datetime.date.today().isoformat()
    return [x for x in _load(TRENDS, []) if x["date"] == today]


# ── activation from Telegram inbox ──────────────────────────────────
AFF_RE = re.compile(r"^\s*aff\s+(\S+)\s+(\S+)", re.I)


def activate_one(domain, link):
    """Activate a single brand with its approved tracking link. Mutates and
    saves the registry; returns the updated entry. Shared by the Telegram
    inbox flow (activate()) and the control-center API."""
    reg = load_reg()
    d = norm(domain)
    e = reg["brands"].setdefault(d, {"domain": d})
    q = urlparse(link).query
    e.update(our_id=link, status="active",
             affiliate_ref=("?" + q) if q else "",
             activated=datetime.date.today().isoformat())
    save_reg(reg)
    return e


def activate():
    reg = load_reg()
    done = []
    if not INBOX.exists():
        return done
    for line in INBOX.read_text(encoding="utf-8").splitlines():
        try:
            m = AFF_RE.match(json.loads(line).get("text", ""))
        except Exception:
            continue
        if not m:
            continue
        d, link = norm(m.group(1)), m.group(2)
        e = reg["brands"].get(norm(d), {})
        if e.get("our_id") == link:
            continue
        activate_one(d, link)
        reg = load_reg()  # refresh after activate_one's own save
        done.append(norm(d))
    return done


def active_sources():
    """Registry brands as product_scout-style Shopify sources (used by daily_heel_scout)."""
    out = []
    for d, e in load_reg()["brands"].items():
        if e.get("status") == "active" and e.get("shopify"):
            out.append({"domain": "www." + d if e.get("www", True) else d,
                        "collections": ["heels", "high-heels", "new-in", "new-arrivals", "all"],
                        "affiliate": {"commission": f"{e.get('commission') or '?'}%",
                                      "program": e.get("program"), "our_id": e.get("our_id")},
                        "affiliate_ref": e.get("affiliate_ref", ""),
                        "max_per_collection": 10})
    return out


# ── telegram ─────────────────────────────────────────────────────────
def _send(text):
    import telegram_sender as ts
    ts.send_text(text, parse_mode=None)


def cards():
    reg = load_reg()
    trends = {x["domain"]: x for x in todays_trends() if x.get("domain")}
    sent = 0
    for d, e in sorted(reg["brands"].items(), key=lambda kv: -kv[1].get("value_per_sale", 0)):
        if e.get("status") != "to_register" or e.get("value_per_sale", 0) < MIN_VALUE:
            continue
        t = trends.get(d)
        lines = [f"🟡 הרשמה לשותפים: {d}",
                 f"💰 {e.get('commission') or '~8?'}% × ${e.get('avg_price')} ≈ ${e['value_per_sale']} למכירה"
                 f" · {e.get('heel_count', 0)} עקבים",
                 f"🏷 {e.get('program')}" + (" (רשת — בודקת אתר)" if e.get("network") else " (ישיר)")]
        if t:
            lines.append(f"🔥 טרנד היום: {t['name']} · {t['views']} צפיות")
        if e.get("requirements"):
            lines.append(f"⚠️ {e['requirements']}")
        lines += [f"🔗 {e.get('signup_link') or e.get('signup_url')}",
                  "📋 טקסטים לטופס: data/affiliate_form_kit.md",
                  f"אחרי אישור שלח לי:  aff {d} <הלינק שקיבלת>"]
        _send("\n".join(lines))
        e["status"] = "carded"
        e["carded"] = datetime.date.today().isoformat()
        sent += 1
    save_reg(reg)
    return sent


def report(activated=()):
    b = load_reg()["brands"]
    by = {}
    for e in b.values():
        by.setdefault(e.get("status"), []).append(e["domain"])
    tr = todays_trends()
    lines = ["🕵️ Heel Hunter — דוח יומי"]
    if tr:
        lines.append("🔥 טרנדים היום:")
        for x in tr[:5]:
            mark = {"active": "✅", "to_register": "🟡", "carded": "🟡", "no_program": "❌"}.get(x["affiliate_status"], "❔")
            lines.append(f"  {mark} {x['name']} · {x['views']} · {x['domain'] or 'מותג לא זוהה'}")
    if activated:
        lines.append("✅ הופעלו היום: " + ", ".join(activated))
    lines.append(f"✅ פעילים: {len(by.get('active', []))} · 🟡 ממתינים להרשמה: "
                 f"{len(by.get('carded', [])) + len(by.get('to_register', []))} · ❌ בלי תוכנית: {len(by.get('no_program', []))}")
    _send("\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["probe", "add", "trend", "activate", "cards", "report", "list"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    if a.cmd == "probe":
        print(json.dumps(probe(a.args[0]), ensure_ascii=False, indent=2))
    elif a.cmd == "add":
        print(json.dumps(upsert(a.args[0], a.note), ensure_ascii=False, indent=2))
    elif a.cmd == "trend":
        print(add_trend(*a.args[:4]))
    elif a.cmd == "activate":
        print(activate())
    elif a.cmd == "cards":
        print(f"cards sent: {cards()}")
    elif a.cmd == "report":
        report(a.args)
    elif a.cmd == "list":
        for d, e in sorted(load_reg()["brands"].items()):
            print(f"{e.get('status',''):12} ${e.get('value_per_sale',0):>6}  {e.get('program') or '-':15} {d}")
