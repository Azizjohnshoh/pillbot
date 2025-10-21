
import asyncio
from datetime import datetime, timedelta
from utils import dbmod, ui, voice, lang

# Бу callback_data мос келадиган форматда бўлиши керак
MAIN_MENU = {
    "add_med": "💊 Dori qo’shish",
    "my_meds": "📋 Dorilarim",
    "report": "📊 Hisobot",
    "settings": "⚙️ Sozlamalar"
}

SETTINGS_MENU = {
    "lang": "🌐 Til",
    "voice": "🔈 Ovoz",
    "tz": "⏱ Vaqt zonasi",
    "back": "⬅️ Orqaga"
}

TIME_CHOICES = ["08:00", "12:00", "18:00", "22:00"]

async def handle_message(update, send_message, send_voice):
    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    # Agar foydalanuvchi /start yuborsa
    if text == "/start":
        await send_main_menu(chat_id, send_message)
        return

    # Agar foydalanuvchi dorining nomini yuborgan bo‘lsa
    user_state = await dbmod.get_user_state(chat_id)
    if user_state and user_state.get("step") == "await_med_name":
        await dbmod.set_user_state(chat_id, {"step": "await_med_time", "title": text})
        keyboard = {
            "inline_keyboard": [[{"text": t, "callback_data": f"time_{t}"}] for t in TIME_CHOICES] +
            [[{"text": "⏰ Boshqa vaqt kiritish", "callback_data": "custom_time"}]]
        }
        await send_message(chat_id, "⏰ Qachon ichasiz?", keyboard)
        return

    # Agar foydalanuvchi maxsus vaqt kiritayotgan bo‘lsa
    if user_state and user_state.get("step") == "await_custom_time":
        try:
            datetime.strptime(text, "%H:%M")
            await save_medicine(chat_id, user_state["title"], text, send_message)
            await dbmod.clear_user_state(chat_id)
        except ValueError:
            await send_message(chat_id, "❌ Noto‘g‘ri format. Masalan: 14:30")
        return

    # Boshqa holatlar учун
    await send_message(chat_id, f"Echo: {text}")

async def handle_callback(callback, send_message, send_voice):
    cq_data = callback.get("data")
    msg = callback.get("message", {})
    chat_id = msg.get("chat", {}).get("id")

    if not cq_data:
        return

    # Asosiy menyu tugmalari
    if cq_data in MAIN_MENU.keys():
        if cq_data == "add_med":
            await dbmod.set_user_state(chat_id, {"step": "await_med_name"})
            await send_message(chat_id, "💊 Dori nomini kiriting (misol: Paracetamol)")
        elif cq_data == "my_meds":
            meds = await dbmod.get_all_meds(chat_id)
            if not meds:
                await send_message(chat_id, "Hech qanday dori topilmadi.")
            else:
                text = "📋 Sizning dorilaringiz:\n" + "\n".join([f"{m['title']} — {m['time']}" for m in meds])
                await send_message(chat_id, text)
        elif cq_data == "report":
            await send_message(chat_id, "📊 Hisobot: bugungi eslatmalar ro‘yxati hali qo‘shilmagan.")
        elif cq_data == "settings":
            await show_settings(chat_id, send_message)
        return

    # Sozlamalar menyusi
    if cq_data in SETTINGS_MENU.keys():
        if cq_data == "back":
            await send_main_menu(chat_id, send_message)
            return
        if cq_data == "lang":
            await send_message(chat_id, "🌐 Tilni tanlang: 🇺🇿 / 🇷🇺 / 🇬🇧")
        if cq_data == "voice":
            current = await dbmod.toggle_voice(chat_id)
            await send_message(chat_id, f"🔈 Ovozli eslatmalar: {'✅ Yoqilgan' if current else '❌ O‘chirilgan'}")
        if cq_data == "tz":
            await send_message(chat_id, "⏱ Vaqt zonasi hozircha avtomatik Asia/Tashkent.")
        return

    # Tanlangan vaqt
    if cq_data.startswith("time_"):
        med_time = cq_data.replace("time_", "")
        state = await dbmod.get_user_state(chat_id)
        if not state or "title" not in state:
            await send_message(chat_id, "⚠️ Dori nomi topilmadi, qayta boshlang.")
            await send_main_menu(chat_id, send_message)
            return
        await save_medicine(chat_id, state["title"], med_time, send_message)
        await dbmod.clear_user_state(chat_id)
        return

    if cq_data == "custom_time":
        await dbmod.set_user_state(chat_id, {"step": "await_custom_time", "title": (await dbmod.get_user_state(chat_id)).get("title")})
        await send_message(chat_id, "⏰ Iltimos, vaqtni HH:MM formatida kiriting.")
        return

async def send_main_menu(chat_id, send_message):
    keyboard = {
        "inline_keyboard": [
            [{"text": MAIN_MENU["add_med"], "callback_data": "add_med"}],
            [{"text": MAIN_MENU["my_meds"], "callback_data": "my_meds"}],
            [{"text": MAIN_MENU["report"], "callback_data": "report"}],
            [{"text": MAIN_MENU["settings"], "callback_data": "settings"}],
        ]
    }
    text = "👋 Assalomu alaykum! Dori eslatish botiga hush kelibsiz!\nQuyidagi menyudan kerakli bo‘limni tanlang:"
    await send_message(chat_id, text, keyboard)

async def show_settings(chat_id, send_message):
    keyboard = {
        "inline_keyboard": [
            [{"text": SETTINGS_MENU["lang"], "callback_data": "lang"}],
            [{"text": SETTINGS_MENU["voice"], "callback_data": "voice"}],
            [{"text": SETTINGS_MENU["tz"], "callback_data": "tz"}],
            [{"text": SETTINGS_MENU["back"], "callback_data": "back"}]
        ]
    }
    await send_message(chat_id, "⚙️ Sozlamalar:", keyboard)

async def save_medicine(chat_id, title, time_str, send_message):
    await dbmod.add_medicine(chat_id, title, time_str)
    await send_message(chat_id, f"✅ {title} dori {time_str} da ichilishini eslatma sifatida qo‘shildi!")
