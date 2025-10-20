import asyncio
import logging
import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from gtts import gTTS
import os
from datetime import datetime
import pytz
import http.server
import socketserver
import threading

# ------------------- CONFIG -------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or "YOUR_TELEGRAM_BOT_TOKEN"
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID") or "YOUR_OWNER_CHAT_ID"

DB_PATH = "pillbot.db"
TIMEZONE = pytz.timezone("Asia/Tashkent")

# ------------------- LOGGING -------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------- DATABASE -------------------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            time TEXT,
            text TEXT
        )
        """)
        await db.commit()

# ------------------- VOICE -------------------
async def speak_text(text, filename="voice.mp3"):
    tts = gTTS(text=text, lang="uz")
    tts.save(filename)
    return filename

# ------------------- COMMANDS -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! Bu PillBot. /add yordamida dori eslatmasini qo‘shing.")

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Foydalanish: /add HH:MM dori_nomi")
        return

    time = context.args[0]
    text = " ".join(context.args[1:])
    user_id = update.message.chat_id

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO reminders (user_id, time, text) VALUES (?, ?, ?)", (user_id, time, text))
        await db.commit()

    await update.message.reply_text(f"Eslatma qo‘shildi: {time} - {text}")

async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT time, text FROM reminders WHERE user_id = ?", (user_id,)) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await update.message.reply_text("Sizda hozircha eslatmalar yo‘q.")
        return

    msg = "\n".join([f"{time} - {text}" for time, text in rows])
    await update.message.reply_text("Sizning eslatmalaringiz:\n" + msg)

# ------------------- DAILY REPORT -------------------
async def daily_report(app):
    text = "📋 Bugungi dori eslatmalari:\n"
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, time, text FROM reminders") as cursor:
            reminders = await cursor.fetchall()

    if not reminders:
        text += "Hech qanday eslatma topilmadi."
    else:
        for user_id, time, rtext in reminders:
            text += f"👤 User {user_id}: {time} - {rtext}\n"

    await app.bot.send_message(chat_id=OWNER_CHAT_ID, text=text)

# ------------------- SCHEDULER -------------------
async def check_reminders(app):
    now = datetime.now(TIMEZONE).strftime("%H:%M")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, text FROM reminders WHERE time = ?", (now,)) as cursor:
            reminders = await cursor.fetchall()

    for user_id, text in reminders:
        voice_file = await speak_text(f"{text}ni ichish vaqti keldi!")
        await app.bot.send_voice(chat_id=user_id, voice=open(voice_file, "rb"))
        os.remove(voice_file)

# ------------------- KEEP ALIVE -------------------
def keep_alive():
    PORT = int(os.getenv("PORT", 10000))
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"🌐 Fake server running on port {PORT}")
        httpd.serve_forever()

# ------------------- MAIN -------------------
async def main():
    await init_db()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("list", list_reminders))

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(check_reminders, "interval", minutes=1, args=[app])
    scheduler.add_job(daily_report, "cron", hour=8, minute=0, args=[app])
    scheduler.start()

    threading.Thread(target=keep_alive, daemon=True).start()

    print("✅ Bot ishga tushdi — Telegram'da /start deb yozing!")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
