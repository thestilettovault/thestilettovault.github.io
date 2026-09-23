# -*- coding: utf-8 -*-
"""
orchestrator.py - run ONE heel end-to-end through the Smart-Heel Space, with the
single human decision (which ad wins) happening in Telegram.

Roles:  [agent] = Claude via the Magnific MCP tools.   [py] = this module.

    1. [py]    stage(item)                       -> GELEM/<slug>/source.jpg
    2. [agent] creations_upload_image(source)    -> creation id
    3. [agent] wire it as the Campaign image generator reference (spaces_edit)
    4. [agent] spaces_run  ... down to the two static ads
    5. [agent] download the 2 ad images          -> GELEM/<slug>/ad_A.jpg, ad_B.jpg
    6. [py]    send_ad_choice(slug)              -> 2 photos + "choose" buttons to Telegram
    7.  Ofer taps  "בחר A/B"  -> telegram_bot callback -> [py] record_choice(slug, x)
    8. [agent] spaces_run ONE 9:16 video from the CHOSEN ad (serves IG + TikTok)
    9. [agent] download the video   -> GELEM/<slug>/video.mp4
   10. [py]    finalize(slug)  -> burn the deal overlay on the chosen ad + queue the
                                  Instagram + TikTok posts (social_publisher / Zernio)

State for the async human step lives in data/orchestrator_state.json so the
Telegram callback (a different process) and the agent can hand off cleanly.
"""
import os, sys, json, time, shutil
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

BOT_TOKEN = ts.BOT_TOKEN
CHAT_ID   = ts.CHAT_ID
API       = ts.BASE_URL


# ---------------- state ----------------

def _load():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}

def _save(st):
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

def set_state(slug, **kw):
    st = _load()
    st.setdefault(slug, {}).update(kw)
    _save(st)
    return st[slug]

def get_state(slug):
    return _load().get(slug, {})


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
    for p in ads:
        letter = p.stem.split("_", 1)[1]        # ad_A -> A
        _send_photo(p, f"*מודעה {letter}* — {slug}",
                    buttons=[[{"text": f"✅ בחר {letter}", "callback_data": f"adpick|{slug}|{letter}"}]])
    set_state(slug, status="awaiting_choice", n_ads=len(ads), ts=time.time())
    print(f"sent {len(ads)} ad options for {slug} to Telegram")
    return True


# ---------------- called by the Telegram callback ----------------

def record_choice(slug, choice):
    """choice in {'A','B'} — mark the winner. The agent watches for status=chosen,
    then runs the two videos from GELEM/<slug>/ad_<choice>.jpg."""
    choice = choice.upper().strip()
    chosen = f"ad_{choice}.jpg"
    if not (GELEM / slug / chosen).exists():
        return False, f"no {chosen} for {slug}"
    set_state(slug, status="chosen", chosen=chosen, choice=choice, chosen_ts=time.time())
    print(f"{slug}: chose {choice}")
    return True, chosen

def pending_video_jobs():
    """Slugs the agent still has to render videos for (status=chosen)."""
    return [s for s, v in _load().items() if v.get("status") == "chosen"]


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
    """Burn the deal overlay on the chosen ad and stage the per-platform drop for
    social_publisher. Runs once the 9:16 video is downloaded into GELEM/<slug>/."""
    st = get_state(slug)
    chosen = st.get("chosen")
    if not chosen:
        print(f"! {slug}: no chosen ad yet"); return False
    deal = overlay_mod._deal_for_folder(slug)
    ad_path = GELEM / slug / chosen
    posted_img = overlay_mod.apply_overlay(str(ad_path), deal,
                                           str(GELEM / slug / "post_image.jpg"))
    drop = build_drop(slug)
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
    ap.add_argument("cmd", choices=["send", "choose", "finalize", "pending", "state"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    if sys.stdout:
        try: sys.stdout.reconfigure(encoding="utf-8")
        except Exception: pass
    if a.cmd == "send":
        send_ad_choice(a.args[0])
    elif a.cmd == "choose":
        print(record_choice(a.args[0], a.args[1]))
    elif a.cmd == "finalize":
        finalize(a.args[0])
    elif a.cmd == "pending":
        print(pending_video_jobs())
    elif a.cmd == "state":
        print(json.dumps(get_state(a.args[0]) if a.args else _load(), ensure_ascii=False, indent=2))
