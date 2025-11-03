#!/usr/bin/env python3
"""
Koyebデプロイ用プロジェクトのダミーワークフロー
実際のボットはKoyebで実行されます
"""
from aiohttp import web
import asyncio

async def health_check(request):
    return web.Response(text="OK - このプロジェクトはKoyebで実行されます")

async def start_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()
    print("✅ Dummy server running on port 8000")
    print("📦 このプロジェクトはKoyebでデプロイしてください")
    print("🚀 'python main.py' で実際のボットが起動します")
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(start_server())
