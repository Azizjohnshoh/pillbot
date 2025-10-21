"""PillBot 4.4 Interactive+ - Webhook server (FastAPI) with state machine and custom time option"""
import os, logging, json, asyncio, re
from fastapi import FastAPI, Request, BackgroundTasks
import aiohttp, pytz
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

async def answer_callback(callback_query_id):
    async with aiohttp.ClientSession() as session:
        try:
            await session.post(f"{BOT_API}/answerCallbackQuery", json={"callback_query_id": callback_query_id})
        except Exception as e:
            log.warning("answerCallback failed: %s", e)

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
    log.info("Starting PillBot 4.4 Interactive+...")
    await dbmod.ensure_schema(path="data/pillbot.db")
    schedmod.start_scheduler()
    # schedule self-ping every 14 minutes
    schedmod.schedule_ping(14, _self_ping)
    log.info("Scheduler started and self-ping scheduled every 14 minutes.")

@app.get("/ping")
async def ping():
    return {"status":"ok"}

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

# validate HH:MM format
def valid_time_format(s):
    return bool(re.match(r'^(?:[01]\d|2[0-3]):[0-5]\d$', s))

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    log.info("Incoming update: %s", data.get("message") or data.get("callback_query") or "[no message]")

    # message flow
    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text","").strip()
        user_name = msg.get("from",{}).get("first_name","")
        await dbmod.ensure_user(chat_id, user_name)
        # check user state
        state, temp = await dbmod.get_state(chat_id)
        # /start
        if text.startswith("/start"):
            greeting = ("👋 Assalomu alaykum! Dori eslatish botiga hush kelibsiz!\n"
                        "Men sizga dorilarni o‘z vaqtida ichishni eslataman.\n"
                        "Quyidagi menyudan kerakli bo‘limni tanlang:")
            await send_message(chat_id, greeting, reply_markup=uimod.main_menu())
            if ENABLE_VOICE:
                background_tasks.add_task(send_voice, chat_id, "Assalomu alaykum! Dori eslatish botiga hush kelibsiz!")
            await dbmod.clear_state(chat_id)
            return {"ok": True}

        # if user is entering custom time after pressing "Other time"
        if state == "awaiting_custom_time":
            if valid_time_format(text):
                # store temp_data with chosen time and move to repeat selection
                await dbmod.set_state(chat_id, "awaiting_repeat", {"title": temp.get("title"), "time": text})
                await send_message(chat_id, "🔁 Qaytarilish turi?", reply_markup=uimod.repeat_choices())
            else:
                await send_message(chat_id, "❌ Noto‘g‘ri format. Iltimos, HH:MM formatda kiriting (masalan: 18:45).")
            return {"ok": True}

        # if user is at awaiting_med_name state (typed after pressing add)
        if state == "awaiting_med_name":
            # store title and prompt time choices
            title = text
            await dbmod.set_state(chat_id, "awaiting_time", {"title": title})
            await send_message(chat_id, "⏰ Qachon ichasiz? Tanlang yoki o‘zingiz kiriting:", reply_markup=uimod.generate_time_buttons())
            return {"ok": True}

        # fallback: if user types "Dori: Name, HH:MM, daily" support legacy
        if text.lower().startswith("dori:") or text.lower().startswith("add:"):
            try:
                parts = text.split(":",1)[1].strip().split(",")
                title = parts[0].strip()
                time_str = parts[1].strip() if len(parts)>1 else "08:00"
                recurring = parts[2].strip() if len(parts)>2 else "daily"
                rid = await dbmod.add_reminder(chat_id, title, time_str, recurring)
                # schedule job
                hh,mm = map(int, time_str.split(":"))
                schedmod.schedule_daily(rid, hh, mm, _send_reminder, args=(chat_id, title))
                await send_message(chat_id, f"✅ Dori qo'shildi: {title} @ {time_str} ({recurring})")
            except Exception as e:
                await send_message(chat_id, "Format xato. Iltimos: Dori: Nomi, HH:MM, daily|weekly")
            return {"ok": True}

        # default reply
        await send_message(chat_id, f"Echo: {text}")
        return {"ok": True}

    # callback_query flow (inline buttons)
    if "callback_query" in data:
        cq = data["callback_query"]
        cid = cq.get("id")
        cq_msg = cq.get("message")
        chat_id = cq_msg["chat"]["id"]
        data_payload = cq.get("data","")
        # answer callback to remove loading spinner
        asyncio.create_task(answer_callback(cid))

        # add med clicked
        if data_payload == "add_med":
            await dbmod.set_state(chat_id, "awaiting_med_name", {})
            await send_message(chat_id, "💊 Dori nomini kiriting (misol: Paracetamol)")
            return {"ok": True}

        # time chosen from buttons
        if data_payload.startswith("time_"):
            time_chosen = data_payload.split("_",1)[1].replace("_",":")
            # read temp title if exists
            state, temp = await dbmod.get_state(chat_id)
            title = temp.get("title") if temp else None
            if not title:
                # user pressed time without title -> prompt for title then continue
                await dbmod.set_state(chat_id, "awaiting_med_name", {})
                await send_message(chat_id, "Iltimos, avval dori nomini kiriting, misol: Paracetamol")
                return {"ok": True}
            # move to repeat selection
            await dbmod.set_state(chat_id, "awaiting_repeat", {"title": title, "time": time_chosen})
            await send_message(chat_id, "🔁 Qaytarilish turi?", reply_markup=uimod.repeat_choices())
            return {"ok": True}

        # custom time selected
        if data_payload == "time_custom":
            await dbmod.set_state(chat_id, "awaiting_custom_time", temp_data := (await dbmod.get_state(chat_id))[1] or {})
            await send_message(chat_id, "🕐 Iltimos, vaqtni HH:MM formatda kiriting (masalan: 18:45)")
            return {"ok": True}

        # repeat choice
        if data_payload in ("repeat_daily","repeat_once"):
            state, temp = await dbmod.get_state(chat_id)
            if not temp:
                await send_message(chat_id, "Xato: iltimos dori qo'shish jarayonini boshlang.")
                return {"ok": True}
            title = temp.get("title")
            time_chosen = temp.get("time")
            recurring = "daily" if data_payload=="repeat_daily" else "once"
            # add reminder
            rid = await dbmod.add_reminder(chat_id, title, time_chosen, recurring)
            # schedule if daily or one-time
            hh,mm = map(int, time_chosen.split(":"))
            schedmod.schedule_daily(rid, hh, mm, _send_reminder, args=(chat_id, title))
            await send_message(chat_id, f"✅ Dori qo'shildi: {title} @ {time_chosen} ({recurring})")
            await dbmod.clear_state(chat_id)
            return {"ok": True}

        # my meds
        if data_payload == "my_meds":
            meds = await dbmod.list_reminders_for_chat(chat_id)
            if meds:
                for r in meds:
                    await send_message(chat_id, f"{r['id']}: {r['title']} @ {r['time']} ({r.get('recurring')})", reply_markup={ "inline_keyboard":[ [{"text":"🗑️ O'chirish","callback_data":f"del_{r['id']}"} , {"text":"✏️ Tahrirlash","callback_data":f"edit_{r['id']}"}] ] })
            else:
                await send_message(chat_id, "Hech qanday dori topilmadi.")
            return {"ok": True}

        # delete
        if data_payload.startswith("del_"):
            rid = int(data_payload.split("_",1)[1])
            await dbmod.delete_reminder(rid)
            schedmod.remove_job(str(rid))
            await send_message(chat_id, "Dori oʻchirildi.")
            return {"ok": True}

        # report
        if data_payload == "report":
            meds = await dbmod.list_reminders_for_chat(chat_id)
            total = len(meds)
            next_item = meds[0] if meds else None
            text = f"📊 Sizning hisobot:\\n💊 Dorilar soni: {total}"
            if next_item:
                text += f"\\n🕓 Eng yaqin eslatma: {next_item['title']} @ {next_item['time']}"
            await send_message(chat_id, text)
            return {"ok": True}

        # settings
        if data_payload == "settings":
            # simple settings menu (scaffold)
            await send_message(chat_id, "⚙️ Sozlamalar:\\n🇺🇿 Til: O‘zbek\\n🔊 Ovoz: On\\n🌐 Vaqt zonasi: Asia/Tashkent")
            return {"ok": True}

        return {"ok": True}

    return {"ok": True}

async def _send_reminder(chat_id, title):
    text = f"🔔 Eslatma: {title} vaqti keldi!"
    await send_message(chat_id, text)
    if ENABLE_VOICE:
        await send_voice(chat_id, text)

# run uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("webhook_app:app", host="0.0.0.0", port=8080)
