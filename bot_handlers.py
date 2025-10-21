
import asyncio, re
from datetime import datetime
from utils import dbmod, ui, lang, voice

# --- Constants ---
DEFAULT_LANG = "uz"
TIME_CHOICES = ["08:00", "12:00", "18:00", "22:00"]

# --- Helpers ---
async def _get_user_prefs(chat_id):
    # should return (lang_code, voice_enabled)
    try:
        prefs = await dbmod.get_user_prefs(chat_id)
        if prefs:
            return prefs[0] or DEFAULT_LANG, bool(prefs[1])
    except Exception:
        pass
    return DEFAULT_LANG, True

# --- Message handler ---
async def handle_message(update, send_message, send_voice):
    msg = update.get("message", {})
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()

    # ensure user in DB
    try:
        await dbmod.ensure_user(chat_id, chat.get("first_name", ""))
    except Exception:
        pass

    # /start handling (greet only first time: if user has no reminders)
    if text.startswith("/start"):
        meds = await dbmod.list_reminders_for_chat(chat_id)
        lang_code, voice_on = await _get_user_prefs(chat_id)
        T = lang.TEXT.get(lang_code, lang.TEXT[DEFAULT_LANG])
        if not meds:
            await send_message(chat_id, T["greeting"] + "\n" + T["start_menu"], reply_markup=ui.main_menu(lang_code))
            if voice_on:
                await send_voice(chat_id, T["greeting"], lang_code=lang_code)
        else:
            await send_message(chat_id, T["start_menu"], reply_markup=ui.main_menu(lang_code))
        return

    # If user sending name while in "awaiting_med_name" state
    state, temp = await dbmod.get_state(chat_id)
    if state == "awaiting_med_name":
        title = text
        await dbmod.set_state(chat_id, "awaiting_med_time", {"title": title})
        # show time choices
        kb = {"inline_keyboard": [[{"text": t, "callback_data": f"time_{t}"}] for t in TIME_CHOICES] + [[{"text":"🕓 Boshqa vaqt kiritish","callback_data":"custom_time"}]]}
        await send_message(chat_id, "⏰ Qachon ichasiz? Tanlang yoki 'Boshqa vaqt' tugmasi orqali kiriting.", reply_markup=kb)
        return

    # If user sending custom time while in awaiting_custom_time
    if state == "awaiting_custom_time":
        if re.match(r'^(?:[01]\d|2[0-3]):[0-5]\d$', text):
            title = (temp or {}).get("title", "NoName")
            await dbmod.add_reminder(chat_id, title, text, "daily")
            await dbmod.clear_state(chat_id)
            lang_code, voice_on = await _get_user_prefs(chat_id)
            T = lang.TEXT.get(lang_code, lang.TEXT[DEFAULT_LANG])
            msg = T["added"].format(title=title, time=text, recurring="daily")
            await send_message(chat_id, msg)
            if voice_on:
                await send_voice(chat_id, msg, lang_code=lang_code)
        else:
            lang_code, _ = await _get_user_prefs(chat_id)
            T = lang.TEXT.get(lang_code, lang.TEXT[DEFAULT_LANG])
            await send_message(chat_id, T["ask_custom_time"])
        return

    # fallback: help hint
    await send_message(chat_id, "ℹ️ Buyruqni tanlang yoki menyudan foydalaning.", reply_markup=ui.main_menu(await _get_user_prefs(chat_id)[0]))

# --- Callback handler ---
async def handle_callback(callback, send_message, send_voice):
    cq = callback
    data = cq.get("data","")
    msg = cq.get("message",{})
    chat = msg.get("chat",{})
    chat_id = chat.get("id")
    lang_code, voice_on = await _get_user_prefs(chat_id)
    T = lang.TEXT.get(lang_code, lang.TEXT[DEFAULT_LANG])

    # --- main menu buttons (names aligned to ui.main_menu) ---
    if data == "add_medication":
        await dbmod.set_state(chat_id, "awaiting_med_name", {})
        await send_message(chat_id, T["ask_med_name"])
        return

    if data == "show_meds":
        meds = await dbmod.list_reminders_for_chat(chat_id)
        if not meds:
            await send_message(chat_id, T["no_meds"])
        else:
            lines = [f\"{r['id']}: {r['title']} — {r['time']}\" for r in meds]
            await send_message(chat_id, "📋 " + "\\n".join(lines))
        return

    if data == "show_report":
        meds = await dbmod.list_reminders_for_chat(chat_id)
        await send_message(chat_id, T["report"].format(total=len(meds)))
        return

    if data == "settings_menu":
        await send_message(chat_id, T["settings"], reply_markup=ui.settings_menu(lang_code, voice_on=voice_on))
        return

    # --- settings actions ---
    if data == "set_lang_uz" or data == "set_lang_ru" or data == "set_lang_en":
        new_lang = data.split("_")[-1]
        await dbmod.set_user_prefs(chat_id, language=new_lang)
        await send_message(chat_id, T["lang_set"].format(lang=new_lang))
        return

    if data == "toggle_voice":
        current = (await dbmod.get_user_prefs(chat_id))[1]
        await dbmod.set_user_prefs(chat_id, voice_enabled=0 if current else 1)
        await send_message(chat_id, T["voice_off"] if current else T["voice_on"])
        return

    if data == "tz_auto":
        await send_message(chat_id, "⏱ Vaqt zonasi hozircha avtomatik Asia/Tashkent.")
        return

    if data == "back_main":
        await send_message(chat_id, T["start_menu"], reply_markup=ui.main_menu(lang_code))
        return

    # --- time choices ---
    if data.startswith("time_"):
        time_chosen = data.split("_",1)[1]
        state, temp = await dbmod.get_state(chat_id)
        title = (temp or {}).get("title")
        if not title:
            await dbmod.set_state(chat_id, "awaiting_med_name", {})
            await send_message(chat_id, T["ask_med_name"])
            return
        await dbmod.add_reminder(chat_id, title, time_chosen, "daily")
        await dbmod.clear_state(chat_id)
        msg = T["added"].format(title=title, time=time_chosen, recurring="daily")
        await send_message(chat_id, msg)
        if voice_on:
            await send_voice(chat_id, msg, lang_code=lang_code)
        return

    if data == "custom_time":
        state, temp = await dbmod.get_state(chat_id)
        await dbmod.set_state(chat_id, "awaiting_custom_time", temp or {})
        await send_message(chat_id, T["ask_custom_time"])
        return

    # --- delete ---
    if data.startswith("delete_"):
        rid = int(data.split("_",1)[1])
        await dbmod.delete_reminder(rid)
        await send_message(chat_id, T["confirm_delete"])
        return

    # fallback
    await send_message(chat_id, "⚠️ Amal topilmadi.")
