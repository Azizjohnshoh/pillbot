#!/usr/bin/env python3
# PillBot Ultra Pro Max v3.6 — Secure + Analytics Edition
# Full working bot (button-driven UX, Smart TZ, Playlist manager, TTS reminders, keep-alive)
# Read BOT_TOKEN and OWNER_ID from environment variables for security.
# Requires: python-telegram-bot==22.5, aiosqlite, APScheduler, pytz, gTTS, aiohttp, nest_asyncio

import os
import logging
import asyncio
import aiosqlite
import aiohttp
import pytz
import zipfile
import traceback
from datetime import datetime, timedelta
from gtts import gTTS
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)

# ---------------- CONFIG/ENV ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")
if not BOT_TOKEN or not OWNER_ID:
    print("ERROR: BOT_TOKEN and OWNER_ID must be set as environment variables.")
    print("Set BOT_TOKEN and OWNER_ID (owner numeric id) and restart.")
    raise SystemExit(1)

try:
    OWNER_ID = int(OWNER_ID)
except:
    raise SystemExit("OWNER_ID must be an integer")

TZ = os.getenv("TZ", "Asia/Tashkent")
DB_PATH = os.getenv("DB_PATH", "pillbot_v3_6.db")
PORT = int(os.getenv("PORT", "10000"))
VOICE_LANG = os.getenv("VOICE_LANG", "uz")
DAILY_REPORT_HOUR = int(os.getenv("DAILY_REPORT_HOUR", "21"))
DAILY_BACKUP_HOUR = int(os.getenv("DAILY_BACKUP_HOUR", "23"))
SMART_CATCHER_MINUTES = int(os.getenv("SMART_CATCHER_MINUTES", "10"))

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pillbot_v3.6")

# ---------------- SCHEDULER ----------------
scheduler = AsyncIOScheduler(timezone=pytz.timezone(TZ))

# ---------------- DB ----------------
async def get_db():
    return await aiosqlite.connect(DB_PATH)

async def init_db():
    db = await get_db()
    await db.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        tz TEXT
    )""")
    await db.execute("""CREATE TABLE IF NOT EXISTS schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        chat_id INTEGER NOT NULL,
        hhmm TEXT NOT NULL,
        label TEXT NOT NULL,
        tz TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        streak INTEGER DEFAULT 0,
        last_taken_date TEXT
    )""")
    await db.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        schedule_id INTEGER,
        user_id INTEGER,
        chat_id INTEGER,
        date TEXT,
        time TEXT,
        label TEXT,
        status TEXT,
        created_at TEXT
    )""")
    await db.execute("""CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        action TEXT,
        timestamp TEXT
    )""")
    await db.commit()
    await db.close()

# ---------------- UTIL ----------------
def now_tz(tz_name=TZ):
    return datetime.now(pytz.timezone(tz_name))

def hhmm_to_tuple(hhmm: str):
    parts = hhmm.split(":")
    return int(parts[0]), int(parts[1])

def tts_save(text: str, filename="pill_tts.mp3", lang=VOICE_LANG):
    try:
        t = gTTS(text=text, lang=lang)
        t.save(filename)
        return filename
    except Exception as e:
        logger.warning("TTS failed: %s", e)
        return None

# ---------------- TIMEZONE DETECTION ----------------
async def detect_timezone_by_ip():
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://ipapi.co/json", timeout=5) as r:
                if r.status == 200:
                    j = await r.json()
                    tz = j.get("timezone")
                    if tz:
                        return tz
    except Exception as e:
        logger.debug("IP TZ detect failed: %s", e)
    return None

# ---------------- LOGGING ACTIONS ----------------
async def log_action(user_id, username, action):
    db = await get_db()
    ts = datetime.now(pytz.timezone(TZ)).isoformat()
    await db.execute("INSERT INTO logs (user_id, username, action, timestamp) VALUES (?,?,?,?)",
                     (user_id, username or "", action, ts))
    await db.commit()
    await db.close()

# ---------------- DB CRUD ----------------
async def set_user_tz(user_id: int, tz_name: str):
    db = await get_db()
    await db.execute("INSERT OR REPLACE INTO users (id, tz) VALUES (?, ?)", (user_id, tz_name))
    await db.commit()
    await db.close()
    await log_action(user_id, None, f"set_tz:{tz_name}")

async def get_user_tz(user_id: int):
    db = await get_db()
    cur = await db.execute("SELECT tz FROM users WHERE id=?", (user_id,))
    row = await cur.fetchone()
    await db.close()
    return row[0] if row else None

async def add_schedule(user_id, chat_id, hhmm, label, tz):
    db = await get_db()
    cur = await db.execute("INSERT INTO schedules (user_id, chat_id, hhmm, label, tz) VALUES (?,?,?,?,?)",
                           (user_id, chat_id, hhmm, label, tz))
    await db.commit()
    rowid = cur.lastrowid
    await db.close()
    await log_action(user_id, None, f"add:{label}@{hhmm}")
    return rowid

async def list_schedules(user_id):
    db = await get_db()
    cur = await db.execute("SELECT id, hhmm, label, tz, streak FROM schedules WHERE user_id=? AND active=1", (user_id,))
    rows = await cur.fetchall()
    await db.close()
    return rows

async def get_schedule(sid):
    db = await get_db()
    cur = await db.execute("SELECT id, user_id, chat_id, hhmm, label, tz FROM schedules WHERE id=?", (sid,))
    row = await cur.fetchone()
    await db.close()
    return row

async def delete_schedule(sid, user_id=None):
    db = await get_db()
    await db.execute("DELETE FROM schedules WHERE id=?", (sid,))
    await db.commit()
    await db.close()
    await log_action(user_id, None, f"delete:{sid}")

async def update_schedule_time(sid, new_hhmm, user_id=None):
    db = await get_db()
    await db.execute("UPDATE schedules SET hhmm=? WHERE id=?", (new_hhmm, sid))
    await db.commit()
    await db.close()
    await log_action(user_id, None, f"update_time:{sid}@{new_hhmm}")

async def update_schedule_label(sid, new_label, user_id=None):
    db = await get_db()
    await db.execute("UPDATE schedules SET label=? WHERE id=?", (new_label, sid))
    await db.commit()
    await db.close()
    await log_action(user_id, None, f"update_label:{sid}:{new_label}")

async def insert_event(schedule_id, user_id, chat_id, date_str, time_str, label, status="scheduled"):
    db = await get_db()
    created = datetime.now(pytz.timezone(TZ)).isoformat()
    await db.execute("INSERT INTO events (schedule_id, user_id, chat_id, date, time, label, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (schedule_id, user_id, chat_id, date_str, time_str, label, status, created))
    await db.commit()
    await db.close()

async def set_event_status(schedule_id, date_str, status):
    db = await get_db()
    await db.execute("UPDATE events SET status=? WHERE schedule_id=? AND date=?", (status, schedule_id, date_str))
    await db.commit()
    await db.close()

async def update_streak(schedule_id):
    db = await get_db()
    cur = await db.execute("SELECT last_taken_date, streak FROM schedules WHERE id=?", (schedule_id,))
    row = await cur.fetchone()
    if not row:
        await db.close()
        return
    last_date, streak = row
    today = datetime.now(pytz.timezone(TZ)).strftime("%Y-%m-%d")
    if last_date == today:
        await db.close()
        return
    if last_date:
        yesterday = (datetime.now(pytz.timezone(TZ)) - timedelta(days=1)).strftime("%Y-%m-%d")
        if last_date == yesterday:
            streak = (streak or 0) + 1
        else:
            streak = 1
    else:
        streak = 1
    await db.execute("UPDATE schedules SET last_taken_date=?, streak=? WHERE id=?", (today, streak, schedule_id))
    await db.commit()
    await db.close()

# ---------------- REMINDERS ----------------
async def send_reminder(app: Application, schedule_row):
    try:
        sid, user_id, chat_id, hhmm, label, tz = schedule_row
    except Exception:
        logger.exception("Malformed schedule row")
        return
    now = datetime.now(pytz.timezone(tz))
    date_str = now.strftime("%Y-%m-%d")
    await insert_event(sid, user_id, chat_id, date_str, hhmm, label)
    # tts + message buttons
    try:
        phrase = f"Eslatma: {label}. Dorini ichish vaqti."
        fn = tts_save(phrase)
        if fn:
            with open(fn, "rb") as f:
                await app.bot.send_voice(chat_id=chat_id, voice=f, caption=f"💊 {label}")
            try: os.remove(fn)
            except: pass
        await app.bot.send_message(chat_id=chat_id,
                                   text=f"💊 {label} — soat {hhmm}",
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ ICHDIM", callback_data=f"took:{sid}"),
                                                                      InlineKeyboardButton("⏰ QOLDIRISH 10m", callback_data=f"snooze:{sid}")]]))
    except Exception:
        logger.exception("send_reminder exception")

async def reload_jobs(app: Application):
    for j in list(scheduler.get_jobs()):
        if j.id.startswith("reminder_") or j.id.startswith("snooze_"):
            try: scheduler.remove_job(j.id)
            except: pass
    db = await get_db()
    cur = await db.execute("SELECT id, user_id, chat_id, hhmm, label, tz FROM schedules WHERE active=1")
    rows = await cur.fetchall()
    await db.close()
    for r in rows:
        sid, user_id, chat_id, hhmm, label, tz = r
        hh, mm = hhmm_to_tuple(hhmm)
        trigger = CronTrigger(hour=hh, minute=mm, timezone=pytz.timezone(tz))
        def make_job(row):
            def job_func():
                asyncio.create_task(send_reminder(app, row))
            return job_func
        scheduler.add_job(make_job(r), trigger, id=f"reminder_{sid}", replace_existing=True)
    logger.info("Jobs reloaded: %d", len(rows))

# ---------------- SMART CATCHER ----------------
async def smart_schedule_after_add(app, schedule_id, user_id, chat_id, hhmm, label, tz):
    hh, mm = hhmm_to_tuple(hhmm)
    user_now = datetime.now(pytz.timezone(tz))
    target_dt = user_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target_dt < user_now:
        target_dt = target_dt + timedelta(days=1)
    diff = (target_dt - user_now).total_seconds() / 60.0
    logger.debug("SmartSchedule diff minutes: %.2f", diff)
    if diff <= SMART_CATCHER_MINUTES:
        run_at = datetime.now(pytz.timezone(TZ)) + timedelta(seconds=15)
        def immediate_job(row=(schedule_id, user_id, chat_id, hhmm, label, tz)):
            asyncio.create_task(send_reminder(app, row))
        scheduler.add_job(immediate_job, trigger='date', run_date=run_at, id=f"snooze_{schedule_id}_{int(run_at.timestamp())}")
        logger.info("Smart catcher fired for %s (%.1f min)", label, diff)

# ---------------- KEEPALIVE ----------------
async def start_keepalive():
    async def handler(request):
        return web.Response(text="PillBot Ultra Pro Max v3.6 — alive")
    app = web.Application()
    app.router.add_get("/", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("KeepAlive server running on port %s", PORT)

# ---------------- OWNER ADMIN ----------------
def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or user.id != OWNER_ID:
            try:
                await update.effective_message.reply_text("Bu faqat egaga taalluqli.")
            except:
                pass
            return
        return await func(update, context)
    return wrapper

@owner_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = scheduler.get_jobs()
    text = f"Jobs: {len(jobs)}\\nTZ default: {TZ}\\nDB: {DB_PATH}"
    await update.message.reply_text(text)

@owner_only
async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if os.path.exists(DB_PATH):
            zipname = f"backup_{datetime.now().strftime('%Y%m%d%H%M%S')}.zip"
            with zipfile.ZipFile(zipname, "w") as z:
                z.write(DB_PATH)
            await context.bot.send_document(chat_id=OWNER_ID, document=open(zipname, "rb"))
            os.remove(zipname)
            await update.message.reply_text("Backup sent.")
    except Exception:
        logger.exception("backup failed")
        await update.message.reply_text("Backup failed.")

@owner_only
async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # export logs last 7 days as csv
    db = await get_db()
    cur = await db.execute("SELECT user_id, username, action, timestamp FROM logs WHERE timestamp >= ? ORDER BY timestamp DESC",
                           ((datetime.now(pytz.timezone(TZ)) - timedelta(days=7)).isoformat(),))
    rows = await cur.fetchall()
    await db.close()
    csv_lines = "user_id,username,action,timestamp\\n"
    for r in rows:
        csv_lines += f"{r[0]},{r[1]},{r[2]},{r[3]}\\n"
    fname = "logs_7days.csv"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(csv_lines)
    await context.bot.send_document(chat_id=OWNER_ID, document=open(fname, "rb"))
    os.remove(fname)

# ---------------- KEYBOARDS ----------------
def main_menu_kb():
    kb = [
        [InlineKeyboardButton("➕ Dori qo'shish", callback_data="ui_add"),
         InlineKeyboardButton("📋 Dorilarim", callback_data="ui_list")],
        [InlineKeyboardButton("📊 Hisobot", callback_data="ui_report"),
         InlineKeyboardButton("⚙️ Sozlamalar", callback_data="ui_settings")]
    ]
    return InlineKeyboardMarkup(kb)

def add_label_kb(preset_labels=None):
    kb = []
    presets = preset_labels or ["Paracetamol", "Zinc", "Vitamin D", "Aspirin"]
    row = []
    for i, lab in enumerate(presets):
        row.append(InlineKeyboardButton(f"💊 {lab}", callback_data=f"pick_label:{lab}"))
        if len(row) == 2:
            kb.append(row); row = []
    if row: kb.append(row)
    kb.append([InlineKeyboardButton("➕ Boshqa nom", callback_data="pick_label:__custom")])
    return InlineKeyboardMarkup(kb)

def add_time_kb():
    times = ["08:00","10:00","12:00","14:00","18:00","20:00","22:00"]
    kb = []
    row=[]
    for t in times:
        row.append(InlineKeyboardButton(t, callback_data=f"pick_time:{t}"))
        if len(row)==3:
            kb.append(row); row=[]
    if row: kb.append(row)
    kb.append([InlineKeyboardButton("🔢 Boshqa vaqt", callback_data="pick_time:__custom")])
    return InlineKeyboardMarkup(kb)

def list_item_kb(sid, label):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ICHDIM", callback_data=f"took:{sid}"),
         InlineKeyboardButton("✏️ Edit", callback_data=f"edit:{sid}")],
        [InlineKeyboardButton("🗑 O'chirish", callback_data=f"del:{sid}")],
    ])

def list_all_kb(rows):
    kb=[]
    for r in rows:
        sid, hhmm, label, tz, streak = r
        kb.append([InlineKeyboardButton(f"{label} — {hhmm}", callback_data=f"item:{sid}")])
    if not kb:
        kb=[[InlineKeyboardButton("➕ Dori qo'shish", callback_data="ui_add")]]
    kb.append([InlineKeyboardButton("🧹 Clear all", callback_data="clear_all")])
    return InlineKeyboardMarkup(kb)

def tz_picker_kb():
    choices = ["Asia/Tashkent","Europe/Moscow","Europe/London","America/New_York","Asia/Karachi"]
    kb=[[InlineKeyboardButton(t, callback_data=f"tz:{t}")] for t in choices]
    kb.append([InlineKeyboardButton("🌍 Boshqa", callback_data="tz:__manual")])
    return InlineKeyboardMarkup(kb)

# ---------------- HANDLERS ----------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    detected = await detect_timezone_by_ip()
    if detected:
        await set_user_tz(user.id, detected)
        tz_info = detected
    else:
        tz_info = (await get_user_tz(user.id)) or TZ
    await update.message.reply_text(f"👋 Assalomu alaykum! PillBot Ultra Pro Max v3.6\\nSizning vaqt zonangiz: {tz_info}", reply_markup=main_menu_kb())
    await log_action(user.id, user.username if user else "", "start")

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "ui_add":
        await q.message.reply_text("Qaysi dorini qo'shmoqchisiz? Tanlang yoki Boshqa tugmasini bosing.", reply_markup=add_label_kb())
        return

    if data.startswith("pick_label:"):
        label = data.split(":",1)[1]
        if label == "__custom":
            await q.message.reply_text("Iltimos, dori nomini yozing.")
            context.user_data['awaiting_custom_label']=True
            return
        else:
            context.user_data['new_label']=label
            await q.message.reply_text(f"Tanlandi: {label}. Endi vaqtni tanlang.", reply_markup=add_time_kb())
            return

    if data.startswith("pick_time:"):
        tt = data.split(":",1)[1]
        if tt == "__custom":
            await q.message.reply_text("Iltimos, vaqtni HH:MM formatida yozing (masalan 20:30).")
            context.user_data['awaiting_custom_time']=True
            return
        else:
            user = q.from_user
            tz_user = await get_user_tz(user.id) or TZ
            label = context.user_data.get('new_label', 'Dori')
            sid = await add_schedule(user.id, q.message.chat.id, tt, label, tz_user)
            await smart_schedule_after_add(context.application, sid, user.id, q.message.chat.id, tt, label, tz_user)
            await reload_jobs(context.application)
            await q.message.reply_text(f"✅ Eslatma saqlandi: {label} — {tt} (Vaqt zonangiz: {tz_user})", reply_markup=main_menu_kb())
            return

    if data == "ui_list":
        rows = await list_schedules(q.from_user.id)
        await q.message.reply_text("Sizning eslatmalaringiz:", reply_markup=list_all_kb(rows))
        return

    if data.startswith("item:"):
        sid = int(data.split(":",1)[1])
        row = await get_schedule(sid)
        if not row:
            await q.message.reply_text("Eslatma topilmadi.")
            return
        _, _, chat_id, hhmm, label, tz = row
        await q.message.reply_text(f"{label} — {hhmm} (tz: {tz})", reply_markup=list_item_kb(sid, label))
        return

    if data.startswith("took:"):
        sid = int(data.split(":",1)[1])
        row = await get_schedule(sid)
        if not row:
            await q.message.reply_text("Eslatma topilmadi.")
            return
        today = datetime.now(pytz.timezone(row[5])).strftime("%Y-%m-%d")
        await set_event_status(sid, today, "taken")
        await update_streak(sid)
        await q.message.reply_text("✅ Belgilandi: ichildi.", reply_markup=main_menu_kb())
        await log_action(q.from_user.id, q.from_user.username if q.from_user else "", f"took:{sid}")
        return

    if data.startswith("snooze:"):
        sid = int(data.split(":",1)[1])
        row = await get_schedule(sid)
        if not row:
            await q.message.reply_text("Eslatma topilmadi.")
            return
        run_at = datetime.now(pytz.timezone(TZ)) + timedelta(minutes=10)
        def snooze_job(row=row):
            asyncio.create_task(send_reminder(context.application, row))
        scheduler.add_job(snooze_job, trigger='date', run_date=run_at, id=f"snooze_{sid}_{int(run_at.timestamp())}")
        await q.message.reply_text("⏰ Qoldirildi 10 daqiqaga.", reply_markup=main_menu_kb())
        await log_action(q.from_user.id, q.from_user.username if q.from_user else "", f"snooze:{sid}")
        return

    if data.startswith("del:"):
        sid = int(data.split(":",1)[1])
        await delete_schedule(sid, q.from_user.id)
        await reload_jobs(context.application)
        await q.message.reply_text("❌ Eslatma o'chirildi.", reply_markup=main_menu_kb())
        return

    if data == "clear_all":
        db = await get_db()
        await db.execute("DELETE FROM schedules WHERE user_id=?", (q.from_user.id,))
        await db.commit()
        await db.close()
        await reload_jobs(context.application)
        await q.message.reply_text("🧹 Barcha eslatmalar o'chirildi.", reply_markup=main_menu_kb())
        await log_action(q.from_user.id, q.from_user.username if q.from_user else "", "clear_all")
        return

    if data.startswith("edit:"):
        sid = int(data.split(":",1)[1])
        context.user_data['edit_sid']=sid
        await q.message.reply_text("Nimani o'zgartirmoqchisiz?", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Nomni o'zgartirish", callback_data="edit_label"),
             InlineKeyboardButton("⏰ Vaqtni o'zgartirish", callback_data="edit_time")],
            [InlineKeyboardButton("🔙 Ortga", callback_data="ui_list")]
        ]))
        return

    if data == "edit_label":
        await q.message.reply_text("Yangi nomni kiriting yoki tanlang:", reply_markup=add_label_kb())
        context.user_data['editing']='label'
        return

    if data == "edit_time":
        await q.message.reply_text("Yangi vaqtni tanlang:", reply_markup=add_time_kb())
        context.user_data['editing']='time'
        return

    if data == "ui_report":
        today = datetime.now(pytz.timezone((await get_user_tz(q.from_user.id)) or TZ)).strftime("%Y-%m-%d")
        db = await get_db()
        cur = await db.execute("SELECT time, label, status FROM events WHERE user_id=? AND date=? ORDER BY time", (q.from_user.id, today))
        rows = await cur.fetchall()
        await db.close()
        if not rows:
            await q.message.reply_text("📋 Bugungi hisobot: hech narsa yo'q.", reply_markup=main_menu_kb())
        else:
            txt = "📋 Bugungi hisobot:\\n"
            for t,l,s in rows:
                txt += f"{t} — {l} ({s})\\n"
            await q.message.reply_text(txt, reply_markup=main_menu_kb())
        await log_action(q.from_user.id, q.from_user.username if q.from_user else "", "report")
        return

    if data == "ui_settings":
        tz_user = await get_user_tz(q.from_user.id) or TZ
        await q.message.reply_text(f"⚙️ Sozlamalar (Vaqt zonasi: {tz_user})", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌍 Vaqt zonasi o'zgartirish", callback_data="set_tz")],
            [InlineKeyboardButton("🔁 Backup yuborish (owner)", callback_data="do_backup")],
            [InlineKeyboardButton("🔙 Ortga", callback_data="menu_back")]
        ]))
        return

    if data == "set_tz":
        await q.message.reply_text("Vaqt zonasini tanlang:", reply_markup=tz_picker_kb())
        return

    if data.startswith("tz:"):
        tz_choice = data.split(":",1)[1]
        if tz_choice == "__manual":
            await q.message.reply_text("Iltimos, o'zingizning vaqt zonangizni yozing (masalan Asia/Tashkent)")
            context.user_data['awaiting_tz_manual']=True
            return
        else:
            await set_user_tz(q.from_user.id, tz_choice)
            await reload_jobs(context.application)
            await q.message.reply_text(f"✅ Vaqt zonasi o'rnatildi: {tz_choice}", reply_markup=main_menu_kb())
            return

    if data == "menu_back":
        await q.message.reply_text("🔙", reply_markup=main_menu_kb())
        return

    if data == "do_backup":
        await q.message.reply_text("🔔 Owner can request /backup")
        return

    await q.message.reply_text("Noma'lum tugma, bosh menyu:", reply_markup=main_menu_kb())

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if context.user_data.get('awaiting_custom_label'):
        context.user_data.pop('awaiting_custom_label', None)
        context.user_data['new_label']=txt
        await update.message.reply_text("Vaqtni tanlang:", reply_markup=add_time_kb())
        return
    if context.user_data.get('awaiting_custom_time'):
        context.user_data.pop('awaiting_custom_time', None)
        hhmm = txt.strip()[:5]
        label = context.user_data.get('new_label') or "Dori"
        user = update.effective_user
        tz_user = await get_user_tz(user.id) or TZ
        sid = await add_schedule(user.id, update.effective_chat.id, hhmm, label, tz_user)
        await smart_schedule_after_add(context.application, sid, user.id, update.effective_chat.id, hhmm, label, tz_user)
        await reload_jobs(context.application)
        await update.message.reply_text(f"✅ Eslatma saqlandi: {label} — {hhmm} (tz: {tz_user})", reply_markup=main_menu_kb())
        return
    if context.user_data.get('editing') == 'label' and context.user_data.get('edit_sid'):
        sid = context.user_data.pop('edit_sid', None)
        context.user_data.pop('editing', None)
        await update_schedule_label(sid, txt, update.effective_user.id)
        await reload_jobs(context.application)
        await update.message.reply_text("✅ Nom yangilandi.", reply_markup=main_menu_kb())
        return
    if context.user_data.get('editing') == 'time' and context.user_data.get('edit_sid'):
        sid = context.user_data.pop('edit_sid', None)
        context.user_data.pop('editing', None)
        await update_schedule_time(sid, txt.strip()[:5], update.effective_user.id)
        await reload_jobs(context.application)
        await update.message.reply_text("✅ Vaqt yangilandi.", reply_markup=main_menu_kb())
        return
    if context.user_data.get('awaiting_tz_manual'):
        context.user_data.pop('awaiting_tz_manual', None)
        await set_user_tz(update.effective_user.id, txt)
        await reload_jobs(context.application)
        await update.message.reply_text(f"✅ Vaqt zonasi o'rnatildi: {txt}", reply_markup=main_menu_kb())
        return
    await update.message.reply_text("Tugmalardan foydalaning yoki ➕ Dori qo'shish ni bosing.", reply_markup=main_menu_kb())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 PillBot yordam:\\nFoydalanish tugmalar orqali.")

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await list_schedules(update.effective_user.id)
    if not rows:
        await update.message.reply_text("Sizda eslatma yo'q.", reply_markup=main_menu_kb())
        return
    txt = "📋 Dorilarim:\\n"
    for r in rows:
        sid, hhmm, label, tz, streak = r
        txt += f"ID {sid}: {label} — {hhmm} (tz:{tz})\\n"
    await update.message.reply_text(txt, reply_markup=main_menu_kb())

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception: %s", context.error)
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=f"Bot error: {context.error}")
    except:
        pass

# Daily report & backup
async def daily_report(app: Application):
    try:
        today = datetime.now(pytz.timezone(TZ)).strftime("%Y-%m-%d")
        db = await get_db()
        cur = await db.execute("SELECT user_id, time, label, status FROM events WHERE date=? ORDER BY user_id", (today,))
        rows = await cur.fetchall()
        await db.close()
        text = f"📅 Daily report {today}\\nTotal events: {len(rows)}"
        await app.bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception:
        logger.exception("daily_report failed")

async def daily_backup(app: Application):
    try:
        if os.path.exists(DB_PATH):
            zipname = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            with zipfile.ZipFile(zipname, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(DB_PATH)
            await app.bot.send_document(chat_id=OWNER_ID, document=open(zipname, "rb"))
            os.remove(zipname)
    except Exception:
        logger.exception("daily_backup failed")

# ---------------- APP BUILD & RUN ----------------
async def build_app_and_run():
    await init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("backup", cmd_backup))
    app.add_handler(CommandHandler("logs", cmd_logs))

    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_error_handler(error_handler)

    if not scheduler.running:
        scheduler.start()

    await reload_jobs(app)

    scheduler.add_job(lambda: asyncio.create_task(daily_report(app)), CronTrigger(hour=DAILY_REPORT_HOUR, minute=0, timezone=pytz.timezone(TZ)), id="daily_report", replace_existing=True)
    scheduler.add_job(lambda: asyncio.create_task(daily_backup(app)), CronTrigger(hour=DAILY_BACKUP_HOUR, minute=5, timezone=pytz.timezone(TZ)), id="daily_backup", replace_existing=True)

    asyncio.create_task(start_keepalive())

    try:
        await app.bot.send_message(chat_id=OWNER_ID, text=f"PillBot v3.6 started at {datetime.now().isoformat()}")
    except Exception:
        logger.exception("owner notify failed")

    await app.run_polling()

def main():
    try:
        import nest_asyncio
        nest_asyncio.apply()
    except Exception:
        pass

    async def runner():
        while True:
            try:
                await build_app_and_run()
            except Exception as e:
                logger.exception("Fatal in build_app_and_run, restarting: %s", e)
                try:
                    async with aiohttp.ClientSession() as s:
                        await s.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                     json={"chat_id": OWNER_ID, "text": f"PillBot crashed: {str(e)[:300]}"})
                except:
                    pass
                await asyncio.sleep(5)

    loop = asyncio.get_event_loop()
    if loop.is_running():
        loop.create_task(runner())
    else:
        loop.run_until_complete(runner())

if __name__ == "__main__":
    main()