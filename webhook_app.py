
"""Webhook entrypoint for PillBot Ultra Pro Max (Render-compatible).
Token is taken from environment variable TELEGRAM_TOKEN.
"""
import os, logging
from fastapi import FastAPI, Request
import aiohttp, asyncio

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("Missing TELEGRAM_TOKEN in environment variables")

BOT_API = f"https://api.telegram.org/bot{TOKEN}"

app = FastAPI()
log = logging.getLogger("pillbot_webhook")
logging.basicConfig(level=logging.INFO)

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    log.info(f"Incoming update: {data}")
    # Example response: echo the received message text back
    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"]["text"]
        async with aiohttp.ClientSession() as session:
            await session.post(f"{BOT_API}/sendMessage", json={
                "chat_id": chat_id,
                "text": f"Echo: {text}"
            })
    return {"ok": True}

@app.get("/")
async def root():
    return {"status": "PillBot Ultra Pro Max Webhook active"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
