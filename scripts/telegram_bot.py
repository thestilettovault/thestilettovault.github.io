"""
TheGothicVault Taste Bot — Long-running polling bot
Handles:
  - ✅/❌ button callbacks on products sent by gothic_scout
  - URLs sent by user (learns their taste from what they share)
  - /taste command — shows current taste profile
  - /run <cmd> — execute terminal command, reply with output
  - /status — recent MP4 files + git status
  - /help command

All incoming messages + callbacks are written to tg_inbox.jsonl
so Claude Code can read them via telegram_bridge.py.

Run once as a background process:
    python telegram_bot.py
"""
import sys
import os
import re
import json
import time
import socket
import logging
import subprocess
import requests as _req
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# pythonw.exe (windowless, used by the scheduled task) has NO console:
# sys.stdout/stderr are None. The bare reconfigure below used to crash the
# process at import time — before logging existed — so it died silently and
# never restarted. Guard it so the bot runs headless.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))
import taste_engine

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID      = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
PROJECT_ROOT = Path("E:/PROJECTS/thegothicvault")
INBOX_FILE   = Path(__file__).parent / "tg_inbox.jsonl"
APPROVAL_FILE= Path(__file__).parent / "tg_approval.json"
TASTE_REFS   = Path(r"E:\BOLD vault\LEARNING\taste-profile\references")
BOLD_BUS     = Path(r"E:\BOLD vault\BOLD_BUS.json")
MIA_ROOT     = Path(r"E:\ALL VS CODE PROJ\maya\mia-system")

# Rotating log — caps size so it never balloons to MBs again (was 5.4MB of httpx spam)
_log_handler = RotatingFileHandler(
    Path(__file__).parent / "bot_callbacks.log",
    maxBytes=2_000_000, backupCount=3, encoding="utf-8"
)
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[_log_handler, logging.StreamHandler()]
)
# Silence per-request HTTP spam — these logged every 10s and drowned real errors
for _noisy in ("httpx", "httpcore", "telegram.ext.Updater", "apscheduler"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

URL_RE = re.compile(r'https?://[^\s]+')

# ── Single-instance guard ─────────────────────────────────────────────
# Binds a localhost port; a second bot process fails here and exits.
# Prevents two getUpdates loops on the same token → Telegram 409 Conflict.
_SINGLE_INSTANCE_PORT = 49517  # arbitrary high port reserved for this bot
_instance_lock_sock = None

def acquire_single_instance():
    global _instance_lock_sock
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", _SINGLE_INSTANCE_PORT))
        s.listen(1)
        _instance_lock_sock = s  # keep ref alive for process lifetime
        return True
    except OSError:
        return False


# ── Global error handler ──────────────────────────────────────────────
# Without this, transient network errors (httpx/httpcore TCP failures) were
# logged as "No error handlers are registered" and could tear down polling.
async def on_error(update, context):
    err = context.error
    name = type(err).__name__
    # Network blips are expected — log quietly, never crash the loop
    logger.warning(f"Handled error: {name}: {str(err)[:200]}")


# ── Shared inbox (Claude Code reads this) ─────────────────────────────

def _write_inbox(entry: dict):
    entry["ts"] = datetime.now().isoformat()
    with open(INBOX_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def _write_approval(data: str, text: str):
    APPROVAL_FILE.write_text(
        json.dumps({"data": data, "text": text, "ts": datetime.now().isoformat()},
                   ensure_ascii=False),
        encoding="utf-8"
    )


# ── Commands ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🖤 *TheGothicVault Taste Bot*\n\n"
        "שלח לי לינק למוצר שאתה אוהב — אלמד ממנו.\n"
        "על מוצרים שאני שולח — לחץ ✅ לאישור או ❌ לדחייה.\n\n"
        "*/taste* — הצג פרופיל טעם נוכחי\n"
        "*/help* — עזרה",
        parse_mode="Markdown"
    )

async def cmd_taste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    summary = taste_engine.get_summary()
    await update.message.reply_text(summary, parse_mode="Markdown")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🖤 *TheGothicVault Bot*\n\n"
        "*/run* `<cmd>` — הרץ פקודת טרמינל\n"
        "*/status* — קבצים אחרונים + git\n"
        "*/taste* — פרופיל טעם\n\n"
        "שלח לינק → לומד טעם\n"
        "שלח טקסט → נשמר ל-Claude Code",
        parse_mode="Markdown"
    )


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.message.chat_id != CHAT_ID:
        return
    raw = update.message.text or ""
    cmd = raw[len("/run"):].strip()
    if not cmd:
        await update.message.reply_text("שימוש: /run <command>")
        return
    _write_inbox({"type": "run", "text": cmd})
    await update.message.reply_text(f"מריץ: `{cmd[:80]}`", parse_mode="Markdown")
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=120, cwd=str(PROJECT_ROOT), encoding="utf-8", errors="replace")
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        body = (out + ("\n" + err if err else ""))[-3000:] or "(no output)"
        status = "OK" if r.returncode == 0 else f"exit {r.returncode}"
        await update.message.reply_text(f"{status}\n```\n{body}\n```", parse_mode="Markdown")
    except subprocess.TimeoutExpired:
        await update.message.reply_text("timeout 120s")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.message.chat_id != CHAT_ID:
        return
    lines = ["*Status*\n"]
    try:
        r = subprocess.run(["git", "-C", str(PROJECT_ROOT), "status", "--short"],
                           capture_output=True, text=True, timeout=5)
        lines.append(f"```\n{r.stdout.strip()[:400] or 'clean'}\n```")
    except Exception:
        pass
    try:
        mp4s = sorted(PROJECT_ROOT.glob("GELEM/**/*.mp4"),
                      key=lambda p: p.stat().st_mtime, reverse=True)[:5]
        for p in mp4s:
            size = p.stat().st_size / 1_048_576
            lines.append(f"• {p.name} ({size:.1f}MB)")
    except Exception:
        pass
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Button callbacks ──────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"query.answer() failed: {e}")

    parts  = query.data.split("|", 1)
    action = parts[0]
    pid    = parts[1] if len(parts) > 1 else ""

    logger.info(f"Callback: action={action} pid={pid}")

    try:
        # Bridge approvals (YES/NO from telegram_bridge.send_approval)
        if action in ("YES", "NO"):
            _write_approval(action, query.data)
            await query.edit_message_text(f"{'Approved' if action == 'YES' else 'Rejected'} — Claude Code notified.")
            return

        # Ofer pressed Run in the Magnific app (free: Unlimited applies only in the UI).
        # Collect the 4 ads in the background: run_collect.bat -> collect_queue.md.
        if action == "boardrun":
            import orchestrator
            slug = orchestrator.resolve_cb(pid)
            if not orchestrator.claim_collect(slug):
                try:
                    await query.message.reply_text("כבר אוסף / כבר טופל - לא מפעיל שוב.")
                except Exception:
                    pass
                return
            try:
                subprocess.Popen(["cmd", "/c", str(Path(__file__).parent / "run_collect.bat")],
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception as e:
                orchestrator.set_status(slug, "board_ready")
                logger.error(f"run_collect launch failed: {e}")
                await query.edit_message_text(f"⚠️ לא הצלחתי להפעיל את האיסוף: {e}")
                return
            await query.edit_message_text(
                f"👍 קיבלתי. אוסף את 4 המודעות של {slug.split('/')[-1]} ושולח לבחירה בעוד כמה דקות.")
            return

        # Ad A/B/C/D winner pick (from orchestrator.send_ad_choice). pid = "<slug-or-token>|A".
        if action == "adpick":
            slug, _, choice = pid.rpartition("|")
            import orchestrator
            slug = orchestrator.resolve_cb(slug)
            ok, info = orchestrator.record_choice(slug, choice)
            msg = (f"✅ נבחר {choice} - המודעה נכנסת לתור הפרסום 🎬"
                   if ok else f"⚠️ {info}")
            try:
                await query.edit_message_caption(caption=msg, parse_mode="Markdown")
            except Exception:
                await query.edit_message_text(text=msg, parse_mode="Markdown")
            return

        product   = taste_engine.get_pending(pid)
        url       = product.get("url", pid)
        title     = product.get("title", url)
        image_url = product.get("image_url", "")
        commission= product.get("commission", "")
        domain    = product.get("domain", taste_engine.get_domain(url))

        logger.info(f"Product: {title[:50]} | url={url[:60]}")

        if action == "ok":
            taste_engine.record_approval(url, title,
                                         image_url=image_url,
                                         commission=commission,
                                         domain=domain)
            taste_engine.remove_pending(pid)
            new_caption = f"✅ *נוסף לטעם שלך*\n🖤 {title[:60]}"
            try:
                await query.edit_message_caption(caption=new_caption, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"edit_message_caption failed ({e}), trying edit_message_text")
                await query.edit_message_text(text=new_caption, parse_mode="Markdown")

        elif action == "no":
            taste_engine.record_rejection(url, title)
            taste_engine.remove_pending(pid)
            new_caption = f"❌ *נדחה*\n{title[:60]}"
            try:
                await query.edit_message_caption(caption=new_caption, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"edit_message_caption failed ({e}), trying edit_message_text")
                await query.edit_message_text(text=new_caption, parse_mode="Markdown")

        elif action == "open":
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"🔗 [פתח מוצר]({url})",
                parse_mode="Markdown"
            )

        elif action == "user_ok":
            taste_engine.record_approval(url, title)
            taste_engine.remove_pending(pid)
            await query.edit_message_text(
                text=f"✅ נוסף לפרופיל הטעם שלך!\n🖤 {title[:60]}",
                parse_mode="Markdown"
            )

        elif action == "user_no":
            taste_engine.remove_pending(pid)
            await query.edit_message_text(text="⏭️ דילוג")

    except Exception as e:
        logger.error(f"Callback handler error: {e}", exc_info=True)
        try:
            await query.edit_message_text(text=f"⚠️ שגיאה: {str(e)[:100]}")
        except Exception:
            pass


# ── Photo handler — reference images → Mia taste flywheel ───────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.message.chat_id != CHAT_ID:
        return

    photo = update.message.photo[-1]  # largest available size
    tg_file = await context.bot.get_file(photo.file_id)

    TASTE_REFS.mkdir(parents=True, exist_ok=True)
    fname = f"ref_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    dest  = TASTE_REFS / fname
    await tg_file.download_to_drive(str(dest))

    _write_inbox({"type": "photo_reference", "path": str(dest)})

    # First: if a just-approved product is waiting for its image (e.g. AliExpress
    # where auto-download was blocked), use this photo as its source.jpg.
    try:
        product_title = taste_engine.attach_photo_to_pending(str(dest))
    except Exception as e:
        logger.warning(f"attach_photo_to_pending failed: {e}")
        product_title = ""
    if product_title:
        name, _, fname = product_title.partition("|")
        which = "תמונה ראשית (source)" if fname == "source.jpg" else f"תמונה נוספת ({fname})"
        await update.message.reply_text(
            f"🖤 {which} נשמרה לספרייה:\n{name[:70]}\n"
            f"אפשר להעלות עוד זוויות, או להמשיך למוצר הבא."
        )
        return

    # Run Mia Vision analysis on the reference
    reply = f"📸 Reference saved: {fname}\n"
    try:
        if str(MIA_ROOT) not in sys.path:
            sys.path.insert(0, str(MIA_ROOT))
        from capabilities.taste_learn import analyze_reference  # type: ignore
        analysis = analyze_reference(str(dest), "liked")
        reply += f"🎨 {analysis[:280]}"
    except Exception as e:
        reply += f"⚠️ Vision analysis unavailable: {e}"

    await update.message.reply_text(reply)

    # Update BUS so orchestrator knows taste was updated
    try:
        with open(str(BOLD_BUS), encoding="utf-8") as f:
            bus = json.load(f)
        bus.setdefault("context", {})["taste_updated"] = datetime.now().isoformat()
        bus["updated_by"] = "telegram_bot"
        with open(str(BOLD_BUS), "w", encoding="utf-8") as f:
            json.dump(bus, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── User URL messages ─────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.message.chat_id != CHAT_ID:
        return

    text = update.message.text or ""
    urls = URL_RE.findall(text)

    # Write ALL messages to inbox for Claude Code
    _write_inbox({"type": "message", "text": text})

    # "next" / "הבא" → advance photo attachment to the next waiting product
    if text.strip().lower() in ("הבא", "next", "מוצר הבא", "הבא!"):
        taste_engine.set_photo_target(None)
        await update.message.reply_text("⏭️ עברתי למוצר הבא — העלה עכשיו את התמונות שלו.")
        return

    if not urls:
        return  # non-URL text: just saved to inbox, no taste action

    for url in urls[:3]:
        # Try to fetch page title
        title = url
        try:
            r = _req.get(url, timeout=6,
                         headers={"User-Agent": "Mozilla/5.0"},
                         allow_redirects=True)
            m = re.search(r'<title[^>]*>([^<]+)</title>', r.text, re.IGNORECASE)
            if m:
                title = m.group(1).strip()[:100]
        except Exception:
            pass

        import hashlib
        pid = hashlib.md5(url.encode()).hexdigest()[:6]
        taste_engine.save_pending(pid, url, title)

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ הוסף לטעם שלי", callback_data=f"user_ok|{pid}"),
            InlineKeyboardButton("⏭️ דלג",            callback_data=f"user_no|{pid}")
        ]])

        await update.message.reply_text(
            f"🔍 *{title}*\n🔗 {url[:80]}\n\nנוסיף לפרופיל הטעם שלך?",
            parse_mode="Markdown",
            reply_markup=keyboard
        )


# ── Main ──────────────────────────────────────────────────────────────

def build_app():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("taste",  cmd_taste))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("run",    cmd_run))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Chat(CHAT_ID) & ~filters.COMMAND,
        handle_message
    ))
    app.add_handler(MessageHandler(
        filters.PHOTO & filters.Chat(CHAT_ID),
        handle_photo
    ))
    app.add_error_handler(on_error)
    return app


def main():
    if not BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set in .env")
        sys.exit(1)

    if not acquire_single_instance():
        logger.warning("Another bot instance is already running — exiting (prevents 409).")
        print("Another instance is already running. Exiting.")
        sys.exit(0)

    # Supervisor loop — if run_polling ever returns/raises (network death,
    # transient error), rebuild and restart in-process with backoff.
    # This makes the bot survive without depending on an external restarter.
    backoff = 5
    while True:
        try:
            logger.info("TheGothicVault Bot — starting polling")
            print("TheGothicVault Bot — running (Ctrl+C to stop)")
            app = build_app()
            app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
            )
            # Clean return = intentional stop (e.g. Ctrl+C) — exit loop
            logger.info("Polling returned cleanly — shutting down.")
            break
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt — shutting down.")
            break
        except Exception as e:
            logger.error(f"Polling crashed: {type(e).__name__}: {str(e)[:200]} — "
                         f"restarting in {backoff}s", exc_info=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)  # cap at 5 min
        else:
            backoff = 5


if __name__ == "__main__":
    main()
