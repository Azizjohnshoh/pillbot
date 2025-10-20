
"""Tiny keepalive HTTP server (used on Render free to prevent idling in some setups).
Listens on port from config_example.json (default 10000).
"""
import asyncio, json, os
from aiohttp import web

with open('config_example.json','r',encoding='utf-8') as f:
    cfg=json.load(f)

PORT = cfg.get('KEEPALIVE_PORT', 10000)

async def handle(req):
    return web.Response(text='PillBot KeepAlive OK')

app = web.Application()
app.router.add_get('/', handle)

if __name__ == '__main__':
    web.run_app(app, port=PORT)
