
import json, os
from aiohttp import web
cfg = {}
try:
    with open('config_example.json','r',encoding='utf-8') as f:
        cfg = json.load(f)
except Exception:
    cfg = {}
PORT = int(os.getenv("KEEPALIVE_PORT", cfg.get("KEEPALIVE_PORT", 10000)))
async def handle(req):
    return web.Response(text='PillBot KeepAlive OK')
app = web.Application()
app.router.add_get('/', handle)
if __name__ == '__main__':
    web.run_app(app, port=PORT)
