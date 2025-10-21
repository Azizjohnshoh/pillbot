
import os, asyncio, logging, json
from datetime import datetime
from fastapi import FastAPI, Request, BackgroundTasks
import aiohttp, uvicorn

from utils import dbmod, schedmod, ui, voice, lang

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("pillbot.webhook")

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT = os.getenv("ADMIN_CHAT", "")
BASE_URL = os.getenv("BASE_URL", "https://pillbot-4-6.onrender.com")
WEBHOOK_URL = f"{BASE_URL}/webhook"
ENABLE_VOICE = os.getenv("ENABLE_VOICE", "True").lower() in ("1","true","yes")
VOICE_LANG = os.getenv("VOICE_LANG", "uz")
PORT = int(os.getenv("PORT", 8080))

if not TOKEN:
    raise RuntimeError("Missing TELEGRAM_TOKEN environment variable")

BOT_API = f"https://api.telegram.org/bot{TOKEN}"

app = FastAPI()

@app.get("/")
async def root():
    return {
        "status": "✅ PillBot 4.6 (Webhook Stable) is running",
        "time": datetime.utcnow().isoformat(),
        "webhook_url": WEBHOOK_URL,
        "voice_enabled": ENABLE_VOICE,
        "lang": VOICE_LANG
    }

@app.get("/ping")
async def ping():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    log.debug("Incoming update keys: %s", list(data.keys()))
    try:
        if "message" in data:
            from bot_handlers import handle_message as _handle_message
            background_tasks.add_task(_handle_message, data, send_message, send_voice)
        if "callback_query" in data:
            cq = data["callback_query"]
            cid = cq.get("id")
            payload = cq.get("data","")
            msg = cq.get("message",{})
            chat_id = msg.get("chat",{}).get("id")
            try:
                async with aiohttp.ClientSession() as session:
                    await session.post(f"{BOT_API}/answerCallbackQuery", json={"callback_query_id": cid}, timeout=5)
            except Exception:
                pass
            from bot_handlers import handle_callback as _handle_callback
            background_tasks.add_task(_handle_callback, cq, send_message, send_voice)
    except Exception as e:
        log.exception("Error processing update: %s", e)
    return {"ok": True}

async def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(f"{BOT_API}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        log.warning("send_message failed: %s", e)

async def send_voice(chat_id, text, lang_code="uz"):
    try:
        mp3 = voice.text_to_speech(text, lang=lang_code)
        async with aiohttp.ClientSession() as session:
            with open(mp3, "rb") as f:
                data = aiohttp.FormData()
                data.add_field("chat_id", str(chat_id))
                data.add_field("voice", f, filename="tts.mp3", content_type="audio/mpeg")
                await session.post(f"{BOT_API}/sendVoice", data=data, timeout=20)
        voice.cleanup_old()
    except Exception as e:
        log.warning("send_voice failed: %s", e)

async def ensure_webhook_once():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BOT_API}/getWebhookInfo", timeout=10) as resp:
                data = await resp.json()
            current = data.get("result", {}).get("url", "")
            if current != WEBHOOK_URL:
                log.info("Setting webhook -> %s", WEBHOOK_URL)
                async with session.post(f"{BOT_API}/setWebhook", data={"url": WEBHOOK_URL}, timeout=15) as set_resp:
                    res = await set_resp.json()
                    log.info("setWebhook response: %s", res)
            else:
                log.info("Webhook already set and correct.")
    except Exception as e:
        log.warning("ensure_webhook_once error: %s", e)

async def periodic_webhook_check():
    while True:
        await ensure_webhook_once()
        await asyncio.sleep(6 * 60 * 60)

async def self_ping_once():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BASE_URL, timeout=10) as r:
                if r.status == 200:
                    log.info("Self-ping OK")
    except Exception as e:
        log.warning("Self-ping failed: %s", e)

async def schedule_keepalive():
    try:
        schedmod.start_scheduler()
        schedmod.schedule_ping(14, self_ping_once)
    except Exception as e:
        log.warning("schedule_keepalive error: %s", e)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(initialize_app())

async def initialize_app():
    log.info("Initializing PillBot 4.6 (Stable Webhook)...")
    try:
        await dbmod.ensure_schema(path="data/pillbot.db")
    except Exception as e:
        log.warning("DB ensure_schema failed: %s", e)
    try:
        await schedule_keepalive()
    except Exception as e:
        log.warning("schedule_keepalive failed: %s", e)
    asyncio.create_task(ensure_webhook_once())
    asyncio.create_task(periodic_webhook_check())
    if ADMIN_CHAT:
        try:
            await send_message(ADMIN_CHAT, f"✅ PillBot 4.6 (Webhook Stable) started at {datetime.utcnow().isoformat()}")
            if ENABLE_VOICE:
                await send_voice(ADMIN_CHAT, "PillBot ishga tushdi. Dori eslatish bot aktiv.", lang_code=VOICE_LANG)
        except Exception as e:
            log.warning("Admin notify failed: %s", e)
    log.info("Initialization tasks scheduled. Webhook: %s", WEBHOOK_URL)

if __name__ == "__main__":
    log.info("Starting Uvicorn: PillBot 4.6 (Webhook Stable) on port %s", PORT)
    uvicorn.run("webhook_app:app", host="0.0.0.0", port=PORT, log_level="info")
