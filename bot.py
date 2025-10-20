
import os
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    print("No TELEGRAM_TOKEN; polling fallback will not start.")
    exit(0)
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    greeting = "👋 Assalomu alaykum! Dori eslatish botiga hush kelibsiz!\nMen sizga dorilarni o‘z vaqtida ichishni eslataman.\nQuyidagi menyudan kerakli bo‘limni tanlang:"
    await update.message.reply_text(greeting)
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.run_polling()
