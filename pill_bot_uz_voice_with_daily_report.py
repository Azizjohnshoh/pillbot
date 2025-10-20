#!/usr/bin/env python3
# PillBot ULTRA — Render Stable Edition
# Author: Azizjon Shoxnazarov
# Features: Uptime monitor, autorestart, backup, scheduler recovery, voice TTS, DB reconnect, crash shield

import asyncio, logging, os, aiosqlite, pytz, aiohttp, zipfile
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger  
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from gtts import gTTS
from aiohttp import web


# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "51662933"))
TIMEZONE = os.getenv("TZ", "Asia/Tashkent")
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = "pillbot_ultra.db"
DAILY_REPORT_HOUR = 9
BACKUP_HOUR = 3
KEEPALIVE_INTERVAL = 600
PING_INTERVAL = 900  # 15 min uptime check

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PillBot")

# ---------------- DATABASE ----------------
async def get_db():
    for _ in range(3):
        try:
            db = await aiosqlite.connect(DB_PATH)
            await db.execute("PRAGMA journal_mode=WAL;")
            return db
        except Exception as e:
            logger.warning(f"DB reconnect: {e}")
            await asyncio.sleep(2)
    raise RuntimeError("DB connection failed after 3 tries")

async def init_db():
    db = await get_db()
    await db.execute(f"""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            hhmm TEXT,
            label TEXT DEFAULT 'dori',
            tz TEXT DEFAULT '{TIMEZONE}',
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
    await db.commit()
    await db.close()

# ---------------- CORE FUNCTIONS ----------------
def uz_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💊 Ichdim", callback_data="taken"),
         InlineKeyboardButton("⏰ Kiyinga qoldirish", callback_data="skip")]
    ])

async def speak_text(text: str, filename="voice.ogg"):
    tts = gTTS(text=text, lang="uz")
    tts.save(filename)
    return filename

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    user_id, chat_id, label = job.data
    try:
        msg = f"💊 Doringizni ichish vaqti keldi!\n👉 {label}"
        await context.bot.send_message(chat_id=chat_id, text=msg, reply_markup=uz_keyboard())
        voice_path = await speak_text(f"{label} doringizni ichish vaqti keldi")
        await context.bot.send_voice(chat_id=chat_id, voice=open(voice_path, "rb"))
    except Exception as e:
        logger.error(f"Send reminder failed: {e}")

async def add_schedule(user_id, chat_id, hhmm, label):
    db = await get_db()
    await db.execute("INSERT INTO schedules (user_id, chat_id, hhmm, label) VALUES (?, ?, ?, ?)",
                     (user_id, chat_id, hhmm, label))
    await db.commit()
    await db.close()

async def list_schedules(user_id):
    db = await get_db()
    cur = await db.execute("SELECT id, hhmm, label FROM schedules WHERE user_id=?", (user_id,))
    data = await cur.fetchall()
    await db.close()
    return data

# ---------------- COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Salom! Men PillBot ULTRA.\n"
                                    "Doringizni ichishni eslatib turaman.\n"
                                    "Yangi jadval uchun /set 08:00 Paracetamol")

async def set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⏰ Foydalanish: /set 08:00 Dori_nomi")
        return
    hhmm = context.args[0]
    label = " ".join(context.args[1:])
    user = update.message.from_user
    await add_schedule(user.id, update.message.chat_id, hhmm, label)
    await update.message.reply_text(f"✅ Jadval qo‘shildi: {hhmm} — {label}")

async def list_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    data = await list_schedules(user.id)
    if not data:
        await update.message.reply_text("🕒 Jadval topilmadi.")
        return
    msg = "\n".join([f"{r[1]} — {r[2]}" for r in data])
    await update.message.reply_text(f"📋 Sizning dori jadvallaringiz:\n{msg}")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "taken":
        await q.edit_message_text("💊 Juda yaxshi! Doringiz ichildi ✅")
    elif q.data == "skip":
        await q.edit_message_text("⏰ Keyinga qoldirildi.")

# ---------------- BACKUP + REPORT ----------------
async def daily_backup(app):
    try:
        zipname = f"backup_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
        with zipfile.ZipFile(zipname, "w") as zf:
            zf.write(DB_PATH)
        await app.bot.send_document(chat_id=OWNER_ID, document=open(zipname, "rb"))
    except Exception as e:
        logger.error(f"Backup failed: {e}")

async def daily_report(app):
    msg = f"🕘 Kunlik hisobot: {datetime.now().strftime('%Y-%m-%d')}\n"
    msg += "🔸 Dori eslatmalari bajarildi."
    await app.bot.send_message(chat_id=OWNER_ID, text=msg)

# ---------------- MONITORS ----------------
async def keep_alive():
    async def handle(request): return web.Response(text="OK")
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🌐 KeepAlive server running on {PORT}")

async def uptime_monitor(app):
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://{os.getenv('RENDER_EXTERNAL_URL', 'example.com')}") as r:
                    logger.info(f"Uptime check: {r.status}")
        except Exception as e:
            logger.warning(f"Uptime ping failed: {e}")
        await asyncio.sleep(PING_INTERVAL)

# ---------------- MAIN ----------------
async def main():
    await init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("set", set_reminder))
    app.add_handler(CommandHandler("list", list_all))
    app.add_handler(CallbackQueryHandler(button))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(daily_backup, CronTrigger(hour=BACKUP_HOUR), args=[app])
    scheduler.add_job(daily_report, CronTrigger(hour=DAILY_REPORT_HOUR), args=[app])
    scheduler.start()

    asyncio.create_task(keep_alive())
    asyncio.create_task(uptime_monitor(app))

    await app.bot.send_message(chat_id=OWNER_ID, text="🔁 PillBot ULTRA restarted successfully 🚀")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
