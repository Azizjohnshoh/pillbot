
def main_menu(lang='uz'):
    return {"inline_keyboard":[[{"text":"💊 Dori qo'shish","callback_data":"add_med"}],[{"text":"📋 Dorilarim","callback_data":"my_meds"}],[{"text":"📊 Hisobot","callback_data":"report"}],[{"text":"⚙️ Sozlamalar","callback_data":"settings"}]]}

def time_buttons(times):
    rows = []
    for i in range(0, len(times), 2):
        row = []
        row.append({"text": times[i], "callback_data": f"time_{times[i]}"})
        if i+1 < len(times):
            row.append({"text": times[i+1], "callback_data": f"time_{times[i+1]}"})
        rows.append(row)
    rows.append([{"text":"🕐 Boshqa vaqt","callback_data":"time_custom"}])
    return {"inline_keyboard": rows}

def repeat_buttons(lang='uz'):
    if lang=='ru':
        return {"inline_keyboard":[[{"text":"Каждый день","callback_data":"repeat_daily"}],[{"text":"Только раз","callback_data":"repeat_once"}]]}
    return {"inline_keyboard":[[{"text":"Har kuni","callback_data":"repeat_daily"}],[{"text":"Faqat bir marta","callback_data":"repeat_once"}]]}

def settings_menu(lang='uz', voice_on=True):
    voice_text = "🔊 Ovoz: On" if voice_on else "🔇 Ovoz: Off"
    lang_text = "🇺🇿 Til: O'zbek" if lang=='uz' else "🇷🇺 Til: Русский"
    return {"inline_keyboard":[[{"text":lang_text,"callback_data":"set_lang"}],[{"text":voice_text,"callback_data":"toggle_voice"}],[{"text":"🔙 Ortga","callback_data":"back"}]]}
