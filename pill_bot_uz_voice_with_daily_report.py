import asyncio
import logging
import os
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import aiohttp

# =============================
# 🔧 Render-safe environment load
# =============================
def get_env_var(key: str, default=None):
    value = os.environ.get(key)
    if not value or value.strip() == "":
        logging.error(f"❌ Missing environment variable: {key}")
        return default
    return value.strip()

TOKEN = get_env_var("8274061170:AAEvxZdkIAI5bz10cgpHu6DO2ze8-rc1H3Y")
OWNER_CHAT_ID = int(get_env_var("51662933", "0"))
PORT = int(get_env_var("PORT", "10000"))

if not TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN not found! Please set it in Render environment.")

# =============================
# Logging setup
# =============================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("PillBot")

# =============================
# Telegram Handlers
# =============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💊 PillBot ishga tushdi! /add bilan eslatma qo‘shing.")

async def add_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Iltimos, dori nomi va vaqtni kiriting. Masalan: /add 9:00 Vitamin C")
        return
    await update.message.reply_text(f"Eslatma qo‘shildi: {text}")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Noma’lum buyruq. Faqat /start va /add ishlaydi.")

# =============================
# Daily Report Job
# =============================
async def daily_report():
    if OWNER_CHAT_ID != 0:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                    json={"chat_id": OWNER_CHAT_ID, "text": "📅 Bugungi dori hisobotini tekshiring!"}
                ) as resp:
                    logger.info(f"Daily report yuborildi: {resp.status}")
        except Exception as e:
            logger.error(f"Daily report error: {e}")

# =============================
# Keep-alive ping (Render Free)
# =============================
async def keep_alive():
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                await session.get(f"http://localhost:{PORT}")
                logger.info("Keep-alive ping sent ✅")
        except Exception as e:
            logger.warning(f"Keep-alive error: {e}")
        await asyncio.sleep(600)

# =============================
# Fake web server (Render requirement)
# =============================
async def fake_server():
    from aiohttp import web
    async def handle(request):
        return web.Response(text="✅ PillBot is alive and healthy.")
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🌐 Fake server started on port {PORT}")

# =============================
# Main Bot App
# =============================
async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_reminder))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(daily_report, "interval", hours=24)
    scheduler.start()

    asyncio.create_task(fake_server())
    asyncio.create_task(keep_alive())

    await app.run_polling(allowed_updates=Update.ALL_TYPES)

# =============================
# Entry Point
# =============================
if __name__ == "__main__":
    asyncio.run(main())
