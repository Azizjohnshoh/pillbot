"""PillBot Ultra Pro Max v4.3 - Webhook server (FastAPI)"""
import os, logging, json
from fastapi import FastAPI, Request, BackgroundTasks
import aiohttp
from utils import db as dbmod, scheduler as schedmod, voice as voicemod, ui as uimod

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("pillbot.webhook")

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing TELEGRAM_TOKEN environment variable")

BOT_API = f"https://api.telegram.org/bot{TOKEN}"
ENABLE_VOICE = os.getenv("ENABLE_VOICE", "True").lower() in ("1","true","yes")
VOICE_LANG = os.getenv("VOICE_LANG", "uz")

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    log.info("Starting PillBot v4.3 Webhook")
    await dbmod.ensure_schema(path="data/pillbot.db")
    schedmod.start_scheduler()

@app.get("/")
async def root():
    return {"status": "PillBot Ultra Pro Max Webhook active"}

async def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    async with aiohttp.ClientSession() as session:
        await session.post(f"{BOT_API}/sendMessage", json=payload)

async def send_voice(chat_id, text):
    try:
        mp3 = voicemod.text_to_speech(text, lang=VOICE_LANG)
        async with aiohttp.ClientSession() as session:
            with open(mp3, "rb") as f:
                data = aiohttp.FormData()
                data.add_field('chat_id', str(chat_id))
                data.add_field('voice', f, filename="tts.mp3", content_type='audio/mpeg')
                await session.post(f"{BOT_API}/sendVoice", data=data)
    except Exception as e:
        log.exception("Voice send failed: %s", e)

async def handle_start(chat_id, user_name):
    greeting = "👋 Assalomu alaykum! Dori eslatish botiga hush kelibsiz!\\nMen sizga dorilarni o‘z vaqtida ichishni eslataman.\\nQuyidagi menyudan kerakli bo‘limni tanlang:"
    markup = uimod.main_menu()
    await send_message(chat_id, greeting, reply_markup=markup)
    if ENABLE_VOICE:
        await send_voice(chat_id, "Assalomu alaykum! Dori eslatish botiga hush kelibsiz!")

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    log.info("Incoming update: %s", data.get("message") or data.get("callback_query") or "[no message]")
    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text","")
        user_name = msg.get("from",{}).get("first_name","")
        if text.startswith("/start"):
            background_tasks.add_task(handle_start, chat_id, user_name)
            return {"ok": True}
        elif text.startswith("/help"):
            background_tasks.add_task(send_message, chat_id, "Bu bot dorilarni eslatish uchun mo‘ljallangan. /start bilan boshlang.")
            return {"ok": True}
        elif text.lower().startswith("dori") or text.lower().startswith("add"):
            background_tasks.add_task(send_message, chat_id, "Dori qo'shish funksiyasi ishlamoqda — iltimos ma'lumot kiriting (misol: Paracetamol, 08:00, daily)")
            return {"ok": True}
        else:
            background_tasks.add_task(send_message, chat_id, f"Echo: {text}")
            return {"ok": True}
    if "callback_query" in data:
        cq = data["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        data_payload = cq.get("data","")
        if data_payload == "add_med":
            background_tasks.add_task(send_message, chat_id, "Dori qoʻshish funksiyasi — iltimos nom, vaqt va interval kiriting.")
        elif data_payload == "my_meds":
            meds = await dbmod.list_reminders_for_chat(chat_id)
            if meds:
                text = "Sizning dorilaringiz:\\n" + "\\n".join([f\"{r['id']}: {r['title']} @ {r['time']}\" for r in meds])
            else:
                text = "Hech qanday dori topilmadi."
            background_tasks.add_task(send_message, chat_id, text)
        elif data_payload == "report":
            background_tasks.add_task(send_message, chat_id, "Hisobot generatsiya qilinmoqda...")
        elif data_payload == "settings":
            background_tasks.add_task(send_message, chat_id, "Sozlamalar: ovoz, timezone, til.")
        return {"ok": True}
    return {"ok": True}
