import time
from pathlib import Path

from aiohttp import web

STATIC_DIR = Path(__file__).parent / "static"


class WebUI:
    def __init__(self, broker, host: str = "0.0.0.0", port: int = 8080):
        self._broker = broker
        self._host = host
        self._port = port
        self._started_at = time.time()

    async def start(self):
        app = web.Application()
        app.router.add_get("/api/state", self._handle_state)
        app.router.add_get("/", self._handle_index)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self._host, self._port)
        await site.start()

    async def _handle_state(self, request):
        state = {
            "uptime": time.time() - self._started_at,
            "connections": self._broker.get_connections_info(),
            "topics": self._broker.get_topics_info(),
            "queues": self._broker.get_queues_info(),
            "metrics": self._broker.metrics.snapshot(),
        }
        return web.json_response(state)

    async def _handle_index(self, request):
        return web.FileResponse(STATIC_DIR / "index.html")
