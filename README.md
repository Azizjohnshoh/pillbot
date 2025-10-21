# 💊 PillBot 4.6 Ultimate — Multilingual + AutoVoice Reminder Bot

**PillBot 4.6** — aqlli Telegram bot bo‘lib, foydalanuvchilarga dori ichish vaqtini eslatadi.  
Bot **Webhook** arxitekturasi asosida ishlaydi va **Render.com**’da barqaror ishlash uchun **autoping** funksiyasi bilan to‘liq avtomatlashtirilgan.  
Barcha asosiy xabarlar avtomatik tarzda **ovozli shaklda** yuboriladi (gTTS orqali).

---

## 🚀 Deploy to Render

### 🔹 1 bosishda joylashtirish (Deploy)
👇  
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Azizjohnshoh/pillbot)

---

## 🧩 Asosiy imkoniyatlar

| Imkoniyat | Tavsif |
|------------|--------|
| ✅ **Webhook rejimi** | 409 xatosiz, tez va barqaror ishlaydi. |
| 🔁 **Avtoping (keepalive)** | Render bepul rejimida botni “uyg‘oq” holatda ushlab turadi (har 14 daqiqada ping). |
| 🔊 **Ovozli eslatmalar** | gTTS orqali barcha eslatmalar ovozli tarzda yuboriladi. |
| 🧠 **Interaktiv menyu** | Dorilarni qo‘shish, ko‘rish, o‘chirish va tahrirlash. |
| ⚙️ **Sozlamalar (Settings)** | Til, ovozli bildirishlar, vaqt zonasi. |
| 📊 **Hisobot (Report)** | Dorilar soni, kunlik holat. |
| 📤 **CSV eksport** | Dorilar ro‘yxatini `.csv` faylga eksport qiladi. |
| 🕐 **Moslashtiriladigan vaqt tanlovi** | Foydalanuvchi o‘zi istagan vaqtni kiritishi mumkin. |
| 🌐 **Multitil (UZ/RU)** | Til avtomatik aniqlanadi, o‘zgartirish menyuda mavjud. |
| 💬 **Avtoovoz** | Har bir eslatma ovozli o‘qib eshittiriladi. |

---

## ⚙️ Muhit sozlamalari (Environment Variables)

| Kalit | Tavsif | Standart qiymat |
|-------|---------|----------------|
| `TELEGRAM_TOKEN` | Telegram bot tokeni | 🔑 (o‘zing qo‘shasan) |
| `ENABLE_VOICE` | Ovozli eslatmalar | `True` |
| `VOICE_LANG` | Ovoz tili | `uz` |
| `BASE_URL` | Botning URL manzili | `https://pillbot-4-6.onrender.com` |
| `DEFAULT_TIMEZONE` | Vaqt zonasi | `Asia/Tashkent` |
| `ADMIN_CHAT` | (Ixtiyoriy) Admin xabarnomalar uchun chat_id | — |

---

## 🧠 Texnologiyalar

- 🐍 Python 3.12+
- ⚡ FastAPI + Uvicorn
- 🕓 APScheduler (rejalashtirish)
- 🗂️ aiosqlite (ma’lumotlar bazasi)
- 🌐 aiohttp (HTTP so‘rovlar)
- 🗣️ gTTS (ovozli bildirishlar)
- 🔄 Webhook arxitekturasi (409-free)
- ☁️ Render (bepul hosting)

---

## 📋 Ishlash printsipi

1️⃣ Foydalanuvchi `/start` yozadi  
2️⃣ Bot salomlashadi (ovoz bilan):  
   > 👋 Assalomu alaykum! Dori eslatish botiga hush kelibsiz!  
   > Quyidagi menyudan kerakli bo‘limni tanlang.  
3️⃣ Tugmalar:
   - 💊 Dori qo‘shish → vaqt tanlash → qaytarilish turi
   - 📋 Dorilarim → mavjud ro‘yxat
   - ⚙️ Sozlamalar → Til / Ovoz / Ortga
4️⃣ Har bir yangi eslatma uchun bot ovozli tasdiq beradi.  

---

## 🌐 Render’da ishga tushirish

1️⃣ GitHub’ga kodingni yukla (`Upload files via GitHub`).  
2️⃣ Render’da yangi **Web Service** yarat.  
3️⃣ **Environment Variables** bo‘limiga yuqoridagi kalitlarni qo‘sh.  
4️⃣ Deploy bosilgach — bot avtomatik tarzda webhook o‘rnatadi.  
5️⃣ Telegram’da `/start` yuborib test qil.  

---

## 🔊 Demo ovoz

Ovozli eslatmalar `gTTS` orqali tayyorlanadi, `uz` va `ru` tillarida tabiiy ovozda yangraydi.  
> Misol: “Paracetamolni soat sakkizda iching.”

---

© 2025 — **PillBot Team (Azizjohnshoh Edition)**  
Licensed under MIT
