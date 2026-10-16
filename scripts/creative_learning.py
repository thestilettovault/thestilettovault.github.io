# -*- coding: utf-8 -*-
"""Creative learning loop: which SHOT TYPES / CAMERA TYPES earn the most engagement.

    py -3 scripts/creative_learning.py            # dry run: Hebrew summary only
    py -3 scripts/creative_learning.py --write    # data/creative_learning.json + poses.md auto section

Chain: Zernio post -> media URL -> shoe slug -> orchestrator choice (A-D) -> GELEM brief
(shot 1-4) -> shot id + camera -> engagement (control.engagement). GET-only reads.
"""
import sys, re, json, argparse, datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT))

try:
    from control.niche import cfg as _cfg
except Exception:
    def _cfg(_path, default=None):
        return default

GELEM = ROOT / "GELEM"
STATE = ROOT / "data" / "orchestrator_state.json"
OUT_JSON = ROOT / "data" / "creative_learning.json"
POSES = ROOT / "data" / "agents" / "poses.md"
START, END = "<!-- LEARNING:START -->", "<!-- LEARNING:END -->"
MIN_VIEWS = 50
PRIOR_W = 3
MIN_POSTS = 5

ID_RE = re.compile(r"\b(PH|ST|BT|FR|P|S|C)\d{2}\b")
CAM_RE = re.compile(r"CAMERA:\s*(PHONE|SET|BTS|FRIEND)", re.I)


def derive_camera(sid):
    if sid.startswith("PH"):
        return "PHONE"
    if sid.startswith("ST"):
        return "SET"
    if sid.startswith("BT"):
        return "BTS"
    if sid.startswith("FR"):
        return "FRIEND"
    if sid.startswith("S"):
        return "PHONE"
    if sid.startswith("C"):
        n = int(sid[1:])
        return "BTS" if n <= 3 else "PHONE" if n <= 5 else "FRIEND"
    return "LEGACY"


def _label(chunk, m):
    rest = chunk[m.end():]
    rest = re.sub(r"^[\s\*·\-—–:]+", "", rest)
    lab = re.split(r"[:(—\n]|\*\*| · | - ", rest, maxsplit=1)[0]
    return lab.strip(" *·-—:")[:60]


def _split_shots(text):
    text = text.strip()
    m = re.search(r"^\s*SHOTS:\s*(.+)$", text, re.M | re.I)
    if m:
        return [c for c in m.group(1).split(" | ") if c.strip()]
    parts = re.split(r"(?m)^\s*(?=[1-4][\.\)]\s)", text)
    return [p for p in parts if re.match(r"\s*[1-4][\.\)]\s", p)]


def parse_brief(text):
    out = []
    for chunk in _split_shots(text or "")[:4]:
        m = ID_RE.search(chunk)
        if not m:
            continue
        sid = m.group(0)
        cm = CAM_RE.search(chunk)
        cam = cm.group(1).upper() if cm else derive_camera(sid)
        out.append({"id": sid, "camera": cam, "label": _label(chunk, m)})
    return out


def slug_from_media(url, img_dir="img/heels"):
    if not url:
        return None
    marker = "/" + img_dir.strip("/") + "/"
    if marker not in url:
        return None
    rest = url.split(marker, 1)[1].split("?")[0].split("#")[0]
    parts = [p for p in rest.split("/") if p]
    if not parts:
        return None
    if len(parts) == 1:
        return re.sub(r"\.[A-Za-z0-9]+$", "", parts[0]) or None
    return parts[0]


def score(row):
    g = lambda k: int(row.get(k) or 0)
    return g("likes") + 2 * g("saves") + 3 * g("shares") + g("comments") + 5 * g("follows")


def rate(row):
    v = int(row.get("views") or 0)
    return score(row) / v if v >= MIN_VIEWS else None


def _state_index(states):
    idx = {}
    for k, v in (states or {}).items():
        if str(k).startswith("_") or not isinstance(v, dict):
            continue
        idx.setdefault(k.split("/")[-1], []).append((k, v))
    return idx


def find_brief(gelem_root, key):
    """GELEM/<key>/_BRIEF.md, else GELEM/<date>/<tail>/_BRIEF.md (state key may be bare)."""
    gelem_root = Path(gelem_root)
    tail = key.split("/")[-1]
    cands = [gelem_root / key / "_BRIEF.md", gelem_root / tail / "_BRIEF.md"]
    cands += sorted(gelem_root.glob("*/" + tail + "/_BRIEF.md"), reverse=True)
    for c in cands:
        if c.exists():
            return c
    return None


def _img_dir():
    try:
        return _cfg("site.img_dir", "img/heels")
    except Exception:
        return "img/heels"


def post_slugs_from_catalog(catalog, img_dir="img/heels"):
    """post_id -> slug tail, from catalog items' `post_ids` (stored by schedule_drop since
    2026-10-15). Needed for TikTok: its media is re-hosted on media.zernio.com, so the
    URL no longer carries our img/<noun>/<slug>/ path."""
    out = {}
    for it in catalog or []:
        ids = it.get("post_ids") or []
        if not ids:
            continue
        tail = None
        for v in (it.get("assets") or {}).values():
            for u in (v if isinstance(v, list) else [v]):
                tail = slug_from_media(u if isinstance(u, str) else "", img_dir)
                if tail:
                    break
            if tail:
                break
        if tail:
            for pid in ids:
                out[pid] = tail
    return out


def build_dataset(posts, per_post, states, gelem_root, post_slugs=None):
    post_slugs = post_slugs or {}
    gelem_root = Path(gelem_root)
    idx = _state_index(states)
    try:
        img_dir = _cfg("site.img_dir", "img/heels")
    except Exception:
        img_dir = "img/heels"
    cache, rows = {}, []
    for p in posts:
        if (p.get("status") or "") != "published":
            continue
        pid = p.get("_id")
        slug = None
        for mi in p.get("mediaItems") or []:
            slug = slug_from_media(mi.get("url"), img_dir)
            if slug:
                break
        slug = slug or post_slugs.get(pid) or post_slugs.get(p.get("latePostId"))
        if not slug or slug not in idx:
            continue
        eng = per_post.get(pid) or per_post.get(p.get("latePostId"))
        if not eng:
            continue
        key = choice = None
        for k, v in idx[slug]:
            c = (v.get("choice") or "").upper()
            if not c and v.get("chosen"):
                m = re.search(r"ad_([A-D])", v["chosen"])
                c = m.group(1) if m else ""
            if c and c in "ABCD":
                key, choice = k, c
                break
        if not choice:
            continue
        if key not in cache:
            try:
                bp = find_brief(gelem_root, key)
                cache[key] = parse_brief(bp.read_text(encoding="utf-8-sig")) if bp else []
            except Exception:
                cache[key] = []
        shots = cache[key]
        i = "ABCD".index(choice)
        if i >= len(shots):
            continue
        sh = shots[i]
        plat = eng.get("platform") or ((p.get("platforms") or [{}])[0] or {}).get("platform", "")
        row = {"post_id": pid, "platform": plat,
               "published_at": eng.get("published_at") or p.get("scheduledFor"),
               "slug": slug, "choice": choice, "shot_id": sh["id"], "camera": sh["camera"],
               "label": sh["label"]}
        for m in ("views", "likes", "saves", "shares", "comments", "follows"):
            row[m] = int(eng.get(m) or 0)
        row["score"] = score(row)
        row["rate"] = rate(row)
        rows.append(row)
    return rows


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _group(rows, keyf):
    g = {}
    for r in rows:
        g.setdefault(keyf(r), []).append(r)
    return g


def _stats(rs):
    return {"n": len(rs), "mean_score": _mean([r["score"] for r in rs]),
            "mean_views": _mean([r["views"] for r in rs]),
            "mean_rate": _mean([r["rate"] for r in rs])}


def aggregate(rows):
    gmean = _mean([r["score"] for r in rows]) or 0.0
    shots = {}
    for sid, rs in _group(rows, lambda r: r["shot_id"]).items():
        s = _stats(rs)
        s["camera"] = rs[0]["camera"]
        s["label"] = next((r["label"] for r in rs if r["label"]), "")
        s["shrunk_score"] = (s["n"] * s["mean_score"] + PRIOR_W * gmean) / (s["n"] + PRIOR_W)
        s["by_platform"] = {pl: _stats(x) for pl, x in _group(rs, lambda r: r["platform"]).items()}
        shots[sid] = s
    cams = {}
    for cam, rs in _group(rows, lambda r: r["camera"]).items():
        s = _stats(rs)
        s["by_platform"] = {pl: _stats(x) for pl, x in _group(rs, lambda r: r["platform"]).items()}
        cams[cam] = s
    ranking = sorted(shots, key=lambda k: -shots[k]["shrunk_score"])
    return {"global_mean_score": gmean, "n": len(rows), "shots": shots,
            "cameras": cams, "ranking": ranking}


def render_section(agg, today=None):
    today = today or datetime.date.today().isoformat()
    n = agg["n"]
    head = "## Measured ranking (auto, %s, %d posts)" % (today, n)
    if n < MIN_POSTS:
        return "\n".join([head, "",
                          "Sample too small (%d usable posts, need %d). No ranking is applied yet; "
                          "keep the standard 2 PHONE + 1 SET + 1 BTS mix and vary ids." % (n, MIN_POSTS)])
    usable = [k for k in agg["ranking"] if agg["shots"][k]["camera"] != "LEGACY"]
    lines = [head, "",
             "| rank | id | camera | label | posts | avg score | avg views |",
             "|---|---|---|---|---|---|---|"]
    for i, k in enumerate(usable[:8], 1):
        s = agg["shots"][k]
        lines.append("| %d | %s | %s | %s | %d | %.1f | %.0f |" % (
            i, k, s["camera"], (s["label"] or "").replace("|", "/"), s["n"],
            s["mean_score"], s["mean_views"] or 0))
    if not usable:
        lines.append("| - | (no PH/ST/BT/FR posts measured yet) | | | | | |")
    cams = sorted(((c, v) for c, v in agg["cameras"].items() if c != "LEGACY"),
                  key=lambda x: -x[1]["mean_score"])
    lines.append("")
    if cams:
        lines.append("Cameras: " + " · ".join(
            "%s %.1f (n=%d)" % (c, v["mean_score"], v["n"]) for c, v in cams))
    else:
        lines.append("Cameras: no measured data on the new camera system yet.")
    lines += ["", "Producer: within the 2 PHONE + 1 SET + 1 BTS mix prefer higher-ranked ids; "
              "keep ONE of the 4 shots for an id with fewer than 3 posts (exploration). "
              "Legacy P/S/C ids are history only - do not pick them."]
    return "\n".join(lines)


def replace_section(text, section):
    block = START + "\n" + section.strip("\n") + "\n" + END
    if START in text and END in text and text.index(START) < text.index(END):
        a = text.index(START)
        b = text.index(END) + len(END)
        return text[:a] + block + text[b:]
    sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    return text + sep + block + "\n"


def heb_summary(agg, rows):
    L = ["למידה קריאטיבית: %d פוסטים תואמים לבריף" % agg["n"]]
    if not rows:
        return "\n".join(L + ["אין מספיק נתונים."])
    L.append("ממוצע ציון גלובלי: %.1f" % agg["global_mean_score"])
    L.append("דירוג צילומים (עם התכווצות לממוצע):")
    for i, k in enumerate(agg["ranking"][:12], 1):
        s = agg["shots"][k]
        L.append("  %d. %s [%s] %s - פוסטים %d, ציון ממוצע %.1f, צפיות %.0f" % (
            i, k, s["camera"], s["label"], s["n"], s["mean_score"], s["mean_views"] or 0))
    L.append("מצלמות:")
    for c, v in sorted(agg["cameras"].items(), key=lambda x: -x[1]["mean_score"]):
        L.append("  %s: ציון %.1f, פוסטים %d, צפיות %.0f" % (c, v["mean_score"], v["n"], v["mean_views"] or 0))
    if agg["n"] < MIN_POSTS:
        L.append("מדגם קטן מדי - לא מיושם דירוג.")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    from control import services, engagement
    import jsonio
    posts = services.zernio_all_posts()
    per_post = engagement._fetch()["per_post"]
    states = json.loads(STATE.read_text(encoding="utf-8-sig")) if STATE.exists() else {}
    try:
        import catalog_io
        post_slugs = post_slugs_from_catalog(catalog_io.load_catalog(), _img_dir())
    except Exception:
        post_slugs = {}
    rows = build_dataset(posts, per_post, states, GELEM, post_slugs)
    agg = aggregate(rows)
    print("posts fetched: %d | matched to a brief: %d" % (len(posts), len(rows)))
    print(heb_summary(agg, rows))
    if a.write:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        jsonio.save(OUT_JSON, {"generated_at": now, "aggregate": agg, "rows": rows},
                    indent=2, ensure_ascii=False)
        text = POSES.read_text(encoding="utf-8") if POSES.exists() else ""
        POSES.write_text(replace_section(text, render_section(agg)), encoding="utf-8", newline="\n")
        print("written:", OUT_JSON, POSES)


if __name__ == "__main__":
    main()
