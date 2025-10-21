
import asyncio, re
from datetime import datetime
from utils import dbmod, ui, lang

# Primary handlers used by webhook_app
async def handle_message(update, send_message, send_voice):
    msg = update.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    text = msg.get("text", "").strip() if msg.get("text") else ""
    from_user = msg.get("from", {}).get("first_name", "")

    # ensure user exists
    await dbmod.ensure_user(chat_id, from_user)

    # if /start command
    if text.startswith("/start"):
        # greet only if user has no reminders (first time)
        meds = await dbmod.list_reminders_for_chat(chat_id)
        T = lang.TEXT.get((await dbmod.get_user_prefs(chat_id))[0], lang.TEXT['uz'])
        if not meds:
            await send_message(chat_id, T['greeting'] + "\\n" + T['start_menu'], reply_markup=ui.main_menu(T and 'uz' or 'uz'))
            if (await dbmod.get_user_prefs(chat_id))[1] and send_voice:
                await send_voice(chat_id, T['greeting'], lang_code=(await dbmod.get_user_prefs(chat_id))[0])
        else:
            await send_message(chat_id, T['start_menu'], reply_markup=ui.main_menu((await dbmod.get_user_prefs(chat_id))[0]))
        return

    # handle free-text quick add: "Dori:Name,HH:MM"
    if text.lower().startswith("dori:") or text.lower().startswith("add:"):
        try:
            parts = text.split(":",1)[1].split(",")
            title = parts[0].strip()
            time_str = parts[1].strip() if len(parts)>1 else "08:00"
            rid = await dbmod.add_reminder(chat_id, title, time_str, "once")
            T = lang.TEXT.get((await dbmod.get_user_prefs(chat_id))[0], lang.TEXT['uz'])
            await send_message(chat_id, T['added'].format(title=title, time=time_str, recurring="once"))
            if (await dbmod.get_user_prefs(chat_id))[1]:
                await send_voice(chat_id, T['added'].format(title=title, time=time_str, recurring="once"), lang_code=(await dbmod.get_user_prefs(chat_id))[0])
        except Exception:
            await send_message(chat_id, "Format xato. Iltimos: Dori: Nomi, HH:MM")
        return

    # if user is in a state waiting for custom time/name etc - defer to dbmod.get_state
    state, temp = await dbmod.get_state(chat_id)
    if state == "awaiting_custom_time":
        if re.match(r'^(?:[01]\\d|2[0-3]):[0-5]\\d$', text):
            title = temp.get("title") if temp else "NoName"
            time_str = text
            await dbmod.add_reminder(chat_id, title, time_str, "once")
            T = lang.TEXT.get((await dbmod.get_user_prefs(chat_id))[0], lang.TEXT['uz'])
            await send_message(chat_id, T['added'].format(title=title, time=time_str, recurring="once"))
            if (await dbmod.get_user_prefs(chat_id))[1]:
                await send_voice(chat_id, T['added'].format(title=title, time=time_str, recurring="once"), lang_code=(await dbmod.get_user_prefs(chat_id))[0])
            await dbmod.clear_state(chat_id)
        else:
            T = lang.TEXT.get((await dbmod.get_user_prefs(chat_id))[0], lang.TEXT['uz'])
            await send_message(chat_id, T['ask_custom_time'])
        return

    # fallback echo
    if text:
        await send_message(chat_id, "Echo: " + text)

async def handle_callback(callback, send_message, send_voice):
    cq = callback
    data = cq.get("data","")
    msg = cq.get("message",{})
    chat_id = msg.get("chat",{}).get("id")
    T = lang.TEXT.get((await dbmod.get_user_prefs(chat_id))[0], lang.TEXT['uz'])
    log_prefix = f"[Callback:{data}]"

    # Debug log message by sending to admin (optional) - avoid spamming general users
    # Main menu
    if data == "add_med":
        await dbmod.set_state(chat_id, "awaiting_med_name", {})
        await send_message(chat_id, T['ask_med_name'])
        return
    if data == "my_meds":
        meds = await dbmod.list_reminders_for_chat(chat_id)
        if not meds:
            await send_message(chat_id, T['no_meds'])
        else:
            for r in meds:
                await send_message(chat_id, f\"{r['id']}: {r['title']} @ {r['time']} [{r.get('recurring')}]\" )
        return
    if data == "report":
        meds = await dbmod.list_reminders_for_chat(chat_id)
        await send_message(chat_id, T['report'].format(total=len(meds)))
        return
    if data == "settings":
        await send_message(chat_id, T['settings'], reply_markup=ui.settings_menu((await dbmod.get_user_prefs(chat_id))[0], voice_on=bool((await dbmod.get_user_prefs(chat_id))[1])) )
        return

    # time chosen from inline buttons: time_ HH:MM
    if data.startswith("time_"):
        time_chosen = data.split("_",1)[1]
        state, temp = await dbmod.get_state(chat_id)
        title = temp.get("title") if temp else None
        if not title:
            await send_message(chat_id, T['ask_med_name'])
            await dbmod.set_state(chat_id, "awaiting_med_name", {})
            return
        await dbmod.add_reminder(chat_id, title, time_chosen, "daily")
        await dbmod.clear_state(chat_id)
        await send_message(chat_id, T['added'].format(title=title, time=time_chosen, recurring="daily"))
        if (await dbmod.get_user_prefs(chat_id))[1]:
            await send_voice(chat_id, T['added'].format(title=title, time=time_chosen, recurring="daily"), lang_code=(await dbmod.get_user_prefs(chat_id))[0])
        return

    if data == "time_custom":
        state, temp = await dbmod.get_state(chat_id)
        await dbmod.set_state(chat_id, "awaiting_custom_time", temp or {})
        await send_message(chat_id, T['ask_custom_time'])
        return

    if data.startswith("set_lang_"):
        new_lang = data.split("_",2)[2]
        await dbmod.set_user_prefs(chat_id, language=new_lang)
        await send_message(chat_id, T['lang_set'].format(lang=new_lang))
        return

    if data == "toggle_voice":
        current = (await dbmod.get_user_prefs(chat_id))[1]
        await dbmod.set_user_prefs(chat_id, voice_enabled=0 if current else 1)
        await send_message(chat_id, T['voice_off'] if current else T['voice_on'])
        return

    if data.startswith("del_"):
        rid = int(data.split("_",1)[1])
        await dbmod.delete_reminder(rid)
        await send_message(chat_id, T['confirm_delete'])
        return

    # fallback
    await send_message(chat_id, "⚠️ Amal topilmadi.")
