"""
TheGothicVault Work Bot — Terminal + Claude AI via Telegram

Commands:
  /run <command>   — execute shell command in project root
  /status          — git status + recent GELEM output files
  /log [n]         — last N lines of work log (default 30)
  /clear           — clear conversation history with Claude
  /help            — this message

Free text → forwarded to Claude (claude-sonnet-4-6) with project context.

Run:
    cd E:/PROJECTS/thegothicvault/scripts
    python work_bot.py

Requires in .env:
    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_CHAT_ID=...
    ANTHROPIC_API_KEY=...   ← add this line
"""
import sys
import os
import subprocess
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")

# Load .env from scripts dir
load_dotenv(Path(__file__).parent / ".env")

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)

BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID     = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

PROJECT_ROOT = Path("E:/PROJECTS/thegothicvault")
GELEM_ROOT   = PROJECT_ROOT / "GELEM"
WORK_LOG     = PROJECT_ROOT / "scripts" / "work_bot.log"
MEMORY_FILE  = Path("C:/Users/ofera/.claude/projects/E--PROJECTS-thegothicvault/memory/MEMORY.md")

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.WARNING
)

# Rolling conversation history for Claude
_history: list[dict] = []
MAX_HISTORY = 16  # turns (user+assistant pairs)


# ── Context loader ─────────────────────────────────────────────────────────────

def load_project_context() -> str:
    parts = []

    # 1. Memory index
    try:
        mem = MEMORY_FILE.read_text(encoding="utf-8")
        parts.append(f"## Memory Index\n{mem[:2000]}")
    except Exception:
        pass

    # 2. Most recently modified project.md across GELEM products
    try:
        logs = sorted(
            GELEM_ROOT.glob("*/edit/project.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        for log in logs[:2]:
            content = log.read_text(encoding="utf-8")[-2000:]
            parts.append(f"## {log.parent.parent.name} — project.md (tail)\n{content}")
    except Exception:
        pass

    # 3. Recent git log
    try:
        r = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "log", "--oneline", "-8"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            parts.append(f"## Recent commits\n{r.stdout.strip()}")
    except Exception:
        pass

    return "\n\n".join(parts)


# ── Claude integration ─────────────────────────────────────────────────────────

async def ask_claude(user_text: str) -> str:
    if not ANTHROPIC_KEY:
        return "❌ ANTHROPIC_API_KEY not set in .env — add it and restart the bot."

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

        _history.append({"role": "user", "content": user_text})

        # Trim history
        while len(_history) > MAX_HISTORY * 2:
            _history.pop(0)

        context = load_project_context()
        system = (
            "You are Claude, remote assistant for TheGothicVault gothic fashion affiliate business. "
            "The owner is messaging you via Telegram (mobile). "
            "Keep replies SHORT and actionable — bullet points, no fluff. "
            "You have full project context below.\n\n"
            f"{context}"
        )

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            messages=list(_history)
        )

        reply = response.content[0].text
        _history.append({"role": "assistant", "content": reply})
        return reply

    except Exception as e:
        return f"❌ Claude error: {e}"


# ── Log writer ─────────────────────────────────────────────────────────────────

def log_event(tag: str, text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{tag}] {text}\n"
    try:
        with open(WORK_LOG, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split_long(text: str, limit: int = 4000) -> list[str]:
    """Split text into ≤4096-char chunks for Telegram."""
    chunks = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


async def _send(update: Update, text: str):
    for chunk in _split_long(text):
        await update.message.reply_text(chunk)


def _guard(update: Update) -> bool:
    """Reject messages from unauthorized chats."""
    return update.message and update.message.chat_id == CHAT_ID


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _guard(update):
        return
    await update.message.reply_text(
        "🖤 *TheGothicVault Work Bot*\n\n"
        "*/run* `<command>` — הרץ פקודת טרמינל\n"
        "*/status* — git status + קבצים אחרונים\n"
        "*/log* `[n]` — n שורות אחרונות מהלוג (ברירת מחדל 30)\n"
        "*/clear* — נקה היסטוריית שיחה עם Claude\n"
        "*/help* — עזרה\n\n"
        "טקסט חופשי → Claude AI עם קונטקסט פרויקט",
        parse_mode="Markdown"
    )


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _guard(update):
        return

    raw = update.message.text or ""
    cmd = raw[len("/run"):].strip()
    if not cmd:
        await update.message.reply_text("שימוש: /run <command>")
        return

    log_event("RUN", cmd)
    await update.message.reply_text(f"⚙️ מריץ: `{cmd[:80]}`", parse_mode="Markdown")

    try:
        r = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(PROJECT_ROOT),
            encoding="utf-8",
            errors="replace"
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        combined = ""
        if out:
            combined += f"stdout:\n{out}"
        if err:
            combined += f"\nstderr:\n{err}"
        if not combined:
            combined = "(no output)"

        status = "✅" if r.returncode == 0 else f"❌ exit {r.returncode}"
        reply = f"{status}\n```\n{combined[-3000:]}\n```"
        log_event("OUT", f"exit={r.returncode} | {combined[:200]}")
        await _send(update, reply)

    except subprocess.TimeoutExpired:
        await update.message.reply_text("⏱️ timeout אחרי 120 שניות")
    except Exception as e:
        await update.message.reply_text(f"❌ שגיאה: {e}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _guard(update):
        return

    lines = ["📊 *סטטוס פרויקט*\n"]

    # git status
    try:
        r = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "status", "--short"],
            capture_output=True, text=True, timeout=5
        )
        lines.append(f"**Git:**\n```\n{r.stdout.strip()[:500] or 'clean'}\n```")
    except Exception as e:
        lines.append(f"Git error: {e}")

    # Recent GELEM output files (mp4, jpg, png — last 24h)
    try:
        mp4s = sorted(
            PROJECT_ROOT.glob("GELEM/**/*.mp4"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:6]
        if mp4s:
            lines.append("**Recent MP4s:**")
            for p in mp4s:
                size_mb = p.stat().st_size / 1_048_576
                mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%m-%d %H:%M")
                lines.append(f"  • {p.name} ({size_mb:.1f}MB) [{mtime}]")
    except Exception:
        pass

    await _send(update, "\n".join(lines))


async def cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _guard(update):
        return

    raw = update.message.text or ""
    parts = raw.split()
    n = 30
    if len(parts) > 1:
        try:
            n = int(parts[1])
        except ValueError:
            pass

    if not WORK_LOG.exists():
        await update.message.reply_text("אין לוג עדיין.")
        return

    lines = WORK_LOG.read_text(encoding="utf-8").splitlines()
    tail = "\n".join(lines[-n:])
    await _send(update, f"```\n{tail}\n```")


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _guard(update):
        return
    global _history
    _history = []
    await update.message.reply_text("🗑️ היסטוריית שיחה נוקתה.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _guard(update):
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    log_event("MSG", text[:200])
    await update.message.reply_text("🤔 שואל את Claude...")

    reply = await ask_claude(text)
    log_event("CLAUDE", reply[:200])
    await _send(update, reply)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set in .env")
        sys.exit(1)

    print(f"🖤 TheGothicVault Work Bot starting...")
    print(f"   Project root: {PROJECT_ROOT}")
    print(f"   Chat ID:      {CHAT_ID}")
    print(f"   Claude API:   {'✅ configured' if ANTHROPIC_KEY else '❌ missing (add ANTHROPIC_API_KEY to .env)'}")
    print(f"   Log:          {WORK_LOG}")
    print()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("start",  cmd_help))
    app.add_handler(CommandHandler("run",    cmd_run))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("log",    cmd_log))
    app.add_handler(CommandHandler("clear",  cmd_clear))
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Chat(CHAT_ID) & ~filters.COMMAND,
        handle_text
    ))

    log_event("START", f"Work bot started. Claude: {'yes' if ANTHROPIC_KEY else 'no'}")
    print("Running — Ctrl+C to stop\n")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
