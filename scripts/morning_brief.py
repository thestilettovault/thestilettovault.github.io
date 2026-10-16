"""Morning brief: ONE short Hebrew Telegram message — what needs Ofer today, and did anything break.

    py -3 scripts/morning_brief.py           # dry run: print the brief
    py -3 scripts/morning_brief.py --send    # send via Telegram, then roll the day-over-day snapshot
    py -3 scripts/morning_brief.py --json    # structured data (for Mia)

Every source is optional: a failing source adds one "⚠️ <source> לא זמין" line and the brief is still built.
GET-only against Zernio. The snapshot (data/brief_state.json) moves only after a successful send.
"""
import sys, re, json, time, argparse, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from control.niche import cfg as _cfg
except Exception:
    def _cfg(_p, default=None):
        return default

import jsonio

DATA = ROOT / "data"
STATE = DATA / "brief_state.json"
STUCK_MIN = 30
STALE_DAYS = 5
MISSED_RUN_H = 26
ERR_PAT = re.compile(r"^(!|Traceback|⚠)|scheduling failed|publishing failed")
ACTION = {"board_ready": "ללחוץ Run באפליקציית Magnific ואז על הכפתור בטלגרם",
          "awaiting_choice": "לבחור A/B/C/D בטלגרם"}
PLAT = {"instagram": "IG", "tiktok": "TT", "pinterest": "PIN", "facebook": "FB", "youtube": "YT"}


def _tz():
    name = _cfg("identity.timezone", "Asia/Jerusalem") or "Asia/Jerusalem"
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return datetime.timezone(datetime.timedelta(hours=2))


def _parse_iso(s, tz):
    try:
        d = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=datetime.timezone.utc)
        return d.astimezone(tz)
    except Exception:
        return None


def _slug(key):
    return str(key).split("/")[-1]


# ---------------------------------------------------------------- sources
def src_needs(now):
    """-> [(slug, what)]: board_ready / awaiting_choice / collecting stuck > 30 min."""
    out = []
    st = jsonio.load(DATA / "orchestrator_state.json", {})
    for k, v in st.items():
        if str(k).startswith("_") or not isinstance(v, dict):
            continue
        s = v.get("status")
        if s in ACTION:
            out.append((_slug(k), ACTION[s]))
        elif s == "collecting":
            ts = v.get("ts") or v.get("started_ts") or 0
            if ts and now.timestamp() - float(ts) > STUCK_MIN * 60:
                out.append((_slug(k), f"תקוע ב-collecting מעל {STUCK_MIN} דק׳ — לבדוק"))
    return out


def src_queue(now, tz):
    q = jsonio.load(DATA / "production_queue.json", [])
    counts, stale = {}, []
    for x in q:
        s = x.get("status") or "?"
        counts[s] = counts.get(s, 0) + 1
        if s == "approved":
            d = _parse_iso(x.get("approved_ts"), tz)
            if d is not None and d.tzinfo is not None and (now - d).days > STALE_DAYS:
                stale.append(_slug(x.get("local_asset") or x.get("title") or "?"))
    return {"counts": counts, "stale": stale}


def src_posts(now, tz):
    from control import services
    posts = services.zernio_all_posts()
    today, yday = now.date(), (now - datetime.timedelta(days=1)).date()
    sched, failed, pub_y = [], [], 0
    for p in posts:
        status = p.get("status")
        when = _parse_iso(p.get("scheduledFor"), tz)
        pls = [(pl or {}).get("platform", "?") for pl in (p.get("platforms") or [])] or ["?"]
        if status == "scheduled" and when and when.date() == today:
            sched.append({"time": when.strftime("%H:%M"), "platforms": pls})
        pub = _parse_iso(p.get("publishedAt"), tz) or when
        if status == "published" and pub and pub.date() == yday:
            pub_y += 1
        if status == "failed":
            ref = _parse_iso(p.get("updatedAt"), tz) or when
            if ref and (now - ref).days < 3:
                failed.append({"time": ref.strftime("%d/%m %H:%M"), "platforms": pls,
                               "title": (p.get("content") or "")[:30]})
    sched.sort(key=lambda r: r["time"])
    return {"today": sched, "failed": failed, "published_yesterday": pub_y}


def src_engagement():
    from control import engagement
    e = engagement._fetch()
    fol = {k: (v or {}).get("count") for k, v in (e.get("followers") or {}).items()}
    return {"likes": (e.get("totals") or {}).get("likes"), "followers": fol,
            "followers_total": e.get("followers_total")}


def src_sales():
    d = jsonio.load(ROOT / "dashboard" / "data.json", None)
    if d is None:
        raise FileNotFoundError("dashboard/data.json")
    s = d.get("sales") or {}
    return {"sales": s.get("total_sales"), "revenue": s.get("total_revenue"), "clicks": s.get("total_clicks")}


def src_alerts(now):
    a = jsonio.load(DATA / "account_alerts.json", {})
    items = a.get("alerts", []) if isinstance(a, dict) else a
    out = []
    for x in items:
        if x.get("done"):
            continue
        u = x.get("until")
        try:
            days = (datetime.date.fromisoformat(u) - now.date()).days if u else None
        except Exception:
            days = None
        if days is not None and days <= 3:
            out.append({"id": x.get("id"), "platform": x.get("platform"), "text": x.get("text", ""),
                        "until": u, "days": days})
    return out


def _last_block(path, marker):
    """-> (lines of the last '<marker>' block, run datetime or None)."""
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    idx = [i for i, l in enumerate(lines) if l.startswith(marker)]
    if not idx:
        raise ValueError("no run block")
    blk = lines[idx[-1]:]
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})", lines[idx[-1]])
    ran = None
    if m:
        mo, d, y, h, mi = map(int, m.groups())
        ran = datetime.datetime(y, mo, d, h, mi)
    return blk, ran


def src_logs(now):
    res = {}
    for name, fn, marker in (("producer", "producer.log", "producer run:"),
                             ("heel_hunter", "heel_hunter.log", "heel hunter run:"),
                             ("collect", "collect.log", "collect run:")):
        p = HERE / fn
        if not p.exists():
            continue                      # a log that never existed is not an outage
        blk, ran = _last_block(p, marker)
        # Hebrew lines are the producer's agent commentary (it may quote "⚠️" notes), not run errors.
        bad = [l.strip()[:80] for l in blk[1:]
               if ERR_PAT.search(l.strip()) and not re.search(r"[֐-׿]", l)]
        missed = bool(name == "producer" and ran and
                      (now.replace(tzinfo=None) - ran).total_seconds() > MISSED_RUN_H * 3600)
        res[name] = {"errors": bad[:2], "missed": missed, "ran": ran.isoformat() if ran else None}
    return res


def src_learning():
    """Top measured shot from creative_learning.json ({aggregate:{n, ranking:[ids], shots:{id:{camera,...}}}}).
    None until the sample is big enough (same 5-post floor the learning loop uses)."""
    p = DATA / "creative_learning.json"
    if not p.exists():
        return None
    ag = json.loads(p.read_text(encoding="utf-8-sig")).get("aggregate") or {}
    if (ag.get("n") or 0) < 5:
        return None
    shots = ag.get("shots") or {}
    for sid in ag.get("ranking") or []:
        cam = (shots.get(sid) or {}).get("camera")
        if cam and cam != "LEGACY":
            return {"id": sid, "camera": cam}
    return None


# ---------------------------------------------------------------- build
def _delta(cur, prev):
    if cur is None or prev is None:
        return None
    return cur - prev


def _sg(n):
    return f"+{n}" if n >= 0 else str(n)


def build_brief(now=None, state=None):
    """-> (text, data). Never raises on a source failure."""
    tz = _tz()
    now = now or datetime.datetime.now(tz)
    warns, data = [], {"date": now.date().isoformat()}

    def run(name, label, fn, *a):
        try:
            data[name] = fn(*a)
        except Exception:
            data[name] = None
            warns.append(f"⚠️ {label} לא זמין")
        return data[name]

    if state is None:
        try:
            state = jsonio.load(STATE, {})
        except Exception:
            state = {}
    needs = run("needs", "סטטוס לידים", src_needs, now) or []
    queue = run("queue", "תור ייצור", src_queue, now, tz) or {"counts": {}, "stale": []}
    posts = run("posts", "Zernio", src_posts, now, tz)
    eng = run("engagement", "אנגייג׳מנט", src_engagement)
    sales = run("sales", "מכירות/קליקים", src_sales)
    alerts = run("alerts", "התראות חשבון", src_alerts, now) or []
    logs = run("logs", "לוגים", src_logs, now) or {}
    try:
        learn = src_learning()
    except Exception:
        learn = None
    data["learning"] = learn

    name = _cfg("identity.name", "The Stiletto Vault") or "The Stiletto Vault"
    emoji = _cfg("identity.emoji", "") or ""
    L = [f"☀️ בוקר טוב — {name}{(' ' + emoji) if emoji else ''} · {now.strftime('%d/%m/%Y')}", "🔴 מחכה לך:"]
    todo = [f"• {s}: {w}" for s, w in needs]
    if queue["stale"]:
        todo.append(f"• {len(queue['stale'])} לידים מאושרים מחכים מעל {STALE_DAYS} ימים")
    L += todo or ["✅ אין משהו שמחכה לך"]

    if posts is not None:
        t = posts["today"]
        if t:
            L.append(f"📅 היום: {len(t)} פוסטים — " + " · ".join(
                f"{r['time']} {'+'.join(PLAT.get(x, x) for x in r['platforms'])}" for r in t))
        else:
            L.append("📅 היום: אין פוסטים מתוזמנים")

    parts, deltas = [], {}
    if eng:
        prev = state.get("engagement") or {}
        dl = _delta(eng.get("likes"), prev.get("likes"))
        df = _delta(eng.get("followers_total"), prev.get("followers_total"))
        if dl is not None:
            parts.append(f"{_sg(dl)} לייקים")
        elif eng.get("likes") is not None:
            parts.append(f"{eng['likes']} לייקים סה״כ")
        if df is not None:
            pf = prev.get("followers") or {}
            per = [f"{PLAT[k]} {_sg(v - pf[k])}" for k, v in (eng.get("followers") or {}).items()
                   if k in PLAT and v is not None and pf.get(k) is not None]
            parts.append(f"{_sg(df)} עוקבים" + (f" ({' · '.join(per)})" if per else ""))
        elif eng.get("followers_total") is not None:
            parts.append(f"{eng['followers_total']} עוקבים סה״כ")
        deltas.update(likes=dl, followers=df)
    if sales:
        prev = state.get("sales") or {}
        dc = _delta(sales.get("clicks"), prev.get("clicks"))
        if dc is not None:
            parts.append(f"קליקים {_sg(dc)}")
        elif sales.get("clicks") is not None:
            parts.append(f"{sales['clicks']} קליקים סה״כ")
        parts.append(f"מכירות {sales['sales'] if sales.get('sales') is not None else '?'}")
        deltas["clicks"] = dc
    if posts is not None:
        parts.append(f"פורסמו {posts['published_yesterday']}")
    if parts:
        L.append("📈 אתמול: " + " · ".join(parts) + ("" if state else " (ריצה ראשונה — אין השוואה)"))
    data["deltas"] = deltas

    prob = [w.replace("⚠️ ", "", 1) for w in warns]
    if posts:
        for f in posts["failed"]:
            prob.append(f"פוסט נכשל {f['time']} ({'+'.join(f['platforms'])}) {f['title']}")
    for n, r in logs.items():
        if r["errors"]:
            prob.append(f"{n}: {r['errors'][0]}")
        if r["missed"]:
            prob.append(f"{n}: לא רץ מעל {MISSED_RUN_H} שעות")
    if prob:
        L.append("⚠️ תקלות:")
        L += [f"• {p}" for p in prob]
    data["problems"] = prob

    if alerts:
        L.append("🔔 תזכורות: " + " | ".join(
            f"{a['platform']}: {a['text'][:50]} (עד {a['until']})" for a in alerts))
    if learn and learn.get("id"):
        L.append(f"🎯 השוט המוביל: {learn['id']}" + (f" ({learn['camera']})" if learn.get("camera") else ""))

    snap = {}
    if eng:
        snap["engagement"] = {k: eng.get(k) for k in ("likes", "followers", "followers_total")}
    if sales:
        snap["sales"] = sales
    data["snapshot"] = snap
    return "\n".join(L), data


def update_snapshot(data):
    state = jsonio.load(STATE, {})
    state.update(data.get("snapshot") or {})
    state["date"] = data.get("date")
    state["ts"] = time.time()
    jsonio.save(STATE, state, ensure_ascii=False, indent=2)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    text, data = build_brief()
    if a.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return 0
    print(text)
    if a.send:
        ok = False
        try:
            import telegram_sender
            ok = bool(telegram_sender.send_text(text, parse_mode=None))
        except Exception as ex:
            print(f"send failed: {ex}")
        if ok:
            update_snapshot(data)
            print("sent; snapshot updated")
            return 0
        print("send FAILED; snapshot not updated")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
