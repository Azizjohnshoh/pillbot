
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
