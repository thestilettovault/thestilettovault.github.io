# -*- coding: utf-8 -*-
"""
orchestrator.py - state + Telegram hand-offs for ONE heel at a time, with the
single human decision (which ad wins) happening in Telegram.

CURRENT FLOW (agents never spend credits; Ofer presses Run in the Magnific app,
where Unlimited makes it free):

    1. run_producer.bat -> produce_queue.md: PREPARE the Space board for the newest
       approved lead (upload source, patch nodes, 4 shot briefs) -> `ready <slug>`
       sends the "board ready" message with a boardrun button; queue status=board_ready.
    2. Ofer presses Run in the Magnific app, taps the button -> telegram_bot
       (claim_collect: board_ready -> collecting) -> run_collect.bat -> collect_queue.md.
    3. collect_queue.md downloads the 4 ads (ad_A..ad_D.jpg), QA -> _QA.md,
       then `send <slug>` posts them with pick buttons (status awaiting_choice).
    4. Ofer taps a pick -> telegram_bot adpick -> record_choice (status chosen).
    5. auto_schedule.py -> finalize(slug): the chosen ad becomes post_image.jpg
       (clean, no burned-in text) + the per-platform drop for social_publisher.
       There is no per-lead video step any more.

slug = local_asset minus the leading "GELEM/", e.g. "2026-10-13/stiletto-heels-123"
(CLI: `slug-of <local_asset>`). It is the key of orchestrator state and the GELEM subfolder.

CLI: send | choose | finalize | pending | state | ready | slug-of | set-status |
     queue-set | claim | resolve-cb

State for the async human steps lives in data/orchestrator_state.json (atomic,
lock-protected writes) so the Telegram callback (a different process) and the
headless agents hand off cleanly.
"""
import os, sys, json, time, shutil, hashlib, contextlib
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

import urllib.request
import space_runner
import overlay as overlay_mod
import telegram_sender as ts   # reuse its proven token/chat/.env loading

ROOT       = Path(__file__).resolve().parent.parent
GELEM      = ROOT / "GELEM"
STATE_FILE = ROOT / "data" / "orchestrator_state.json"
QUEUE_FILE = ROOT / "data" / "production_queue.json"

BOT_TOKEN = ts.BOT_TOKEN
CHAT_ID   = ts.CHAT_ID
API       = ts.BASE_URL
BURN_DEAL_OVERLAY = False   # clean posts (Ofer 2026-10-15)


# ---------------- state ----------------

@contextlib.contextmanager
def _lock(path, timeout=10.0, stale=60.0):
    """Cross-process lock via an O_CREAT|O_EXCL lock file next to `path`."""
    lock = str(path) + ".lock"
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock) > stale:
                    os.remove(lock)
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                raise TimeoutError(f"lock busy: {lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass

def _read_json(path, default):
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default

def _write_json_atomic(path, data):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)

def _load():
    return _read_json(STATE_FILE, {})

def _save(st):
    with _lock(STATE_FILE):
        _write_json_atomic(STATE_FILE, st)

def _update(fn):
    """Locked read-modify-write of the state file. fn(state) -> result."""
    with _lock(STATE_FILE):
        st = _read_json(STATE_FILE, {})
        res = fn(st)
        _write_json_atomic(STATE_FILE, st)
        return res

def set_state(slug, **kw):
    def f(st):
        st.setdefault(slug, {}).update(kw)
        return dict(st[slug])
    return _update(f)

def get_state(slug):
    return _load().get(slug, {})

def slug_of(local_asset):
    """local_asset 'GELEM/2026-10-13/foo-123' -> state key '2026-10-13/foo-123'."""
    s = str(local_asset).replace("\\", "/").strip().strip("/")
    if s.upper().startswith("GELEM/"):
        s = s[len("GELEM/"):]
    return s

def set_status(slug, status):
    """Set only the orchestrator status of a slug (used by the .md runners)."""
    return set_state(slug, status=status)

def queue_set(slug, status):
    """Set status of the production_queue.json entry whose local_asset maps to slug.
    Returns True if an entry was updated."""
    with _lock(QUEUE_FILE):
        q = _read_json(QUEUE_FILE, [])
        hit = False
        for e in q:
            if slug_of(e.get("local_asset", "")) == slug:
                e["status"] = status
                hit = True
        if hit:
            _write_json_atomic(QUEUE_FILE, q)
    return hit

COLLECT_STALE_S = 30 * 60


def claim_collect(slug):
    """Atomically flip board_ready -> collecting. False if not board_ready
    (already collecting / double tap). A 'collecting' claim older than
    COLLECT_STALE_S (crashed run) and the legacy 'run_clicked' can be re-claimed."""
    def f(st):
        cur = st.get(slug, {})
        s = cur.get("status")
        stale = s == "collecting" and time.time() - cur.get("collect_ts", 0) > COLLECT_STALE_S
        if s not in ("board_ready", "run_clicked") and not stale:
            return False
        cur.update(status="collecting", collect_ts=time.time())
        st[slug] = cur
        return True
    return _update(f)


# ---------------- Telegram callback tokens (64-byte limit) ----------------

CB_LIMIT = 64

def _cb_token(slug):
    """Short token (10 hex of sha1) registered in state['_cb'] -> slug."""
    short = hashlib.sha1(slug.encode("utf-8")).hexdigest()[:10]
    def f(st):
        st.setdefault("_cb", {})[short] = slug
    _update(f)
    return short

def make_callback(action, slug, extra=None):
    """Build callback_data (<=64 bytes). Old full-slug format when it fits, short
    token otherwise."""
    tail = f"|{extra}" if extra else ""
    full = f"{action}|{slug}{tail}"
    if len(full.encode("utf-8")) <= CB_LIMIT:
        return full
    data = f"{action}|{_cb_token(slug)}{tail}"
    assert len(data.encode("utf-8")) <= CB_LIMIT, data
    return data

def resolve_cb(token):
    """Accept a short token or a full slug (buttons already in chat); return the slug."""
    cb = _load().get("_cb", {})
    return cb.get(token, token)


# ---------------- Telegram ----------------

def _send_photo(path, caption, buttons=None):
    """POST a local photo to the chat with an optional inline keyboard.
    Uses requests' multipart (the hand-rolled body 400'd on large 2K images);
    drops parse_mode so long slugs/captions can't break Markdown parsing, and
    retries the transient Telegram "internal Server Error / 404 during file
    upload" a few times."""
    import requests, time as _t
    data = {"chat_id": CHAT_ID, "caption": caption}
    if buttons:
        data["reply_markup"] = json.dumps({"inline_keyboard": buttons})
    for attempt in range(4):
        try:
            with open(path, "rb") as fh:
                r = requests.post(f"{API}/sendPhoto", data=data,
                                  files={"photo": fh}, timeout=90)
            if r.ok:
                return True
        except Exception:
            pass
        _t.sleep(3)
    return False

def send_ad_choice(slug):
    """Send all candidate ads (ad_A.jpg, ad_B.jpg, ...) so Ofer picks ONE winner.
    The chosen ad is the only one that goes on to become the single 9:16 video."""
    folder = GELEM / slug
    ads = sorted(folder.glob("ad_*.jpg"))
    if not ads:
        print(f"! no ad_*.jpg in {folder}"); return False
    # QA verdicts written by the producer (data/agents/qa.md): "A ✅" / "B ⚠️ 3 רגליים"
    qa = {}
    qa_file = folder / "_QA.md"
    if qa_file.exists():
        for line in qa_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if len(line) > 1 and line[0] in "ABCD" and line[1] == " ":
                qa[line[0]] = line[2:].strip()
    sent = 0
    for p in ads:
        letter = p.stem.split("_", 1)[1]        # ad_A -> A
        verdict = f"\nבדיקה: {qa[letter]}" if letter in qa else ""
        if _send_photo(p, f"*מודעה {letter}* — {slug}{verdict}",
                       buttons=[[{"text": f"✅ בחר {letter}",
                                  "callback_data": make_callback("adpick", slug, letter)}]]):
            sent += 1
    if sent < 1:
        print(f"! {slug}: no ad could be sent to Telegram - status left unchanged"); return False
    set_state(slug, status="awaiting_choice", n_ads=len(ads), n_sent=sent, ts=time.time())
    print(f"sent {sent}/{len(ads)} ad options for {slug} to Telegram")
    return True


# ---------------- called by the Telegram callback ----------------

def board_ready(slug):
    """The Space now holds THIS shoe + its 4-shot brief. Ofer presses Run in the
    Magnific app (free there — Unlimited does not apply to API runs) and taps the
    button; the bot then collects the 4 ads (run_collect.bat)."""
    src = GELEM / slug / "source.jpg"
    caption = (f"🎬 הלוח מוכן: {slug.split('/')[-1]}\n"
               "1. פתח את Magnific > הלוח thestilettovault Ad campaign\n"
               "2. לחץ Run על Creative concept builder\n"
               "3. כשרואים 4 תמונות, לחץ על הכפתור כאן")
    btn = [[{"text": "✅ הרצתי, יש 4 תמונות", "callback_data": make_callback("boardrun", slug)}]]
    if src.exists():
        _send_photo(src, caption, buttons=btn)
    else:
        import requests
        requests.post(f"{API}/sendMessage", json={"chat_id": CHAT_ID, "text": caption,
                      "reply_markup": {"inline_keyboard": btn}}, timeout=20)
    set_state(slug, status="board_ready", board_ready_ts=time.time())
    print(f"{slug}: board ready, Telegram notice sent")
    return True


def record_choice(slug, choice):
    """choice in {'A','B','C','D'} - mark the winner. Only allowed while the slug is
    awaiting_choice (or already chosen: re-pick); anything else is 'already handled'."""
    choice = choice.upper().strip()
    chosen = f"ad_{choice}.jpg"
    cur = get_state(slug).get("status")
    if cur not in ("awaiting_choice", "chosen"):
        return False, f"already handled ({cur or 'unknown'})"
    if not (GELEM / slug / chosen).exists():
        return False, f"no {chosen} for {slug}"
    set_state(slug, status="chosen", chosen=chosen, choice=choice, chosen_ts=time.time())
    print(f"{slug}: chose {choice}")
    return True, chosen

def pending_video_jobs():
    """Slugs whose ad was chosen but not finalized yet (status=chosen)."""
    return [s for s, v in _load().items() if isinstance(v, dict) and v.get("status") == "chosen"]


# ---------------- finalize (after videos are downloaded) ----------------

def build_drop(slug):
    """Lay the FINAL media into GELEM/<slug>/drop/ under the ig_/tt_ names that
    pickup_drop.classify_media routes per platform. The Smart-Heel design is one
    still + one 9:16 video that serve BOTH channels, so each is mirrored to
    Instagram and TikTok. This keeps the raw ad_*/source files out of the drop
    entirely — pickup_drop points at this subfolder via --folder.
    Returns the drop dir, or None if the post_image is missing."""
    folder = GELEM / slug
    post_image = folder / "post_image.jpg"
    video      = folder / "video.mp4"
    if not post_image.exists():
        print(f"! {slug}: no post_image to drop"); return None
    drop = folder / "drop"
    drop.mkdir(exist_ok=True)
    shutil.copyfile(post_image, drop / "ig_image_1.jpg")
    shutil.copyfile(post_image, drop / "tt_image_1.jpg")
    if video.exists():
        shutil.copyfile(video, drop / "ig_video_1.mp4")
        shutil.copyfile(video, drop / "tt_video_1.mp4")
    else:
        print(f"  ~ {slug}: no video.mp4 yet — drop has stills only")
    print(f"  drop ready: {drop} ({'image+video' if video.exists() else 'image only'})")
    return drop


def finalize(slug):
    """Make the chosen ad the post image (deal overlay only if BURN_DEAL_OVERLAY) and
    stage the per-platform drop for social_publisher. video.mp4 is optional."""
    st = get_state(slug)
    chosen = st.get("chosen")
    if not chosen:
        print(f"! {slug}: no chosen ad yet"); return False
    ad_path = GELEM / slug / chosen
    if not ad_path.exists():
        print(f"! {slug}: chosen ad {chosen} missing on disk - NOT finalized"); return False
    deal = overlay_mod._deal_for_folder(slug)
    # Ofer 2026-10-15: posts are CLEAN photos from now on (no burned-in price or
    # headline). The deal still travels in the caption. Set BURN_DEAL_OVERLAY = True
    # to bring the overlay back.
    posted_img = (overlay_mod.apply_overlay(str(ad_path), deal,
                                            str(GELEM / slug / "post_image.jpg"))
                  if BURN_DEAL_OVERLAY else None)
    # No deal data (full-price brand heels, e.g. Naked Wolfe) → no overlay is drawn.
    # The clean chosen ad is then the post image; without this the heel had no
    # drop and silently never got scheduled (2026-10-13: 5 Naked Wolfe heels stuck).
    post_path = GELEM / slug / "post_image.jpg"
    if not posted_img or not post_path.exists():
        shutil.copyfile(ad_path, post_path)
        posted_img = str(post_path)
    drop = build_drop(slug)
    if not drop:
        print(f"! {slug}: no drop built — NOT finalized"); return False
    set_state(slug, status="finalized",
              post_image=posted_img,
              video=str(GELEM / slug / "video.mp4"),   # one 9:16 video -> both IG + TikTok
              drop=str(drop) if drop else None,
              deal=deal)
    print(f"{slug}: finalized -> {Path(posted_img).name if posted_img else '(no deal overlay)'}")
    print(f"  next: pickup_drop.py {slug} --from-gelem --folder {slug}/drop --push --publish")
    return True


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["send", "choose", "finalize", "pending", "state", "ready",
                                    "slug-of", "set-status", "queue-set", "claim", "resolve-cb"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    if sys.stdout:
        try: sys.stdout.reconfigure(encoding="utf-8")
        except Exception: pass
    if a.cmd == "ready":
        board_ready(a.args[0])
    elif a.cmd == "send":
        sys.exit(0 if send_ad_choice(a.args[0]) else 1)
    elif a.cmd == "choose":
        print(record_choice(a.args[0], a.args[1]))
    elif a.cmd == "finalize":
        sys.exit(0 if finalize(a.args[0]) else 1)
    elif a.cmd == "pending":
        print(pending_video_jobs())
    elif a.cmd == "slug-of":
        print(slug_of(a.args[0]))
    elif a.cmd == "set-status":
        print(set_status(a.args[0], a.args[1]).get("status"))
    elif a.cmd == "queue-set":
        ok = queue_set(a.args[0], a.args[1])
        print("ok" if ok else "no matching queue entry")
        sys.exit(0 if ok else 1)
    elif a.cmd == "claim":
        ok = claim_collect(a.args[0])
        print("claimed" if ok else "not claimable")
        sys.exit(0 if ok else 1)
    elif a.cmd == "resolve-cb":
        print(resolve_cb(a.args[0]))
    elif a.cmd == "state":
        print(json.dumps(get_state(a.args[0]) if a.args else _load(), ensure_ascii=False, indent=2))
