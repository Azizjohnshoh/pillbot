from aiohttp import web
import os

async def handle(request):
    return web.Response(text="PillBot Ultra Pro Max v4.6 — alive")

def run_keepalive():
    app = web.Application()
    app.router.add_get('/', handle)
    port = int(os.environ.get("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)
