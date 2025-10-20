import asyncio
import logging
import aiosqlite
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from gtts import gTTS
import os
import httpx

# ---------------- CONFIG ---------------- #
BOT_TOKEN = "8274061170:AAEvxZdkIAI5bz10cgpHu6DO2ze8-rc1H3Y"
OWNER_ID = 51662933
DB_FILE = "pillbot.db"
TIMEZONE = "Asia/Tashkent"
BACKUP_HOUR = 23  # бэкап в 23:00 по Ташкенту
KEEPALIVE_PORT = 10000

# ---------------- LOGGING ---------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------- DATABASE ---------------- #
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            time TEXT
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT
        )
        """)
        await db.commit()

# ---------------- CORE FUNCTIONS ---------------- #
async def add_reminder(user_id: int, text: str, time_str: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO reminders (user_id, text, time) VALUES (?, ?, ?)", (user_id, text, time_str))
        await db.commit()

async def get_reminders():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT user_id, text, time FROM reminders") as cursor:
            return await cursor.fetchall()

async def delete_reminder(user_id: int, text: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM reminders WHERE user_id = ? AND text = ?", (user_id, text))
        await db.commit()

# ---------------- TELEGRAM HANDLERS ---------------- #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Assalomu alaykum! Men PillBot Ultra Pro Max!\n"
                                    "💊 /add — dori eslatmasi qo‘shish\n"
                                    "🗓 /report — kunlik hisobot\n"
                                    "🧠 /help — yordam")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💊 Dori eslatmasi uchun /add so‘ng matn va vaqt yozing.\n"
                                    "Masalan: /add Paratsetamol 20:00")

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("❗ Format: /add <nomi> <soat:daq>")
            return
        text = " ".join(args[:-1])
        time_str = args[-1]
        await add_reminder(update.effective_user.id, text, time_str)
        await update.message.reply_text(f"✅ Eslatma saqlandi: {text} ⏰ {time_str}")
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {e}")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reminders = await get_reminders()
    if not reminders:
        await update.message.reply_text("📭 Hozircha eslatmalar yo‘q.")
        return
    msg = "\n".join([f"👤 {r[0]} — 💊 {r[1]} ⏰ {r[2]}" for r in reminders])
    await update.message.reply_text(f"📋 Kunlik hisobot:\n\n{msg}")

# ---------------- DAILY JOBS ---------------- #
async def daily_report(app: Application):
    reminders = await get_reminders()
    if not reminders:
        return
    msg = "🗓 *Kunlik hisobot:*\n\n" + "\n".join([f"💊 {r[1]} ⏰ {r[2]}" for r in reminders])
    await app.bot.send_message(chat_id=OWNER_ID, text=msg, parse_mode="Markdown")

async def daily_backup(app: Application):
    backup_file = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    try:
        import shutil
        shutil.copy(DB_FILE, backup_file)
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("INSERT INTO backups (timestamp) VALUES (?)", (datetime.now().isoformat(),))
            await db.commit()
        await app.bot.send_message(chat_id=OWNER_ID, text=f"🧩 Backup tayyorlandi: `{backup_file}`", parse_mode="Markdown")
    except Exception as e:
        await app.bot.send_message(chat_id=OWNER_ID, text=f"⚠️ Backup xatolik: {e}")

# ---------------- KEEPALIVE SERVER ---------------- #
async def start_keepalive():
    async def handle_request(reader, writer):
        response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nPillBot Ultra running!"
        writer.write(response)
        await writer.drain()
        writer.close()
    server = await asyncio.start_server(handle_request, "0.0.0.0", KEEPALIVE_PORT)
    logger.info(f"🌐 KeepAlive server running on {KEEPALIVE_PORT}")
    async with server:
        await server.serve_forever()

async def ping_uptime():
    while True:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.get("https://pillbot-yourname.onrender.com")
        except Exception as e:
            logger.warning(f"Uptime ping failed: {e}")
        await asyncio.sleep(300)

# ---------------- MAIN ---------------- #
async def main():
    await init_db()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("report", report))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(daily_report, CronTrigger(hour=21), args=[app])
    scheduler.add_job(daily_backup, CronTrigger(hour=BACKUP_HOUR), args=[app])
    scheduler.start()

    await app.bot.send_message(chat_id=OWNER_ID, text="🚀 PillBot Ultra Pro Max ishga tushdi!")

    await asyncio.gather(
        start_keepalive(),
        ping_uptime(),
        app.run_polling()
    )

# ---------- ENTRY POINT with loop safety ---------- #
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()

    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(main())
        else:
            loop.run_until_complete(main())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
