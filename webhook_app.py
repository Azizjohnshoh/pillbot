
import os, asyncio, logging, json
from datetime import datetime
from fastapi import FastAPI, Request, BackgroundTasks
import aiohttp
import uvicorn
from utils import dbmod, schedmod, ui, voice, lang
import bot_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("pillbot")

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT = os.getenv("ADMIN_CHAT", "")
BASE_URL = os.getenv("BASE_URL", "https://pillbot-ultra-pro-max.onrender.com")
WEBHOOK_URL = f"{BASE_URL}/webhook"
ENABLE_VOICE = os.getenv("ENABLE_VOICE", "True").lower() in ("1","true","yes")
VOICE_LANG = os.getenv("VOICE_LANG", "uz")
PORT = int(os.getenv("PORT", 8080))
BOT_API = f"https://api.telegram.org/bot{TOKEN}"
app = FastAPI()

async def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    async with aiohttp.ClientSession() as session:
        await session.post(f"{BOT_API}/sendMessage", json=payload)

async def send_voice(chat_id, text, lang_code='uz'):
    try:
        mp3 = voice.text_to_speech(text, lang=lang_code)
        async with aiohttp.ClientSession() as session:
            with open(mp3, "rb") as f:
                data = aiohttp.FormData()
                data.add_field("chat_id", str(chat_id))
                data.add_field("voice", f, filename="tts.mp3", content_type="audio/mpeg")
                await session.post(f"{BOT_API}/sendVoice", data=data)
        voice.cleanup_old()
    except Exception as e:
        log.exception("Voice send failed: %s", e)

# webhook and maintenance
async def ensure_webhook():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo") as resp:
                data = await resp.json()
                current = data["result"].get("url","")
                if current != WEBHOOK_URL:
                    async with session.post(f"https://api.telegram.org/bot{TOKEN}/setWebhook", data={"url": WEBHOOK_URL}) as r:
                        log.info(await r.json())
    except Exception as e:
        log.error("ensure_webhook error: %s", e)

async def periodic_webhook_check():
    while True:
        await ensure_webhook()
        await asyncio.sleep(6*60*60)

async def _self_ping():
    try:
        async with aiohttp.ClientSession() as s:
            await s.get(BASE_URL)
    except:
        pass

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(initialize_app())

async def initialize_app():
    log.info("Starting PillBot 4.6 Ultimate...")
    await dbmod.ensure_schema(path="data/pillbot.db")
    schedmod.start_scheduler()
    schedmod.schedule_ping(14, _self_ping)
    asyncio.create_task(ensure_webhook())
    asyncio.create_task(periodic_webhook_check())
    # notify admin/chat if set
    if ADMIN_CHAT:
        await send_message(ADMIN_CHAT, "✅ PillBot 4.6 started at " + datetime.utcnow().isoformat())
        if ENABLE_VOICE:
            await send_voice(ADMIN_CHAT, "PillBot ishga tushdi. Dori eslatish bot aktiv.", lang_code=VOICE_LANG)

@app.get("/")
async def root():
    return {"status":"ok","time":datetime.utcnow().isoformat()}

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    # process via bot_handlers (message flows)
    try:
        # message content
        if "message" in data:
            # pass helper functions
            await bot_handlers.handle_message(data, send_message, send_voice)
        # callback_query (inline buttons)
        if "callback_query" in data:
            cq = data["callback_query"]
            cid = cq.get("id")
            msg = cq.get("message",{})
            chat_id = msg.get("chat",{}).get("id")
            payload = cq.get("data","")
            # answer callback quickly
            async with aiohttp.ClientSession() as session:
                try:
                    await session.post(f"{BOT_API}/answerCallbackQuery", json={"callback_query_id": cid})
                except:
                    pass
            # minimal inline handling: start add flow and time/repeat/custom/back/settings
            state, temp = await dbmod.get_state(chat_id)
            lang_code, voice_on = await dbmod.get_user_prefs(chat_id)
            T = lang.TEXT.get(lang_code, lang.TEXT['uz'])
            if payload == "add_med":
                await dbmod.set_state(chat_id, "awaiting_med_name", {})
                await send_message(chat_id, T['ask_med_name'])
            elif payload.startswith("time_"):
                time_chosen = payload.split("_",1)[1]
                # store and ask repeat
                s, tdata = await dbmod.get_state(chat_id)
                title = tdata.get("title") if tdata else None
                if not title:
                    # if no title, prompt for title
                    await dbmod.set_state(chat_id, "awaiting_med_name", {})
                    await send_message(chat_id, T['ask_med_name'])
                else:
                    await dbmod.set_state(chat_id, "awaiting_repeat", {"title": title, "time": time_chosen})
                    await send_message(chat_id, T['ask_repeat'], reply_markup=ui.repeat_buttons(lang_code))
            elif payload == "time_custom":
                # ask to input custom time
                s, tdata = await dbmod.get_state(chat_id)
                await dbmod.set_state(chat_id, "awaiting_custom_time", tdata or {})
                await send_message(chat_id, T['ask_custom_time'])
            elif payload in ("repeat_daily","repeat_once"):
                s, tdata = await dbmod.get_state(chat_id)
                if not tdata:
                    await send_message(chat_id, "Jarayon topilmadi. Iltimos boshidan boshlang.")
                else:
                    title = tdata.get("title")
                    time_chosen = tdata.get("time")
                    recurring = "daily" if payload=="repeat_daily" else "once"
                    rid = await dbmod.add_reminder(chat_id, title, time_chosen, recurring)
                    # schedule
                    hh,mm = map(int, time_chosen.split(":"))
                    schedmod.schedule_daily(rid, hh, mm, lambda cid, t=title: None, args=(chat_id, title))
                    await send_message(chat_id, T['added'].format(title=title, time=time_chosen, recurring=recurring))
                    # voice
                    if voice_on:
                        await send_voice(chat_id, T['added'].format(title=title, time=time_chosen, recurring=recurring), lang_code=lang_code)
                    await dbmod.clear_state(chat_id)
            elif payload == "my_meds":
                meds = await dbmod.list_reminders_for_chat(chat_id)
                if meds:
                    for r in meds:
                        await send_message(chat_id, f"{r['id']}: {r['title']} @ {r['time']} ({r.get('recurring')})")
                else:
                    await send_message(chat_id, T['no_meds'])
            elif payload == "report":
                meds = await dbmod.list_reminders_for_chat(chat_id)
                total = len(meds)
                text = T['report'].format(total=total)
                await send_message(chat_id, text)
            elif payload == "settings":
                # send settings menu
                await send_message(chat_id, T['settings'], reply_markup=ui.settings_menu(lang_code, voice_on=bool(voice_on)))
            elif payload == "set_lang":
                # toggle language
                new_lang = 'ru' if lang_code=='uz' else 'uz'
                await dbmod.set_user_prefs(chat_id, language=new_lang)
                T2 = lang.TEXT.get(new_lang, lang.TEXT['uz'])
                await send_message(chat_id, T2['lang_set'].format(lang=new_lang), reply_markup=ui.main_menu(new_lang))
            elif payload == "toggle_voice":
                new_voice = 0 if voice_on else 1
                await dbmod.set_user_prefs(chat_id, voice_enabled=new_voice)
                await send_message(chat_id, lang.TEXT.get(lang_code, lang.TEXT['uz'])['voice_off'] if new_voice==0 else lang.TEXT.get(lang_code, lang.TEXT['uz'])['voice_on'], reply_markup=ui.settings_menu(lang_code, voice_on=bool(new_voice)))
            elif payload == "back":
                await send_message(chat_id, ui.main_menu(lang_code), reply_markup=ui.main_menu(lang_code))
    except Exception as e:
        log.exception("Webhook handling failed: %s", e)
    return {"ok": True}
