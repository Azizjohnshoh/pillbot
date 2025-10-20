#!/usr/bin/env python3
# pill_bot_pro_render.py
# PillBot PRO Render Edition
# Features: keep-alive, restart notification, daily health report, error alerts,
# backups, owner commands, resilient async loop, aiosqlite storage, cron scheduler.
# DOES NOT contain secrets — set BOT_TOKEN and OWNER_ID in Render environment variables.

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, date
import aiosqlite
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from gtts import gTTS
import aiohttp
from aiohttp import web
import traceback
import sys

# ------------- CONFIG -------------
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID") or os.getenv("OWNER_CHAT_ID") or "0")
TIMEZONE = os.getenv("TZ", "Asia/Tashkent")
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "pillbot_pro.db")
VOICE_FILE = "voice.ogg"
DAILY_REPORT_HOUR = int(os.getenv("DAILY_REPORT_HOUR", "9"))  # owner's local time hour (24h)
BACKUP_HOUR = int(os.getenv("BACKUP_HOUR", "3"))  # daily backup hour
KEEP_ALIVE_INTERVAL = int(os.getenv("KEEP_ALIVE_INTERVAL", "600"))  # seconds

if not BOT_TOKEN:
    raise SystemExit("Environment variable BOT_TOKEN is not set. Please set it in Render or env.")

# ------------- Logging -------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("PillBotPRO")

# ------------- DB helpers -------------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                hhmm TEXT NOT NULL,
                label TEXT DEFAULT 'dori',
                tz TEXT DEFAULT ?,
                active INTEGER DEFAULT 1
            )
        """, (TIMEZONE,))
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER,
                user_id INTEGER,
                chat_id INTEGER,
                date TEXT, -- YYYY-MM-DD
                time TEXT, -- HH:MM
                label TEXT,
                status TEXT, -- scheduled / taken / skipped
                created_at TEXT
            )
        """)
        await db.commit()

async def add_schedule_db(user_id, chat_id, hhmm, label, tz=TIMEZONE):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO schedules (user_id, chat_id, hhmm, label, tz) VALUES (?,?,?,?,?)",
            (user_id, chat_id, hhmm, label, tz),
        )
        await db.commit()
        return cur.lastrowid

async def list_schedules_db(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, hhmm, label FROM schedules WHERE user_id=?", (user_id,))
        return await cur.fetchall()

async def get_schedule_db(schedule_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, user_id, chat_id, hhmm, label, tz FROM schedules WHERE id=?", (schedule_id,))
        return await cur.fetchone()

async def remove_schedule_db(schedule_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM schedules WHERE id=? AND user_id=?", (schedule_id, user_id))
        await db.commit()

async def insert_event(schedule_id, user_id, chat_id, hhmm, label):
    now = datetime.now(pytz.timezone(TIMEZONE))
    d = now.strftime("%Y-%m-%d")
    created = now.isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO events (schedule_id, user_id, chat_id, date, time, label, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (schedule_id, user_id, chat_id, d, hhmm, label, "scheduled", created),
        )
        await db.commit()

async def mark_last_event(schedule_id, status):
    now = datetime.now(pytz.timezone(TIMEZONE))
    d = now.strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id FROM events WHERE schedule_id=? AND date=? ORDER BY id DESC LIMIT 1", (schedule_id, d))
        row = await cur.fetchone()
        if row:
            eid = row[0]
            await db.execute("UPDATE events SET status=? WHERE id=?", (status, eid))
            await db.commit()
            return True
    return False

async def get_events_for_date(d):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT time, label, status FROM events WHERE date=? ORDER BY time", (d,))
        return await cur.fetchall()

# ------------- Keyboard -------------
def make_keyboard(schedule_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ICHDIM ✅", callback_data=f"took:{schedule_id}")],
        [InlineKeyboardButton("KEYINGA QOLDIRISH ⏰", callback_data=f"snooze:{schedule_id}")],
    ])

# ------------- Voice helper -------------
def tts_create(text, filename=VOICE_FILE):
    try:
        tts = gTTS(text=text, lang="uz")
        tts.save(filename)
        return filename
    except Exception as e:
        logger.warning("gTTS failed: %s", e)
        return None

# ------------- Send reminder -------------
async def send_voice_and_text(app, schedule_row):
    try:
        sid, user_id, chat_id, hhmm, label, tz = schedule_row
    except Exception:
        logger.exception("Bad schedule row")
        return
    try:
        await insert_event(sid, user_id, chat_id, hhmm, label)
    except Exception:
        logger.exception("insert_event failed")
    try:
        voice = None
        try:
            voice = tts_create(f"{label}ni ichish vaqti keldi!")
            if voice:
                with open(voice, "rb") as vf:
                    await app.bot.send_voice(chat_id=chat_id, voice=vf)
        except Exception:
            logger.exception("Sending voice failed, fallback to text")
            await app.bot.send_message(chat_id=chat_id, text=f"Dorini ichish vaqti: {label}")
        # then send text with buttons
        text = f"🕐 DORI VAQTI: {label}\n\nAgar ichgan bo'lsangiz, 'ICHDIM ✅' tugmasini bosing."
        await app.bot.send_message(chat_id=chat_id, text=text, reply_markup=make_keyboard(sid))
    finally:
        if os.path.exists(VOICE_FILE):
            try:
                os.remove(VOICE_FILE)
            except:
                pass

# ------------- Scheduler reload -------------
scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))

async def reload_jobs(app):
    rows = await aiosqlite.connect(DB_PATH)
    async with rows as db:
        cur = await db.execute("SELECT id, user_id, chat_id, hhmm, label, tz FROM schedules WHERE active=1")
        schedules = await cur.fetchall()
    for row in schedules:
        sid, user_id, chat_id, hhmm, label, tz = row
        hh, mm = map(int, hhmm.split(":"))
        trigger = CronTrigger(hour=hh, minute=mm, timezone=pytz.timezone(tz))
        # careful closure capture
        def make_job(r):
            return lambda: asyncio.create_task(send_voice_and_text(app, r))
        scheduler.add_job(make_job(row), trigger, id=f"reminder_{sid}", replace_existing=True)

# ------------- Command handlers -------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! PillBot PRO ishga tushdi. /qoshish HH:MM nomi — dori qo'shish")

async def cmd_qoshish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Masalan: /qoshish 09:00 VitaminC")
        return
    hhmm = context.args[0]
    label = " ".join(context.args[1:]) if len(context.args) > 1 else "dori"
    try:
        hh, mm = map(int, hhmm.split(":"))
        assert 0 <= hh < 24 and 0 <= mm < 60
    except:
        await update.message.reply_text("Notogri format. Masalan: 08:30")
        return
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    sid = await add_schedule_db(user_id, chat_id, hhmm, label, TIMEZONE)
    # add job
    trigger = CronTrigger(hour=hh, minute=mm, timezone=pytz.timezone(TIMEZONE))
    scheduler.add_job(lambda: asyncio.create_task(send_voice_and_text(context.application, (sid, user_id, chat_id, hhmm, label, TIMEZONE))), trigger, id=f"reminder_{sid}")
    await update.message.reply_text(f"Eslatma qo'shildi: {hhmm} — {label} (ID: {sid})")

async def cmd_royxat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await list_schedules_db(update.effective_user.id)
    if not rows:
        await update.message.reply_text("Hozircha eslatma yo'q.")
        return
    text = "\n".join([f"ID {r[0]}: {r[1]} — {r[2]}" for r in rows])
    await update.message.reply_text(text)

async def cmd_ochirish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Masalan: /ochirish 1")
        return
    try:
        sid = int(context.args[0])
    except:
        await update.message.reply_text("ID raqam bo'lishi kerak.")
        return
    await remove_schedule_db(sid, update.effective_user.id)
    try:
        scheduler.remove_job(f"reminder_{sid}")
    except Exception:
        pass
    await update.message.reply_text(f"Eslatma o'chirildi (ID {sid})")

async def cmd_ozgartirish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Masalan: /ozgartirish 1 VitaminD")
        return
    try:
        sid = int(context.args[0])
    except:
        await update.message.reply_text("ID raqam bo'lishi kerak.")
        return
    new_label = " ".join(context.args[1:])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE schedules SET label=? WHERE id=? AND user_id=?", (new_label, sid, update.effective_user.id))
        await db.commit()
    await update.message.reply_text(f"ID {sid} nomi o'zgartirildi: {new_label}")

# owner-only admin commands
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    # basic status
    now = datetime.now(pytz.timezone(TIMEZONE))
    text = f"📊 PillBot PRO status\nTime: {now.isoformat()}\nScheduler jobs: {len(scheduler.get_jobs())}\nDB: {DB_PATH}"
    await update.message.reply_text(text)

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    # send today's report immediately
    await send_daily_report(context.application)

async def cmd_reload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    # remove all jobs then reload
    for j in scheduler.get_jobs():
        try:
            j.remove()
        except:
            pass
    await reload_jobs(context.application)
    await update.message.reply_text("Scheduler qayta yuklandi.")

# ------------- Callback handler -------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("took:"):
        sid = int(data.split(":",1)[1])
        ok = await mark_last_event(sid, "taken")
        if ok:
            await query.edit_message_text("Yaxshi! Ichilgan ✅")
        else:
            await query.edit_message_text("Yozuv topilmadi.")
    elif data.startswith("snooze:"):
        sid = int(data.split(":",1)[1])
        await mark_last_event(sid, "skipped")
        row = await get_schedule_db(sid)
        if not row:
            await query.edit_message_text("Eslatma topilmadi.")
            return
        run_at = datetime.now(pytz.timezone(TIMEZONE)) + timedelta(minutes=10)
        scheduler.add_job(lambda: asyncio.create_task(send_voice_and_text(context.application, row)), 'date', run_date=run_at, id=f"snooze_{sid}_{int(run_at.timestamp())}")
        await query.edit_message_text("Eslatma 10 daqiqaga qoldirildi. ⏰")

# ------------- Daily report & health -------------
async def send_daily_report(app):
    tz = pytz.timezone(TIMEZONE)
    today = datetime.now(tz).date().strftime("%Y-%m-%d")
    rows = await get_events_for_date(today)
    if not rows:
        text = "📅 Bugungi hisobot: hech qanday eslatma yo'q."
    else:
        taken = [f"{r[1]} ({r[0]})" for r in rows if r[2]=="taken"]
        skipped = [f"{r[1]} ({r[0]})" for r in rows if r[2]=="skipped"]
        scheduled = [f"{r[1]} ({r[0]})" for r in rows if r[2]=="scheduled"]
        text = "📅 Bugungi hisobot:\n\n"
        text += f"✅ Ichilgan: {', '.join(taken) if taken else '—'}\n"
        text += f"⏰ Qoldirilgan: {', '.join(skipped) if skipped else '—'}\n"
        text += f"🔔 Rejalashtirilgan: {', '.join(scheduled) if scheduled else '—'}\n"
        text += f"\n💊 Jami: {len(rows)}"
    try:
        await app.bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception:
        logger.exception("send_daily_report failed")

# ------------- Backup DB daily -------------
async def backup_db(app):
    try:
        if os.path.exists(DB_PATH):
            # send file to owner
            await app.bot.send_document(chat_id=OWNER_ID, document=open(DB_PATH, "rb"), filename=f"backup_{int(time.time())}.db")
            logger.info("Database backup sent to owner.")
    except Exception:
        logger.exception("backup_db failed")

# ------------- Error handling wrapper -------------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    # catch unhandled exceptions in handlers
    try:
        err = context.error
        trace = "".join(traceback.format_exception(None, err, err.__traceback__))
        logger.error("Handler error: %s", trace)
        if OWNER_ID:
            text = f"⚠️ Bot error:\n{str(err)[:800]}\n\nTrace:\n{trace[:1400]}"
            try:
                await context.application.bot.send_message(chat_id=OWNER_ID, text=text)
            except Exception:
                logger.exception("Failed to send error to owner")
    except Exception:
        logger.exception("on_error failed")

# ------------- Keep-alive & fake server -------------
async def fake_server():
    async def handle(request):
        return web.Response(text="PillBot PRO alive")
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("🌐 Fake server running on port %s", PORT)

async def keep_alive_ping():
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                await session.get(f"http://localhost:{PORT}", timeout=10)
                logger.debug("Keepalive ping ok")
        except Exception as e:
            logger.warning("Keepalive ping failed: %s", e)
        await asyncio.sleep(KEEP_ALIVE_INTERVAL)

# ------------- Startup notify -------------
async def notify_restart(app):
    try:
        await app.bot.send_message(chat_id=OWNER_ID, text=f"🔁 PillBot restarted — {datetime.now(pytz.timezone(TIMEZONE)).isoformat()}")
    except Exception:
        logger.exception("notify_restart failed")

# ------------- Main -------------
async def main():
    await init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    # add handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("qoshish", cmd_qoshish))
    application.add_handler(CommandHandler("royxat", cmd_royxat))
    application.add_handler(CommandHandler("ochirish", cmd_ochirish))
    application.add_handler(CommandHandler("ozgartirish", cmd_ozgartirish))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("report", cmd_report))
    application.add_handler(CommandHandler("reload", cmd_reload))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_error_handler(on_error)

# ------------- Entry point with event-loop safety -------------
if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(main())
        else:
            loop.run_until_complete(main())
    except RuntimeError:
        asyncio.run(main())
