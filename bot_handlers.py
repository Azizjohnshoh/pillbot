
import asyncio, re
from utils import dbmod, ui, lang, voice
from datetime import datetime, timedelta
import pytz

# helpers
def round_to_next_slot(now):
    minute = 30 if now.minute >= 30 else 0
    base = now.replace(minute=minute, second=0, microsecond=0)
    return base

def generate_time_slots(tz_name='Asia/Tashkent', slots=6):
    tz = pytz.timezone(tz_name)
    now = datetime.now(tz)
    base = round_to_next_slot(now)
    times = []
    for i in range(slots):
        t = base + timedelta(minutes=30*i)
        times.append(t.strftime("%H:%M"))
    return times

async def handle_message(data, send_message, send_voice):
    # minimal dispatcher for messages
    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text","").strip()
        user_name = msg.get("from",{}).get("first_name","")
        await dbmod.ensure_user(chat_id, user_name)
        state, temp = await dbmod.get_state(chat_id)
        lang_code, voice_on = await dbmod.get_user_prefs(chat_id)
        T = lang.TEXT.get(lang_code, lang.TEXT['uz'])
        # start
        if text.startswith("/start"):
            await send_message(chat_id, T['greeting'] + "\n" + T['start_menu'], reply_markup=ui.main_menu(lang_code))
            if voice_on and send_voice:
                await send_voice(chat_id, T['greeting'])
            await dbmod.clear_state(chat_id)
            return
        # if awaiting medication name
        if state == "awaiting_med_name":
            title = text
            await dbmod.set_state(chat_id, "awaiting_time", {"title": title})
            slots = generate_time_slots()
            await send_message(chat_id, T['ask_time'], reply_markup=ui.time_buttons(slots))
            return
        # if awaiting custom time
        if state == "awaiting_custom_time":
            if re.match(r'^(?:[01]\d|2[0-3]):[0-5]\d$', text):
                temp = temp or {}
                temp['time'] = text
                await dbmod.set_state(chat_id, "awaiting_repeat", temp)
                await send_message(chat_id, T['ask_repeat'], reply_markup=ui.repeat_buttons(lang_code))
            else:
                await send_message(chat_id, T['ask_custom_time'])
            return
        # legacy quick add: "Dori: name, HH:MM, daily"
        if text.lower().startswith("dori:") or text.lower().startswith("add:"):
            try:
                parts = text.split(":",1)[1].strip().split(",")
                title = parts[0].strip()
                time_str = parts[1].strip() if len(parts)>1 else "08:00"
                recurring = parts[2].strip() if len(parts)>2 else "daily"
                rid = await dbmod.add_reminder(chat_id, title, time_str, recurring)
                await send_message(chat_id, T['added'].format(title=title, time=time_str, recurring=recurring))
            except Exception:
                await send_message(chat_id, "Format xato. Iltimos: Dori: Nomi, HH:MM, daily|weekly")
            return
        # default echo
        await send_message(chat_id, "Echo: " + text)
