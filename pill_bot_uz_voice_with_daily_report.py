#!/usr/bin/env python3
# pill_bot_uz_voice_with_daily_report.py
# Uzbek pill bot with daily 21:00 report (Latin only)

import logging
import asyncio
import time
from datetime import datetime, timedelta, date
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
TELEGRAM_TOKEN = "REPLACE_WITH_YOUR_TOKEN"  # <-- put your bot token here
OWNER_CHAT_ID = 123456789  # <-- replace with your Telegram user id
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
        # schedules table (existing)
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
        # events table: stores each reminder occurrence and its status
        await db.execute(
            """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_id INTEGER,
            user_id INTEGER,
            chat_id INTEGER,
            date TEXT,         -- YYYY-MM-DD
            time TEXT,         -- HH:MM
            label TEXT,
            status TEXT,       -- scheduled / taken / skipped
            created_at TEXT
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
        cur = await db.execute("SELECT id, hhmm, label FROM schedules WHERE user_id=?", (user_id,))
        return await cur.fetchall()


async def remove_schedule(schedule_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM schedules WHERE id=? AND user_id=?", (schedule_id, user_id))
        await db.commit()


async def edit_schedule(schedule_id, user_id, new_label):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE schedules SET label=? WHERE id=? AND user_id=?", (new_label, schedule_id, user_id))
        await db.commit()


async def get_schedule(schedule_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, user_id, chat_id, hhmm, label, tz FROM schedules WHERE id=?", (schedule_id,))
        return await cur.fetchone()


async def load_all_schedules():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, user_id, chat_id, hhmm, label, tz FROM schedules WHERE active=1")
        return await cur.fetchall()


# === EVENTS helpers ===
async def insert_event(schedule_id, user_id, chat_id, hhmm, label):
    now = datetime.now(pytz.timezone(DEFAULT_TZ))
    d = now.strftime("%Y-%m-%d")
    t = hhmm  # hh:mm from schedule
    created = now.isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO events (schedule_id, user_id, chat_id, date, time, label, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (schedule_id, user_id, chat_id, d, t, label, "scheduled", created),
        )
        await db.commit()


async def mark_last_event_taken(schedule_id):
    now = datetime.now(pytz.timezone(DEFAULT_TZ))
    d = now.strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id FROM events WHERE schedule_id=? AND date=? ORDER BY id DESC LIMIT 1", (schedule_id, d)
        )
        row = await cur.fetchone()
        if row:
            eid = row[0]
            await db.execute("UPDATE events SET status=? WHERE id=?", ("taken", eid))
            await db.commit()
            return True
    return False


async def mark_last_event_skipped(schedule_id):
    now = datetime.now(pytz.timezone(DEFAULT_TZ))
    d = now.strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id FROM events WHERE schedule_id=? AND date=? ORDER BY id DESC LIMIT 1", (schedule_id, d)
        )
        row = await cur.fetchone()
        if row:
            eid = row[0]
            await db.execute("UPDATE events SET status=? WHERE id=?", ("skipped", eid))
            await db.commit()
            return True
    return False


# === BUTTONS ===
def make_keyboard(schedule_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ICHDIM ✅", callback_data=f"took:{schedule_id}")],
        [InlineKeyboardButton("KEYINGA QOLDIRISH ⏰", callback_data=f"snooze:{schedule_id}")]
    ])


# === VOICE + TEXT MESSAGE ===
async def send_voice_and_text(app, schedule_row):
    sched_id, user_id, chat_id, hhmm, label, tz = schedule_row
    try:
        # create event record (scheduled)
        try:
            await insert_event(sched_id, user_id, chat_id, hhmm, label)
        except Exception:
            logger.exception("Could not insert event record")

        # Try gTTS; if fails, send text-only
        try:
            tts = gTTS(text=VOICE_TEXT, lang="uz")
            tts.save(VOICE_FILE)
            with open(VOICE_FILE, "rb") as voice:
                await app.bot.send_voice(chat_id=chat_id, voice=voice)
        except Exception:
            await app.bot.send_message(chat_id=chat_id, text="Salom! Dorini ichish vaqti boldi.")

        text = (
            f"🕐 DORINI ICHISH VAQTI BOLDI.\n"
            f"Agar ichgan bolsangiz, 'ICHDIM ✅' tugmasini bosing.\n\n"
            f"Dori nomi: {label}"
        )
        await app.bot.send_message(chat_id=chat_id, text=text, reply_markup=make_keyboard(sched_id))
    except Exception as e:
        logger.exception("Failed to send reminder: %s", e)
    finally:
        if os.path.exists(VOICE_FILE):
            try:
                os.remove(VOICE_FILE)
            except Exception:
                pass


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
        await update.message.reply_text("Iltimos, vaqtni kiriting. Masalan: /qoshish 09:00 Vitamin C")
        return
    hhmm = context.args[0]
    label = " ".join(context.args[1:]) if len(context.args) > 1 else "dori"
    try:
        hh, mm = map(int, hhmm.split(":"))
        assert 0 <= hh < 24 and 0 <= mm < 60
    except:
        await update.message.reply_text("Notogri vaqt formati. Masalan: 08:30 yoki 21:45")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    schedule_id = await add_schedule(user_id, chat_id, hhmm, label)
    trigger = CronTrigger(hour=hh, minute=mm, timezone=pytz.timezone(DEFAULT_TZ))
    # schedule job - use create_task to run async send
    scheduler.add_job(
        lambda: asyncio.create_task(send_voice_and_text(context.application, (schedule_id, user_id, chat_id, hhmm, label, DEFAULT_TZ))),
        trigger, id=f"reminder_{schedule_id}"
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
    except Exception:
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
    await update.message.reply_text(f"ID {sid} uchun dori nomi ozgartirildi: {new_label}")


# === BUTTON HANDLER ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("took:"):
        sid = int(data.split(":", 1)[1])
        ok = await mark_last_event_taken(sid)
        if ok:
            await query.edit_message_text("Yaxshi! Dorini ichganingiz yozib qoyildi ✅")
        else:
            await query.edit_message_text("Qayta urinib ko'ring — yozuv topilmadi.")
    elif data.startswith("snooze:"):
        sid = int(data.split(":", 1)[1])
        # mark current as skipped
        await mark_last_event_skipped(sid)
        row = await get_schedule(sid)
        if not row:
            await query.edit_message_text("Bu eslatma mavjud emas.")
            return
        # schedule snooze in REMIND_INTERVAL_MIN minutes
        run_at = datetime.now(pytz.timezone(DEFAULT_TZ)) + timedelta(minutes=REMIND_INTERVAL_MIN)
        # create a job that will call send_voice_and_text later
        scheduler.add_job(
            lambda: asyncio.create_task(send_voice_and_text(context.application, row)),
            'date',
            run_date=run_at,
            id=f"snooze_{sid}_{int(run_at.timestamp())}"
        )
        await query.edit_message_text(f"Eslatma {REMIND_INTERVAL_MIN} daqiqaga qoldirildi. ⏰")


# === DAILY REPORT ===
async def send_daily_report(app):
    # prepare today's date range in DEFAULT_TZ
    tz = pytz.timezone(DEFAULT_TZ)
    today = datetime.now(tz).date()
    d = today.strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT time, label, status FROM events WHERE date=? ORDER BY time", (d,))
        rows = await cur.fetchall()

    if not rows:
        text = "📅 Bugun hech qanday eslatma yo'q."
    else:
        taken = [f"{r[1]} ({r[0]})" for r in rows if r[2] == "taken"]
        skipped = [f"{r[1]} ({r[0]})" for r in rows if r[2] == "skipped"]
        scheduled = [f"{r[1]} ({r[0]})" for r in rows if r[2] == "scheduled"]

        text = "📅 Bugungi hisobot:\n\n"
        text += f"✅ Ichilgan: {', '.join(taken) if taken else '—'}\n"
        text += f"⏰ Qoldirilgan: {', '.join(skipped) if skipped else '—'}\n"
        text += f"🔔 Rejalashtirilgan (halaqon): {', '.join(scheduled) if scheduled else '—'}\n"
        text += f"\n💊 Jami eslatmalar: {len(rows)}"

    try:
        await app.bot.send_message(chat_id=OWNER_CHAT_ID, text=text)
    except Exception as e:
        logger.exception("Could not send daily report: %s", e)


# === LOAD & START helpers ===
async def reload_jobs(app):
    rows = await load_all_schedules()
    for row in rows:
        sid, user_id, chat_id, hhmm, label, tz = row
        hh, mm = map(int, hhmm.split(":"))
        trigger = CronTrigger(hour=hh, minute=mm, timezone=pytz.timezone(tz))
        # job will run the async send_voice_and_text via create_task
        scheduler.add_job(
            lambda r=row: asyncio.create_task(send_voice_and_text(app, r)),
            trigger,
            id=f"reminder_{sid}"
        )
    # schedule daily report at 21:00
    scheduler.add_job(
        lambda: asyncio.create_task(send_daily_report(app)),
        CronTrigger(hour=21, minute=0, timezone=pytz.timezone(DEFAULT_TZ)),
        id="daily_report_21_00",
        replace_existing=True
    )
# === TELEGRAM notify helpers ===
async def notify_restart(bot):
    try:
        await bot.send_message(OWNER_CHAT_ID, "🔁 Bot qayta ishga tushdi — hammasi joyida!")
    except Exception:
        pass


async def notify_error(bot, error_text):
    try:
        await bot.send_message(OWNER_CHAT_ID, f"⚠️ Botda xatolik: {error_text}\n♻️ Qayta ishga tushmoqda...")
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
    # notify owner on start
    loop.run_until_complete(notify_restart(app.bot))

    print("✅ Bot ishga tushdi — Telegram'da /boshlash deb yozing!")
    app.run_polling()


# === AUTO RESTART WRAPPER (optional) ===
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
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error: {err_text}\n")

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
