#!/usr/bin/env python3
# pill_bot_uz_voice_fixed_latin_full_windows_auto_restart_notify_alert.py

import logging
import asyncio
import time
from datetime import datetime, timedelta
import aiosqlite
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)
from gtts import gTTS
import os
import sys
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

# --- SETTINGS ---
TELEGRAM_TOKEN = "8274061170:AAEvxZdkIAI5bz10cgpHu6DO2ze8-rc1H3Y"  # <-- your bot token
OWNER_CHAT_ID = 51662933  # <-- your Telegram ID (get via @userinfobot)
DEFAULT_TZ = "Asia/Tashkent"
REMIND_INTERVAL_MIN = 10
DB_PATH = "pillbot.db"
VOICE_TEXT = "Salom! Dorini ichish vaqti boldi."
VOICE_FILE = "voice.ogg"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone=pytz.timezone(DEFAULT_TZ))

# === DATABASE ===
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            hhmm TEXT NOT NULL,
            label TEXT DEFAULT 'dori',
            tz TEXT DEFAULT '{DEFAULT_TZ}',
            active INTEGER DEFAULT 1
        )
        """
        )
        await db.commit()


async def add_schedule(user_id, chat_id, hhmm, label, tz=DEFAULT_TZ):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO schedules (user_id, chat_id, hhmm, label, tz) VALUES (?,?,?,?,?)",
            (user_id, chat_id, hhmm, label, tz),
        )
        await db.commit()
        return cur.lastrowid


async def list_schedules(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, hhmm, label FROM schedules WHERE user_id=?", (user_id,)
        )
        return await cur.fetchall()


async def remove_schedule(schedule_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM schedules WHERE id=? AND user_id=?", (schedule_id, user_id)
        )
        await db.commit()


async def edit_schedule(schedule_id, user_id, new_label):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE schedules SET label=? WHERE id=? AND user_id=?",
            (new_label, schedule_id, user_id),
        )
        await db.commit()


async def get_schedule(schedule_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, user_id, chat_id, hhmm, label, tz FROM schedules WHERE id=?",
            (schedule_id,),
        )
        return await cur.fetchone()


async def load_all_schedules():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, user_id, chat_id, hhmm, label, tz FROM schedules WHERE active=1"
        )
        return await cur.fetchall()


# === BUTTONS ===
def make_keyboard(schedule_id):
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("ICHDIM ✅", callback_data=f"took:{schedule_id}")],
            [
                InlineKeyboardButton(
                    "KEYINGA QOLDIRISH ⏰", callback_data=f"snooze:{schedule_id}"
                )
            ],
        ]
    )


# === VOICE + TEXT MESSAGE ===
async def send_voice_and_text(app, schedule_row):
    sched_id, user_id, chat_id, hhmm, label, tz = schedule_row
    try:
        try:
            tts = gTTS(text=VOICE_TEXT, lang="uz")
            tts.save(VOICE_FILE)
            with open(VOICE_FILE, "rb") as voice:
                await app.bot.send_voice(chat_id=chat_id, voice=voice)
        except Exception:
            await app.bot.send_message(
                chat_id=chat_id, text="Salom! Dorini ichish vaqti boldi."
            )

        text = (
            f"🕐 DORINI ICHISH VAQTI BOLDI.\n"
            f"Agar ichgan bolsangiz, 'ICHDIM ✅' tugmasini bosing.\n\n"
            f"Dori nomi: {label}"
        )
        await app.bot.send_message(
            chat_id=chat_id, text=text, reply_markup=make_keyboard(sched_id)
        )
    except Exception as e:
        logger.exception("Failed to send reminder: %s", e)
    finally:
        if os.path.exists(VOICE_FILE):
            os.remove(VOICE_FILE)


# === COMMANDS ===
async def boshlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom! Men dorilarni vaqtida ichishni eslataman 🎙️💊\n\n"
        "Buyruqlar:\n"
        "/qoshish HH:MM nomi — yangi dori qoshish\n"
        "/royxat — barcha eslatmalarni korish\n"
        "/ozgartirish ID yangi_nom — dori nomini ozgartirish\n"
        "/ochirish ID — ochirish\n"
        "/yordam — yordam"
    )


async def yordam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await boshlash(update, context)


async def qoshish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Iltimos, vaqtni kiriting. Masalan: /qoshish 09:00 Vitamin C"
        )
        return
    hhmm = context.args[0]
    label = " ".join(context.args[1:]) if len(context.args) > 1 else "dori"
    try:
        hh, mm = map(int, hhmm.split(":"))
        assert 0 <= hh < 24 and 0 <= mm < 60
    except:
        await update.message.reply_text(
            "Notogri vaqt formati. Masalan: 08:30 yoki 21:45"
        )
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    schedule_id = await add_schedule(user_id, chat_id, hhmm, label)
    trigger = CronTrigger(hour=hh, minute=mm, timezone=pytz.timezone(DEFAULT_TZ))
    scheduler.add_job(
        lambda: asyncio.create_task(
            send_voice_and_text(
                context.application,
                (schedule_id, user_id, chat_id, hhmm, label, DEFAULT_TZ),
            )
        ),
        trigger,
        id=f"reminder_{schedule_id}",
    )
    await update.message.reply_text(f"Eslatma qoshildi: {hhmm} — {label} (ID: {schedule_id})")


async def royxat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = await list_schedules(user_id)
    if not rows:
        await update.message.reply_text("Hozircha hech qanday eslatma yoq.")
        return
    text = "\n".join([f"ID {r[0]}: {r[1]} — {r[2]}" for r in rows])
    await update.message.reply_text(text)


async def ochirish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Masalan: /ochirish 1")
        return
    try:
        sid = int(context.args[0])
    except:
        await update.message.reply_text("ID raqam bolishi kerak.")
        return
    user_id = update.effective_user.id
    await remove_schedule(sid, user_id)
    try:
        scheduler.remove_job(f"reminder_{sid}")
    except:
        pass
    await update.message.reply_text(f"Eslatma ochirildi (ID {sid})")


async def ozgartirish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Masalan: /ozgartirish 1 Vitamin D")
        return
    try:
        sid = int(context.args[0])
    except:
        await update.message.reply_text("ID raqam bolishi kerak.")
        return
    new_label = " ".join(context.args[1:])
    user_id = update.effective_user.id
    await edit_schedule(sid, user_id, new_label)
    await update.message.reply_text(
        f"ID {sid} uchun dori nomi ozgartirildi: {new_label}"
    )


# === BUTTON HANDLER ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("took:"):
        await query.edit_message_text("Yaxshi! Dorini ichganingiz yozib qoyildi ✅")
    elif data.startswith("snooze:"):
        sid = int(data.split(":", 1)[1])
        row = await get_schedule(sid)
        if not row:
            await query.edit_message_text("Bu eslatma mavjud emas.")
            return
        run_at = datetime.now(pytz.timezone(DEFAULT_TZ)) + timedelta(
            minutes=REMIND_INTERVAL_MIN
        )
        scheduler.add_job(
            lambda: asyncio.create_task(send_voice_and_text(context.application, row)),
            "date",
            run_date=run_at,
            id=f"snooze_{sid}_{int(run_at.timestamp())}",
        )
        await query.edit_message_text(
            f"Eslatma {REMIND_INTERVAL_MIN} daqiqaga qoldirildi. ⏰"
        )


# === LOAD JOBS ===
async def reload_jobs(app):
    rows = await load_all_schedules()
    for row in rows:
        sid, user_id, chat_id, hhmm, label, tz = row
        hh, mm = map(int, hhmm.split(":"))
        trigger = CronTrigger(hour=hh, minute=mm, timezone=pytz.timezone(tz))
        scheduler.add_job(
            lambda: asyncio.create_task(send_voice_and_text(app, row)),
            trigger,
            id=f"reminder_{sid}",
        )


# === TELEGRAM NOTIFICATIONS ===
async def notify_restart(bot):
    try:
        await bot.send_message(OWNER_CHAT_ID, "🔁 Bot qayta ishga tushdi — hammasi joyida!")
    except Exception:
        pass


async def notify_error(bot, error_text):
    try:
        await bot.send_message(
            OWNER_CHAT_ID, f"⚠️ Botda xatolik: {error_text}\n♻️ Qayta ishga tushmoqda..."
        )
    except Exception:
        pass


# === MAIN RUNNER ===
def run_bot():
    if TELEGRAM_TOKEN.startswith("REPLACE"):
        print("❗ Iltimos, TELEGRAM_TOKEN ni toldiring.")
        raise SystemExit(1)

    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("boshlash", boshlash))
    app.add_handler(CommandHandler("yordam", yordam))
    app.add_handler(CommandHandler("qoshish", qoshish))
    app.add_handler(CommandHandler("royxat", royxat))
    app.add_handler(CommandHandler("ochirish", ochirish))
    app.add_handler(CommandHandler("ozgartirish", ozgartirish))
    app.add_handler(CallbackQueryHandler(button_handler))

    scheduler.start()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    loop.run_until_complete(reload_jobs(app))
    loop.run_until_complete(notify_restart(app.bot))

    print("✅ Bot ishga tushdi — Telegram'da /boshlash deb yozing!")
    app.run_polling()


# === AUTO RESTART WRAPPER ===
if __name__ == "__main__":
    while True:
        with open("bot_restarts.log", "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Bot restarted\n")

        try:
            run_bot()
        except Exception as e:
            err_text = str(e)
            print(f"\n⚠️ Bot xatolik tufayli to'xtadi: {err_text}")
            print("♻️ 5 soniyadan keyin qayta ishga tushiriladi...")
            with open("bot_restarts.log", "a", encoding="utf-8") as f:
                f.write(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error: {err_text}\n"
                )

            try:
                import telegram
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                bot = telegram.Bot(token=TELEGRAM_TOKEN)
                loop.run_until_complete(notify_error(bot, err_text))
                loop.close()
            except Exception:
                pass

            time.sleep(5)
            continue
