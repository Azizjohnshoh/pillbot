# 💊 PillBot 4.2 — Professional Medication Reminder Bot

**PillBot 4.2** — aqlli Telegram bot bo‘lib, foydalanuvchilarga dori ichish vaqtini eslatadi.  
Bot to‘liq tayyor **Webhook** arxitekturasi bilan ishlaydi, Render.com’da barqaror ishlashi uchun **avtoping** funksiyasi bilan ta’minlangan.  

---

## 🚀 Asosiy imkoniyatlar

✅ **Webhook rejimi** — 409 xatosiz, barqaror va tez javob beradi.  
✅ **Avtoping (keepalive)** — Render free rejimida botni “uyg‘oq” ushlab turadi (har 14 daqiqada ping).  
✅ **Ovozli eslatmalar** — gTTS orqali eslatmani ovozli shaklda yuboradi.  
✅ **Interaktiv menyu** — dorilarni qo‘shish, ko‘rish, o‘chirish, tahrirlash.  
✅ **Sozlamalar** — vaqt zonasi, ovozli bildirishlar, til.  
✅ **Hisobot** — barcha eslatmalarni ro‘yxatda ko‘rish.  
✅ **CSV eksport** — barcha dorilarni `.csv` faylga eksport qilish.  
✅ **Asinxron arxitektura** — `FastAPI`, `aiohttp`, `aiosqlite`, `APScheduler` asosida.

---

## ⚙️ Muhit sozlamalari (Environment Variables)

| Kalit | Tavsif | Standart qiymat |
|-------|---------|----------------|
| `TELEGRAM_TOKEN` | Telegram bot tokeni | 🔒 (o‘zing qo‘shasan) |
| `ENABLE_VOICE` | Ovozli eslatmalar | True |
| `VOICE_LANG` | Ovoz tili | uz |
| `BASE_URL` | Bot URL manzili | https://pillbot-4-2.onrender.com |
| `DEFAULT_TIMEZONE` | Vaqt zonasi | Asia/Tashkent |

---

## 🧠 Texnologiyalar

- Python 3.12.5  
- FastAPI + Uvicorn  
- APScheduler (rejalashtiruvchi)  
- aiosqlite (ma’lumotlar bazasi)  
- aiohttp (HTTP mijoz)  
- gTTS (ovozli bildirishlar)

---

## 🔧 Render’da deploy qilish

1️⃣ GitHub’da `pillbot-4.2` reposini tayyorla.  
2️⃣ [Render.com](https://render.com) da **New Web Service** yarat.  
3️⃣ Muhit o‘zgaruvchilarini (`Environment Variables`) quyidagicha sozla:  

