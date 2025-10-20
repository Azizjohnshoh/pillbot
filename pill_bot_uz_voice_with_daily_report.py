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
import httpx
from gtts import gTTS

# ============ CONFIG ============
TOKEN = os.getenv("8274061170:AAEvxZdkIAI5bz10cgpHu6DO2ze8-rc1H3Y")
OWNER_CHAT_ID = int(os.getenv("51662933", "0"))
KEEP_ALIVE_PORT = int(os.getenv("PORT", 10000))

# ============ LOGGING ============
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ TELEGRAM HANDLERS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! 💊 PillBot ishga tushdi. /add bilan eslatma qo‘shing!")

async def add_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Iltimos, dori nomi va vaqtni kiriting. Masalan: /add soat 9:00 vitamin C")
        return
    await update.message.reply_text(f"Eslatma qo‘shildi: {text}")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Noma’lum buyruq. Faqat /start va /add ishlaydi.")

# ============ JOBS ============

async def daily_report():
    if OWNER_CHAT_ID != 0:
        app = Application.builder().token(TOKEN).build()
        await app.bot.send_message(chat_id=OWNER_CHAT_ID, text="📅 Bugungi dori hisobotini tekshiring!")
        logger.info("Daily report yuborildi.")

# ============ KEEP-ALIVE ============

async def keep_alive():
    import aiohttp
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                await session.get(f"http://localhost:{KEEP_ALIVE_PORT}")
                logger.info("Keep-alive ping sent")
        except Exception as e:
            logger.warning(f"Keep-alive error: {e}")
        await asyncio.sleep(600)  # 10 minut

# ============ FAKE SERVER (Render uchun) ============

async def fake_server():
    from aiohttp import web
    async def handle(request):
        return web.Response(text="OK - PillBot is alive 💊")
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", KEEP_ALIVE_PORT)
    await site.start()
    logger.info(f"🌐 Fake server running on port {KEEP_ALIVE_PORT}")

# ============ MAIN LOOP ============

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

    await app.run_polling()

# ============ ENTRY POINT (Render fix) ============

if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(main())
        else:
            loop.run_until_complete(main())
    except RuntimeError:
        asyncio.run(main())
