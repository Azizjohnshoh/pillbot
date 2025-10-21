"""PillBot Ultra Pro Max v4.4 Interactive - Webhook server (FastAPI)"""
import os, logging, json, asyncio, datetime
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
BASE_URL = os.getenv("BASE_URL", "https://pillbot-ultra-pro-max.onrender.com")

app = FastAPI()

async def _self_ping():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{BASE_URL}/ping") as resp:
                if resp.status == 200:
                    logging.getLogger("pillbot.keepalive").info("Self-ping OK ✅")
        except Exception as e:
            logging.getLogger("pillbot.keepalive").warning(f"Self-ping failed: {e}")

@app.on_event("startup")
async def startup_event():
    log.info("Starting PillBot v4.4 Interactive...")
    await dbmod.ensure_schema(path="data/pillbot.db")
    schedmod.start_scheduler()
    # schedule self-ping every 14 minutes to keep Render alive
    schedmod.schedule_ping(14, _self_ping)
    log.info("Scheduler started and self-ping scheduled every 14 minutes.")

@app.get("/ping")
async def ping():
    return {"status":"ok"}

# helper to send messages
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
                data.add_field("chat_id", str(chat_id))
                data.add_field("voice", f, filename="tts.mp3", content_type="audio/mpeg")
                await session.post(f"{BOT_API}/sendVoice", data=data)
        voicemod.cleanup_old()
    except Exception as e:
        log.exception("Voice send failed: %s", e)

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    log.info("Incoming update: %s", data.get("message") or data.get("callback_query") or "[no message]")
    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text","")
        user_name = msg.get("from",{}).get("first_name","")
        await dbmod.ensure_user(chat_id, user_name)
        if text.startswith("/start"):
            greeting = ("👋 Assalomu alaykum! Dori eslatish botiga hush kelibsiz!\\n"
                        "Men sizga dorilarni o‘z vaqtida ichishni eslataman.\\n"
                        "Quyidagi menyudan kerakli bo‘limni tanlang:")
            await send_message(chat_id, greeting, reply_markup=uimod.main_menu())
            if ENABLE_VOICE:
                background_tasks.add_task(send_voice, chat_id, "Assalomu alaykum! Dori eslatish botiga hush kelibsiz!")
            return {"ok": True}
        if text.lower().startswith("dori:") or text.lower().startswith("add:"):
            try:
                parts = text.split(":",1)[1].strip().split(",")
                title = parts[0].strip()
                time_str = parts[1].strip() if len(parts)>1 else "08:00"
                recurring = parts[2].strip() if len(parts)>2 else "daily"
                rid = await dbmod.add_reminder(chat_id, title, time_str, recurring)
                hh,mm = map(int, time_str.split(":"))
                schedmod.schedule_daily(rid, hh, mm, _send_reminder, args=(chat_id, title))
                await send_message(chat_id, f"✅ Dori qo'shildi: {title} @ {time_str} ({recurring})")
            except Exception:
                await send_message(chat_id, "Format xato. Iltimos: Dori: Nomi, HH:MM, daily|weekly")
            return {"ok": True}
        await send_message(chat_id, f"Echo: {text}")
        return {"ok": True}
    if "callback_query" in data:
        cq = data["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        data_payload = cq.get("data","")
        if data_payload == "add_med":
            await send_message(chat_id, "💊 Dori nomini kiriting (misol: Paracetamol)")
        elif data_payload.startswith("time_"):
            await send_message(chat_id, f"Vaqt tanlandi: {data_payload[5:].replace('_',':')}\\nIltimos, dori nomini yuboring formatda: Dori: Nomi, HH:MM, daily")
        elif data_payload == "my_meds":
            meds = await dbmod.list_reminders_for_chat(chat_id)
            if meds:
                for r in meds:
                    text = f"{r['id']}: {r['title']} @ {r['time']} ({r.get('recurring')})"
                    await send_message(chat_id, text, reply_markup={ "inline_keyboard":[ [{"text":"🗑️ O'chirish","callback_data":f"del_{r['id']}"},{"text":"✏️ Tahrirlash","callback_data":f"edit_{r['id']}"} ] ] })
            else:
                await send_message(chat_id, "Hech qanday dori topilmadi.")
        elif data_payload.startswith("del_"):
            rid = int(data_payload.split("_",1)[1])
            await dbmod.delete_reminder(rid)
            schedmod.remove_job(str(rid))
            await send_message(chat_id, "Dori oʻchirildi.")
        elif data_payload == "settings":
            await send_message(chat_id, "⚙️ Sozlamalar:\\n- Til: 🇺🇿 / 🇷🇺 / 🇬🇧\\n- Ovoz: On/Off\\n- Vaqt zonasi")
        return {"ok": True}
    return {"ok": True}

async def _send_reminder(chat_id, title):
    text = f"🔔 Eslatma: {title} vaqti keldi!"
    await send_message(chat_id, text)
    if ENABLE_VOICE:
        await send_voice(chat_id, text)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("webhook_app:app", host="0.0.0.0", port=8080)
