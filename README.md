
# 💊 PillBot Ultra Pro Max — v4.2 Ultimate

**PillBot Ultra Pro Max** — это умный Telegram-бот для напоминаний о приёме лекарств, 
полностью готовый к деплою на **Render.com** с поддержкой **webhook** и голосовых уведомлений.

---

## 🚀 Deploy to Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

Нажми кнопку выше, чтобы автоматически развернуть PillBot Ultra Pro Max на Render.  
Render создаст Python Web Service, используя файл `render.yaml` из этого репозитория.

---

## 🧩 Основные возможности

✅ Добавление, удаление и редактирование напоминаний  
✅ Ежедневные (повторяющиеся) напоминания  
✅ Отложенные уведомления (Snooze)  
✅ Голосовые уведомления через gTTS  
✅ Экспорт и импорт данных в CSV  
✅ Полностью на асинхронном Python (aiosqlite + APScheduler)  
✅ Uzbek интерфейс кнопок: “Dori qo’shish”, “Dorilarim”, “Hisobot”, “Sozlamalar”  
✅ Webhook-режим для Render (без getUpdates конфликтов)

---

## ⚙️ Настройка окружения (Render Environment Variables)

| Key | Value |
|-----|--------|
| `TELEGRAM_TOKEN` | 🔑 Твой токен от BotFather |
| `ENABLE_VOICE` | `True` |
| `VOICE_LANG` | `uz` |
| `KEEPALIVE_PORT` | `10000` |
| `USE_WEBHOOK` | `True` |
| `DEFAULT_TIMEZONE` | `Asia/Tashkent` |
| `WEBHOOK_URL` | `https://pillbot-ultra-pro-max.onrender.com/webhook` |

---

## 🏗️ Структура проекта

```
/pillbot-ultra-pro-max/
│
├── bot.py                  # основной бот (polling mode)
├── webhook_app.py           # FastAPI вебхук сервер
├── keepalive.py             # сервер для Render keep-alive
├── utils/                   # модули (db, scheduler, voice, csv)
├── data/pillbot.db          # пример SQLite база
├── render.yaml              # конфигурация Render auto-deploy
├── Procfile                 # команда старта Render
├── config_example.json      # пример конфига (webhook включён)
├── .env.example             # пример переменных окружения
└── README.md                # эта инструкция
```

---

## 🔧 Локальный запуск

```bash
pip install -r requirements.txt
python bot.py
```

или для webhook-сервера:
```bash
python webhook_app.py
```

---

## 💬 Авторы и лицензия

Автор проекта: **Azizjon Shoxnazarov**  
Лицензия: MIT License  
(c) 2025 PillBot Ultra Pro Max
