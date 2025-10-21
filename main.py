import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from database import init_db, get_reminders
from scheduler import start_scheduler
from utils import setup_logging

setup_logging()

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://pillbot-ultra-promax.onrender.com/webhook")
PORT = int(os.getenv("PORT", 10000))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💊 Dori qo‘shish", callback_data="add")],
        [InlineKeyboardButton("📋 Dorilarim", callback_data="list")],
        [InlineKeyboardButton("⚙️ Sozlamalar", callback_data="settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👋 Salom! Men sizga dorilarni eslataman.", reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "add":
        await query.edit_message_text("💊 Dori qo‘shish funksiyasi tez orada qo‘shiladi.")
    elif query.data == "list":
        reminders = await get_reminders(query.from_user.id)
        if not reminders:
            await query.edit_message_text("📭 Sizda hozircha hech qanday dori eslatmalari yo‘q.")
        else:
            text = "\n".join([f"💊 {r[1]} — {r[2]}" for r in reminders])
            await query.edit_message_text(f"Sizning dorilaringiz:\n{text}")
    elif query.data == "settings":
        await query.edit_message_text("⚙️ Sozlamalar: ovozli eslatmalar yoqilgan.")

async def main():
    await init_db()
    start_scheduler()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    await app.bot.set_webhook(url=WEBHOOK_URL)
    print("Webhook set:", WEBHOOK_URL)
    await app.run_webhook(listen="0.0.0.0", port=PORT, url_path="/webhook", webhook_url=WEBHOOK_URL)

if __name__ == "__main__":
    asyncio.run(main())
