
def main_menu():
    keyboard = {
        "inline_keyboard": [
            [{"text": "💊 Dori qo'shish", "callback_data": "add_med"}],
            [{"text": "📋 Dorilarim", "callback_data": "my_meds"}],
            [{"text": "📊 Hisobot", "callback_data": "report"}],
            [{"text": "⚙️ Sozlamalar", "callback_data": "settings"}]
        ]
    }
    return keyboard

def time_choices():
    keys = []
    for h in range(6, 24):
        keys.append([{"text": f"{h:02d}:00", "callback_data": f"time_{h:02d}_00"}])
        keys.append([{"text": f"{h:02d}:30", "callback_data": f"time_{h:02d}_30"}])
    return {"inline_keyboard": keys}

def repeat_choices():
    return {"inline_keyboard": [[{"text":"Har kuni","callback_data":"repeat_daily"}],[{"text":"Haftada 1 marta","callback_data":"repeat_weekly"}]]}
