
import asyncio
from datetime import datetime
from utils import dbmod, voice

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

LANGS = {"uz": "🇺🇿", "ru": "🇷🇺", "en": "🇬🇧"}

# --------------- HANDLERS ---------------

async def handle_message(update, send_message, send_voice):
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "").strip()

    state = await dbmod.get_user_state(chat_id)

    # START команда
    if text == "/start":
        await send_main_menu(chat_id, send_message)
        return

    # Номинация лекарства
    if state and state.get("step") == "await_med_name":
        await dbmod.set_user_state(chat_id, {"step": "await_med_time", "title": text})
        keyboard = {
            "inline_keyboard": [[{"text": t, "callback_data": f"time_{t}"}] for t in TIME_CHOICES] +
            [[{"text": "⏰ Boshqa vaqt kiritish", "callback_data": "custom_time"}]]
        }
        await send_message(chat_id, f"💊 {text} uchun vaqtni tanlang:", keyboard)
        return

    # Кастомное время
    if state and state.get("step") == "await_custom_time":
        try:
            datetime.strptime(text, "%H:%M")
            await save_medicine(chat_id, state["title"], text, send_message, send_voice)
            await dbmod.clear_user_state(chat_id)
        except ValueError:
            await send_message(chat_id, "❌ Noto‘g‘ri format. Masalan: 14:30")
        return

    await send_message(chat_id, "ℹ️ Buyruqni tanlang yoki menyudan foydalaning.")

async def handle_callback(callback, send_message, send_voice):
    cq_data = callback.get("data")
    msg = callback.get("message", {})
    chat_id = msg.get("chat", {}).get("id")

    if not cq_data:
        return

    # --- Main Menu ---
    if cq_data == "add_med":
        await dbmod.set_user_state(chat_id, {"step": "await_med_name"})
        await send_message(chat_id, "💊 Dori nomini kiriting (misol: Paracetamol)")
        return

    if cq_data == "my_meds":
        meds = await dbmod.get_all_meds(chat_id)
        if not meds:
            await send_message(chat_id, "📭 Sizda hali dori eslatmalari yo‘q.")
        else:
            inline = [[{"text": f"❌ {m['title']} ({m['time']})", "callback_data": f"del_{m['id']}"}] for m in meds]
            await send_message(chat_id, "📋 Sizning dorilaringiz:", {"inline_keyboard": inline})
        return

    if cq_data == "report":
        meds = await dbmod.get_recent_meds(chat_id, limit=5)
        if not meds:
            await send_message(chat_id, "📊 Hisobot: bugungi eslatmalar ro‘yxati hali yo‘q.")
        else:
            lines = [f"{m['title']} — {m['time']}" for m in meds]
            await send_message(chat_id, "📊 So‘nggi 5 eslatma:\n" + "\n".join(lines))
        return

    if cq_data == "settings":
        await show_settings(chat_id, send_message)
        return

    # --- Settings ---
    if cq_data == "lang":
        lang_buttons = [[{"text": f"{v}", "callback_data": f"lang_{k}"}] for k, v in LANGS.items()]
        await send_message(chat_id, "🌐 Tilni tanlang:", {"inline_keyboard": lang_buttons})
        return

    if cq_data.startswith("lang_"):
        lang_code = cq_data.split("_")[1]
        await dbmod.set_user_lang(chat_id, lang_code)
        await send_message(chat_id, f"✅ Til tanlandi: {LANGS.get(lang_code, lang_code)}")
        return

    if cq_data == "voice":
        current = await dbmod.toggle_voice(chat_id)
        await send_message(chat_id, f"🔈 Ovozli eslatmalar: {'✅ Yoqilgan' if current else '❌ O‘chirilgan'}")
        return

    if cq_data == "tz":
        await send_message(chat_id, "⏱ Vaqt zonasi hozircha avtomatik Asia/Tashkent.")
        return

    if cq_data == "back":
        await send_main_menu(chat_id, send_message)
        return

    # --- Time selection ---
    if cq_data.startswith("time_"):
        med_time = cq_data.replace("time_", "")
        state = await dbmod.get_user_state(chat_id)
        if state and "title" in state:
            await save_medicine(chat_id, state["title"], med_time, send_message, send_voice)
            await dbmod.clear_user_state(chat_id)
        else:
            await send_message(chat_id, "⚠️ Dori nomi topilmadi, qayta urinib ko‘ring.")
        return

    if cq_data == "custom_time":
        state = await dbmod.get_user_state(chat_id)
        if state and "title" in state:
            await dbmod.set_user_state(chat_id, {"step": "await_custom_time", "title": state["title"]})
            await send_message(chat_id, "⏰ Iltimos, vaqtni HH:MM formatida kiriting.")
        return

    # --- Delete medicine ---
    if cq_data.startswith("del_"):
        med_id = cq_data.replace("del_", "")
        await dbmod.delete_med(chat_id, med_id)
        await send_message(chat_id, "🗑 Dori o‘chirildi.")
        return


# --------------- UI HELPERS ---------------

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


async def save_medicine(chat_id, title, time_str, send_message, send_voice):
    await dbmod.add_medicine(chat_id, title, time_str)
    confirm = f"✅ {title} dori {time_str} da ichilishini eslatma sifatida qo‘shildi!"
    await send_message(chat_id, confirm)
    try:
        await send_voice(chat_id, confirm)
    except Exception:
        pass
