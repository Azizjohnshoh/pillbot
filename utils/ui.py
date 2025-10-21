
from datetime import datetime, timedelta
import pytz, json

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

def generate_time_buttons(tz_name="Asia/Tashkent", slots=6):
    tz = pytz.timezone(tz_name)
    now = datetime.now(tz)
    # round up to next 30-min slot
    minute = 30 if now.minute >= 30 else 0
    base = now.replace(minute=minute, second=0, microsecond=0)
    times = []
    for i in range(slots):
        t = base + timedelta(minutes=30*i)
        times.append(t.strftime("%H:%M"))
    rows = []
    for i in range(0, len(times), 2):
        row = []
        row.append({"text": times[i], "callback_data": f"time_{times[i]}"})
        if i+1 < len(times):
            row.append({"text": times[i+1], "callback_data": f"time_{times[i+1]}"})
        rows.append(row)
    # add custom time button
    rows.append([{"text":"🕐 Boshqa vaqt", "callback_data":"time_custom"}])
    return {"inline_keyboard": rows}

def repeat_choices():
    return {"inline_keyboard": [[{"text":"Har kuni","callback_data":"repeat_daily"}],[{"text":"Faqat bir marta","callback_data":"repeat_once"}]]}
