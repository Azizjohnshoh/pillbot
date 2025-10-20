#!/usr/bin/env python3
# PillBot ULTRA PRO MAX v2
# Features:
# - Natural input parsing (simple) for "I take Paracetamol at 08:00" style messages
# - Conversation-based add flow with buttons (no need for /add)
# - Inline buttons for quick actions (ICHDIM / SNOOZE)
# - Daily text + voice (gTTS) report to owner
# - Daily backup: .db zip sent to owner
# - Keepalive server + uptime pings
# - Owner-only admin commands (status, backup, restart, logs, report)
# - Safe event-loop handling for Render / Python 3.13
# - SQLite w/ auto reconnect
# - Basic gamification: streak increment when user marks "ICHDIM"
#
# Env vars:
# BOT_TOKEN (or TELEGRAM_TOKEN) - required
# OWNER_ID - your numeric TG id
# TZ (default Asia/Tashkent)
# PORT (keepalive)
# RENDER_EXTERNAL_URL (optional) - used for uptime pings

import os
import sys
import re
import time
import zipfile
import random
import logging
import asyncio
import traceback
from datetime import datetime, timedelta
import aiosqlite
import pytz
import aiohttp
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
)
from gtts import gTTS

# Optional: nest_asyncio to be safe on Render
try:
    import nest_asyncio
    nest_asyncio.apply()
except Exception:
    pass

# -------------- CONFIG --------------
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID") or os.getenv("OWNER_CHAT_ID") or 0)
TZ = os.getenv("TZ", "Asia/Tashkent")
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "pillbot_ultra_v2.db")
DAILY_REPORT_HOUR = int(os.getenv("DAILY_REPORT_HOUR", "21"))
DAILY_BACKUP_HOUR = int(os.getenv("DAILY_BACKUP_HOUR", "23"))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")  # e.g. myapp.onrender.com
VOICE_LANG = os.getenv("VOICE_LANG", "uz")

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN not set in environment (BOT_TOKEN or TELEGRAM_TOKEN). Exiting.")
    raise SystemExit("BOT_TOKEN missing")

if OWNER_ID == 0:
    print("WARNING: OWNER_ID not set or 0 — owner-only features disabled.")

# -------------- LOGGING --------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PillBotULTRAv2")

# -------------- DB helpers --------------
async def get_db(retries=3, delay=1.0):
    last = None
    for i in range(retries):
        try:
            db = await aiosqlite.connect(DB_PATH)
            await db.execute("PRAGMA journal_mode=WAL;")
            return db
        except Exception as e:
            last = e
            logger.warning("DB connect failed (%s/%s): %s", i+1, retries, e)
            await asyncio.sleep(delay)
    logger.exception("DB connection permanently failed")
    raise last

async def init_db():
    db = await get_db()
    await db.execute(f"""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            hhmm TEXT,
            label TEXT,
            tz TEXT DEFAULT '{TZ}',
            streak INTEGER DEFAULT 0,
            last_taken_date TEXT,
            active INTEGER DEFAULT 1
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_id INTEGER,
            user_id INTEGER,
            chat_id INTEGER,
            date TEXT,
            time TEXT,
            label TEXT,
            status TEXT,
            created_at TEXT
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            created_at TEXT
        )
    """)
    await db.commit()
    await db.close()

# -------------- utilities --------------
def normalize_time_str(s: str):
    """Return HH:MM if possible, else None"""
    s = s.strip()
    m = re.search(r'([01]?\d|2[0-3])[:.]([0-5]\d)', s)
    if m:
        hh = int(m.group(1)); mm = int(m.group(2))
        return f"{hh:02d}:{mm:02d}"
    return None

def extract_time_and_label(text: str):
    """
    Try to extract time and label from a natural sentence.
    Returns (label, hhmm) or (None, None)
    Simple heuristics: find HH:MM and treat rest as label.
    """
    hhmm = normalize_time_str(text)
    if hhmm:
        # remove time token from text
        label = re.sub(r'([01]?\d|2[0-3])[:.]([0-5]\d)', '', text).strip(" ,.-")
        if label == "":
            label = "dori"
        return label, hhmm
    # also try "soat 8" or "8 da"
    m = re.search(r'\b([01]?\d|2[0-3])\s*(soat|:|da|:)\b', text)
    if m:
        hh = int(m.group(1))
        hhmm = f"{hh:02d}:00"
        label = re.sub(r'\b([01]?\d|2[0-3])\s*(soat|:|da)\b', '', text).strip()
        return (label or "dori"), hhmm
    return None, None

def tts_save(text: str, filename="voice.ogg", lang=VOICE_LANG):
    try:
        tts = gTTS(text=text, lang=lang)
        tts.save(filename)
        return filename
    except Exception as e:
        logger.warning("gTTS failed: %s", e)
        return None

# -------------- scheduler & jobs --------------
scheduler = AsyncIOScheduler(timezone=pytz.timezone(TZ))

async def reload_jobs(app: Application):
    # remove old reminder jobs
    for j in scheduler.get_jobs():
        if j.id.startswith("reminder_"):
            try:
                scheduler.remove_job(j.id)
            except Exception:
                pass
    # load from DB
    db = await get_db()
    cur = await db.execute("SELECT id, user_id, chat_id, hhmm, label, tz FROM schedules WHERE active=1")
    rows = await cur.fetchall()
    await db.close()
    for row in rows:
        sid, user_id, chat_id, hhmm, label, tz = row
        try:
            hh, mm = map(int, hhmm.split(":"))
        except Exception:
            logger.warning("Bad time for schedule %s: %s", sid, hhmm)
            continue
        trigger = CronTrigger(hour=hh, minute=mm, timezone=pytz.timezone(tz))
        # closure to capture row
        def make_job(r=row):
            async def job():
                await send_reminder(app, r)
            return job
        scheduler.add_job(make_job(), trigger, id=f"reminder_{sid}", replace_existing=True)
    logger.info("Reloaded %s reminder jobs", len(rows))

# -------------- sending reminders --------------
async def insert_event(schedule_id, user_id, chat_id, hhmm, label):
    now = datetime.now(pytz.timezone(TZ))
    d = now.strftime("%Y-%m-%d")
    created = now.isoformat()
    db = await get_db()
    await db.execute(
        "INSERT INTO events (schedule_id, user_id, chat_id, date, time, label, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (schedule_id, user_id, chat_id, d, hhmm, label, "scheduled", created),
    )
    await db.commit()
    await db.close()

async def send_reminder(app: Application, schedule_row):
    # schedule_row: (id, user_id, chat_id, hhmm, label, tz)
    try:
        sid, user_id, chat_id, hhmm, label, tz = schedule_row
    except Exception:
        logger.exception("Bad schedule row")
        return
    try:
        await insert_event(sid, user_id, chat_id, hhmm, label)
    except Exception:
        logger.exception("insert_event failed")
    # prepare phrase
    phrase = random.choice([
        f"Dorini ichish vaqti: {label}",
        f"Eslatma: {label}ni qabul qilish kerak",
        f"{label}ni hozir qabul qiling"
    ])
    fn = tts_save(phrase)
    try:
        if fn:
            with open(fn, "rb") as f:
                await app.bot.send_voice(chat_id=chat_id, voice=f)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💊 ICHDIM", callback_data=f"took:{sid}")],
            [InlineKeyboardButton("⏰ KEYINGA QOLDIRISH", callback_data=f"snooze:{sid}")]
        ])
        await app.bot.send_message(chat_id=chat_id, text=f"💊 DORI VAQTI: {label}\nSoat: {hhmm}", reply_markup=keyboard)
    except Exception:
        logger.exception("Failed to send reminder")
    finally:
        try:
            if fn and os.path.exists(fn):
                os.remove(fn)
        except:
            pass

# -------------- daily report & backup --------------
async def get_events_for_date(date_str):
    db = await get_db()
    cur = await db.execute("SELECT time, label, status FROM events WHERE date=? ORDER BY time", (date_str,))
    rows = await cur.fetchall()
    await db.close()
    return rows

async def send_daily_report(app: Application):
    tz = pytz.timezone(TZ)
    today = datetime.now(tz).strftime("%Y-%m-%d")
    rows = await get_events_for_date(today)
    if not rows:
        text = f"📅 Bugungi hisobot ({today}): hech qanday voqea yo'q."
    else:
        taken = [f"{r[1]} ({r[0]})" for r in rows if r[2] == "taken"]
        skipped = [f"{r[1]} ({r[0]})" for r in rows if r[2] == "skipped"]
        scheduled = [f"{r[1]} ({r[0]})" for r in rows if r[2] == "scheduled"]
        text = "📅 Bugungi hisobot:\n\n"
        text += f"✅ Ichilgan: {', '.join(taken) if taken else '—'}\n"
        text += f"⏰ Qoldirilgan: {', '.join(skipped) if skipped else '—'}\n"
        text += f"🔔 Rejalashtirilgan: {', '.join(scheduled) if scheduled else '—'}\n"
    try:
        await app.bot.send_message(chat_id=OWNER_ID, text=text)
        # TTS summary
        tts_text = "Bugungi hisobot. " + ("ichilganlar mavjud." if any(r[2]=="taken" for r in rows) else "hech nima yo'q.")
        fn = tts_save(tts_text)
        if fn:
            with open(fn, "rb") as f:
                await app.bot.send_voice(chat_id=OWNER_ID, voice=f)
            os.remove(fn)
    except Exception:
        logger.exception("send_daily_report failed")

async def backup_db_and_send(app: Application):
    try:
        if os.path.exists(DB_PATH):
            zipname = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            with zipfile.ZipFile(zipname, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(DB_PATH, arcname=os.path.basename(DB_PATH))
            db = await get_db()
            await db.execute("INSERT INTO backups (filename, created_at) VALUES (?, ?)", (zipname, datetime.now().isoformat()))
            await db.commit()
            await db.close()
            with open(zipname, "rb") as f:
                await app.bot.send_document(chat_id=OWNER_ID, document=f)
            os.remove(zipname)
            logger.info("Backup sent")
    except Exception:
        logger.exception("backup failed")

# -------------- keepalive + uptime monitor --------------
async def start_keepalive_server():
    async def handle(request):
        return web.Response(text="PillBot ULTRA PRO MAX v2 alive")
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("KeepAlive HTTP server started on port %s", PORT)

async def uptime_monitor_loop():
    url = f"https://{RENDER_EXTERNAL_URL}" if RENDER_EXTERNAL_URL else f"http://localhost:{PORT}"
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=10) as r:
                    logger.debug("Uptime ping %s -> %s", url, r.status)
        except Exception as e:
            logger.warning("Uptime ping failed: %s", e)
        await asyncio.sleep(900)

# -------------- Conversation handler for adding --------------
ASK_LABEL, ASK_TIME = range(2)

def add_keyboard_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Dori qoʻshish", callback_data="add_flow")],
        [InlineKeyboardButton("📋 Hisobot", callback_data="report_now")]
    ])

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "👋 Salom! Men PillBot ULTRA PRO MAX v2.\n"
        "Siz dori qoʻshishni xohlasangiz — tugmani bosing yoki yozing:\n"
        "Misol: 'Paratsetamol 20:00' yoki 'Men Paratsetamolni 08:00 da ichaman'.",
        reply_markup=add_keyboard_main()
    )

async def begin_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Qaysi dori nomini qoʻshmoqchisiz? (masalan: Paratsetamol)")
    return ASK_LABEL

async def ask_time_after_label(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data['label_temp'] = text
    await update.message.reply_text("Soat nechida eslatma berilsin? (format HH:MM, masalan 20:00)")
    return ASK_TIME

async def save_from_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    label = context.user_data.get('label_temp', 'dori')
    time_str = normalize_time_str(update.message.text.strip())
    if not time_str:
        await update.message.reply_text("Noto'g'ri format. Iltimos HH:MM yozing (masalan 20:00).")
        return ASK_TIME
    # save schedule
    db = await get_db()
    cur = await db.execute("INSERT INTO schedules (user_id, chat_id, hhmm, label, tz) VALUES (?,?,?,?,?)",
                           (update.effective_user.id, update.effective_chat.id, time_str, label, TZ))
    await db.commit()
    sid = cur.lastrowid
    await db.close()
    # add job immediately
    hh, mm = map(int, time_str.split(":"))
    trigger = CronTrigger(hour=hh, minute=mm, timezone=pytz.timezone(TZ))
    scheduler.add_job(lambda: asyncio.create_task(send_reminder(context.application, (sid, update.effective_user.id, update.effective_chat.id, time_str, label, TZ))),
                      trigger, id=f"reminder_{sid}", replace_existing=True)
    await update.message.reply_text(f"✅ Eslatma saqlandi: {label} ⏰ {time_str}", reply_markup=add_keyboard_main())
    context.user_data.pop('label_temp', None)
    return ConversationHandler.END

async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Qoʻshish bekor qilindi.", reply_markup=add_keyboard_main())
    return ConversationHandler.END

# -------------- natural input message handler --------------
async def natural_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    # simple trigger words
    if re.search(r'\b(add|qo\'sh|eslat|dori|напомн|помни)\b', text, re.IGNORECASE):
        # try to extract time and label
        label, hhmm = extract_time_and_label(text)
        if hhmm:
            # store
            db = await get_db()
            cur = await db.execute("INSERT INTO schedules (user_id, chat_id, hhmm, label, tz) VALUES (?,?,?,?,?)",
                                   (update.effective_user.id, update.effective_chat.id, hhmm, label, TZ))
            await db.commit()
            sid = cur.lastrowid
            await db.close()
            # add scheduler job
            try:
                hh, mm = map(int, hhmm.split(":"))
                trigger = CronTrigger(hour=hh, minute=mm, timezone=pytz.timezone(TZ))
                scheduler.add_job(lambda: asyncio.create_task(send_reminder(context.application, (sid, update.effective_user.id, update.effective_chat.id, hhmm, label, TZ))),
                                  trigger, id=f"reminder_{sid}")
            except Exception:
                logger.exception("failed to schedule autodetected reminder")
            await update.message.reply_text(f"✅ Men tushundim — {label} ⏰ {hhmm} ga eslatma qoʻshildi.", reply_markup=add_keyboard_main())
            return
        # if not extracted, begin dialog
        await update.message.reply_text("Siz dori qoʻshmoqchisiz — keling, men savol beraman.")
        await update.message.reply_text("Qaysi dori nomini yozing:")
        return ASK_LABEL
    # otherwise ignore or reply help
    # if user wrote only time+label (e.g. "Paratsetamol 08:00"), try again
    label, hhmm = extract_time_and_label(text)
    if hhmm:
        db = await get_db()
        cur = await db.execute("INSERT INTO schedules (user_id, chat_id, hhmm, label, tz) VALUES (?,?,?,?,?)",
                               (update.effective_user.id, update.effective_chat.id, hhmm, label, TZ))
        await db.commit()
        sid = cur.lastrowid
        await db.close()
        try:
            hh, mm = map(int, hhmm.split(":"))
            trigger = CronTrigger(hour=hh, minute=mm, timezone=pytz.timezone(TZ))
            scheduler.add_job(lambda: asyncio.create_task(send_reminder(context.application, (sid, update.effective_user.id, update.effective_chat.id, hhmm, label, TZ))),
                              trigger, id=f"reminder_{sid}")
        except Exception:
            logger.exception("failed to schedule quick parsed reminder")
        await update.message.reply_text(f"✅ Eslatma qoʻshildi: {label} ⏰ {hhmm}", reply_markup=add_keyboard_main())
        return
    # fallback: show main keyboard
    await update.message.reply_text("Iltimos, nimadir yozing yoki tugmani bosing.", reply_markup=add_keyboard_main())

# -------------- callback (buttons) handler --------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    if data == "add_flow":
        await q.message.reply_text("Qaysi dori nomini qoʻshmoqchisiz?")
        return ASK_LABEL
    if data == "report_now":
        await q.message.reply_text("Hisobot yuborilmoqda...")
        await send_daily_report(context.application)
        return
    if data.startswith("took:"):
        sid = int(data.split(":", 1)[1])
        # mark event for today as taken
        ok = await mark_event_taken_and_update_streak(sid)
        if ok:
            await q.edit_message_text("💊 Ajoyib! Siz dorini ichdingiz ✅")
        else:
            await q.edit_message_text("Ma'lumot topilmadi.")
        return
    if data.startswith("snooze:"):
        sid = int(data.split(":", 1)[1])
        await mark_event_skipped(sid)
        # schedule a one-off job after 10 minutes
        row = await get_schedule_row(sid)
        if not row:
            await q.edit_message_text("Eslatma topilmadi.")
            return
        run_at = datetime.now(pytz.timezone(TZ)) + timedelta(minutes=10)
        scheduler.add_job(lambda: asyncio.create_task(send_reminder(context.application, row)), 'date', run_date=run_at, id=f"snooze_{sid}_{int(run_at.timestamp())}")
        await q.edit_message_text("⏰ Eslatma 10 daqiqaga qoldirildi.")
        return

# -------------- event marking helpers --------------
async def get_schedule_row(sid):
    db = await get_db()
    cur = await db.execute("SELECT id, user_id, chat_id, hhmm, label, tz FROM schedules WHERE id=?", (sid,))
    row = await cur.fetchone()
    await db.close()
    return row

async def mark_event_taken_and_update_streak(schedule_id):
    # find the most recent event for today
    now = datetime.now(pytz.timezone(TZ))
    today = now.strftime("%Y-%m-%d")
    db = await get_db()
    cur = await db.execute("SELECT id FROM events WHERE schedule_id=? AND date=? ORDER BY id DESC LIMIT 1", (schedule_id, today))
    row = await cur.fetchone()
    if not row:
        await db.close()
        return False
    eid = row[0]
    await db.execute("UPDATE events SET status=? WHERE id=?", ("taken", eid))
    # update streak in schedules
    cur = await db.execute("SELECT last_taken_date, streak FROM schedules WHERE id=?", (schedule_id,))
    srow = await cur.fetchone()
    last, streak = srow if srow else (None, 0)
    today_s = today
    if last == today_s:
        # already counted
        pass
    else:
        yest = (datetime.now(pytz.timezone(TZ)) - timedelta(days=1)).strftime("%Y-%m-%d")
        if last == yest:
            streak = (streak or 0) + 1
        else:
            streak = 1
        await db.execute("UPDATE schedules SET last_taken_date=?, streak=? WHERE id=?", (today_s, streak, schedule_id))
    await db.commit()
    await db.close()
    return True

async def mark_event_skipped(schedule_id):
    now = datetime.now(pytz.timezone(TZ))
    today = now.strftime("%Y-%m-%d")
    db = await get_db()
    cur = await db.execute("SELECT id FROM events WHERE schedule_id=? AND date=? ORDER BY id DESC LIMIT 1", (schedule_id, today))
    row = await cur.fetchone()
    if not row:
        # insert a skipped event
        created = now.isoformat()
        await db.execute("INSERT INTO events (schedule_id, user_id, chat_id, date, time, label, status, created_at) SELECT id, user_id, chat_id, ?, hhmm, label, 'skipped', ? FROM schedules WHERE id=?", (today, created, schedule_id))
    else:
        eid = row[0]
        await db.execute("UPDATE events SET status=? WHERE id=?", ("skipped", eid))
    await db.commit()
    await db.close()

# -------------- owner / admin commands --------------
def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user and user.id == OWNER_ID:
            return await func(update, context)
        else:
            try:
                await update.effective_message.reply_text("Bu buyruq faqat admin uchun.")
            except:
                pass
    return wrapper

@owner_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = scheduler.get_jobs()
    await update.message.reply_text(f"Jobs: {len(jobs)}\nTZ: {TZ}\nDB: {DB_PATH}")

@owner_only
async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Backup yaratilmoqda...")
    await backup_db_and_send(context.application)

@owner_only
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bugungi hisobot yuborilmoqda...")
    await send_daily_report(context.application)

@owner_only
async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot qayta ishga tushirilmoqda...")
    try:
        await context.application.shutdown()
        await context.application.stop()
    except Exception:
        logger.exception("Restart error")
    # ensure process exit so Render restarts container
    os._exit(0)

# -------------- error handler --------------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    trace = "".join(traceback.format_exception(None, err, err.__traceback__))
    logger.error("Handler error: %s", trace)
    if OWNER_ID:
        try:
            # send shortened trace
            await context.application.bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Bot error:\n{str(err)[:800]}")
        except Exception:
            pass

# -------------- application start --------------
async def main():
    await init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation handler for add flow
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(begin_add_cb, pattern="^add_flow$")],
        states={
            ASK_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_time_after_label)],
            ASK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_from_conversation)],
        },
        fallbacks=[CommandHandler('cancel', cancel_add)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, natural_text_handler))

    # Owner admin
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("backup", cmd_backup))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.add_error_handler(on_error)

    # scheduler jobs
    if not scheduler.running:
        scheduler.start()
    await reload_jobs(app)
    # daily jobs
    scheduler.add_job(lambda: asyncio.create_task(send_daily_report(app)), CronTrigger(hour=DAILY_REPORT_HOUR, minute=0, timezone=pytz.timezone(TZ)), id="daily_report", replace_existing=True)
    scheduler.add_job(lambda: asyncio.create_task(backup_db_and_send(app)), CronTrigger(hour=DAILY_BACKUP_HOUR, minute=5, timezone=pytz.timezone(TZ)), id="daily_backup", replace_existing=True)

    # keepalive + uptime monitor
    asyncio.create_task(start_keepalive_server())
    asyncio.create_task(uptime_monitor_loop())

    # notify owner
    try:
        await app.bot.send_message(chat_id=OWNER_ID, text=f"🔁 PillBot ULTRA PRO MAX v2 started — {datetime.now(pytz.timezone(TZ)).isoformat()}")
    except Exception:
        logger.exception("notify failed")

    await app.run_polling()

# -------------- ENTRY POINT --------------
if __name__ == "__main__":
    # safe loop handling for Render / Python 3.13
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(main())
        else:
            loop.run_until_complete(main())
    except RuntimeError:
        # fallback
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
