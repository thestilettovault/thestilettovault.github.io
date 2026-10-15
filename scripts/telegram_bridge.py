"""
telegram_bridge.py — Two-way Telegram bridge for Claude Code

Claude Code uses this to:
  1. Read your latest Telegram messages (get_messages)
  2. Send you approval buttons (send_approval / wait_for_approval)
  3. Send status updates (send_text, send_video)

Usage from Claude Code session:
    python telegram_bridge.py messages          → print last N messages
    python telegram_bridge.py send "text"       → send a text message
    python telegram_bridge.py approval "Do X?"  → send Yes/No buttons, wait for click

As a Python module:
    from telegram_bridge import get_messages, send_approval, wait_for_approval
"""
import sys, os, json, time, requests
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv(Path(__file__).parent / ".env")

BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID       = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
BASE_URL      = f"https://api.telegram.org/bot{BOT_TOKEN}"
SCRIPTS_DIR   = Path(__file__).parent
INBOX_FILE    = SCRIPTS_DIR / "tg_inbox.jsonl"     # written by telegram_bot.py
APPROVAL_FILE = SCRIPTS_DIR / "tg_approval.json"   # written by telegram_bot.py


# ── Read messages (from shared inbox written by telegram_bot.py) ───────────

def get_messages(limit: int = 10, since_ts: str = "") -> list[dict]:
    """
    Read messages that telegram_bot.py has written to tg_inbox.jsonl.
    since_ts: ISO timestamp — only return newer than this.
    """
    if not INBOX_FILE.exists():
        return []
    lines = INBOX_FILE.read_text(encoding="utf-8").splitlines()
    msgs = []
    for line in lines:
        try:
            m = json.loads(line)
            if since_ts and m.get("ts", "") <= since_ts:
                continue
            msgs.append(m)
        except Exception:
            pass
    return msgs[-limit:]


# ── Send ──────────────────────────────────────────────────────────────────────

def send_text(text: str, parse_mode: str = "") -> bool:
    payload = {"chat_id": CHAT_ID, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    r = requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=10)
    return r.ok


def send_video(path: str, caption: str = "") -> bool:
    with open(path, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/sendVideo",
            data={"chat_id": CHAT_ID, "caption": caption, "supports_streaming": "true"},
            files={"video": (os.path.basename(path), f, "video/mp4")},
            timeout=120
        )
    return r.ok


def send_approval(question: str, yes_label: str = "Yes", no_label: str = "No",
                  callback_yes: str = "YES", callback_no: str = "NO") -> int | None:
    """
    Send a message with Yes/No inline keyboard.
    Returns the Telegram message_id (needed to read the button press).
    """
    keyboard = {"inline_keyboard": [[
        {"text": yes_label, "callback_data": callback_yes},
        {"text": no_label,  "callback_data": callback_no},
    ]]}
    r = requests.post(f"{BASE_URL}/sendMessage", json={
        "chat_id": CHAT_ID,
        "text": question,
        "reply_markup": keyboard
    }, timeout=10)
    if r.ok:
        return r.json()["result"]["message_id"]
    return None


def wait_for_approval(question: str, timeout_s: int = 300,
                      yes_label: str = "Yes", no_label: str = "No") -> bool | None:
    """
    Send approval button and block until telegram_bot.py writes the result to tg_approval.json.
    Returns True (yes), False (no), None (timeout).
    """
    # Clear any previous approval result
    if APPROVAL_FILE.exists():
        APPROVAL_FILE.unlink()

    send_approval(question, yes_label, no_label)
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        if APPROVAL_FILE.exists():
            try:
                d = json.loads(APPROVAL_FILE.read_text(encoding="utf-8"))
                return d.get("data") == "YES"
            except Exception:
                pass
        time.sleep(2)

    return None  # timeout


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] == "messages":
        limit = int(args[1]) if len(args) > 1 else 10
        msgs = get_messages(limit=limit)
        if not msgs:
            print("(no new messages)")
        for m in msgs:
            ts = m.get("ts", "")[:16].replace("T", " ")
            kind = "[BTN]" if m.get("type") == "callback" else "[MSG]"
            print(f"{ts} {kind} {m.get('text', '')[:120]}")

    elif args[0] == "send":
        text = " ".join(args[1:])
        ok = send_text(text)
        print("sent" if ok else "error")

    elif args[0] == "approval":
        question = " ".join(args[1:]) or "Proceed?"
        result = wait_for_approval(question, timeout_s=120)
        if result is True:
            print("YES")
        elif result is False:
            print("NO")
        else:
            print("TIMEOUT")

    elif args[0] == "video":
        path = args[1]
        caption = " ".join(args[2:]) if len(args) > 2 else ""
        ok = send_video(path, caption)
        print("sent" if ok else "error")

    else:
        print(__doc__)
