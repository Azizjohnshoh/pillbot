# 💊 PillBot Ultra Pro Max — v4.3 Full Webhook

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Azizjohnshoh/pillbot)

---

## 📘 Описание

**PillBot Ultra Pro Max v4.3** — умный Telegram-бот для напоминаний о приёме лекарств.  
Полностью готов к работе на **Render.com** с поддержкой **webhook**, **графика напоминаний**,  
**озвучки через gTTS** и **интерфейсом на узбекском языке**.

---

## 🚀 Основные возможности

✅ Добавление, удаление и редактирование напоминаний  
✅ Ежедневные (повторяющиеся) уведомления  
✅ Отложенные уведомления (Snooze)  
✅ Голосовые уведомления через **gTTS**  
✅ Экспорт и импорт данных в CSV  
✅ Поддержка узбекского интерфейса  
✅ Асинхронная работа на **FastAPI + APScheduler**  
✅ Полная поддержка **Render Webhook Mode** (без getUpdates)

---

## 🧭 Приветственное сообщение

При вводе `/start` бот отвечает:


И показывает главное меню:
- 💊 Dori qo‘shish  
- 📋 Dorilarim  
- 📊 Hisobot  
- ⚙️ Sozlamalar  

---

## ⚙️ Настройка окружения (Render Environment Variables)

| Key | Value | Description |
|-----|--------|-------------|
| `TELEGRAM_TOKEN` | 🔑 Твой токен от BotFather | (добавь вручную в Render → Environment) |
| `ENABLE_VOICE` | `True` | Включить голосовые уведомления |
| `VOICE_LANG` | `uz` | Язык озвучки |
| `KEEPALIVE_PORT` | `10000` | Для поддержания активности |
| `USE_WEBHOOK` | `True` | Активирует режим webhook |
| `DEFAULT_TIMEZONE` | `Asia/Tashkent` | Часовой пояс по умолчанию |
| `WEBHOOK_URL` | `https://pillbot-ultra-pro-max.onrender.com/webhook` | Адрес webhook |

---

## 🔧 Инструкция по деплою

1. Открой 👉 [Render Deploy](https://render.com/deploy?repo=https://github.com/Azizjohnshoh/pillbot)  
2. Нажми **Deploy Blueprint**  
3. Дождись завершения сборки и запуска сервиса  
4. После запуска добавь webhook командой (в PowerShell):

   ```powershell
   $TOKEN="ВАШ_ТОКЕН_БОТА"
   irm "https://api.telegram.org/bot$TOKEN/setWebhook?url=https://pillbot-ultra-pro-max.onrender.com/webhook"
