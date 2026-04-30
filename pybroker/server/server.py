import asyncio
import logging

from pybroker.server.broker import Broker
from pybroker.server.connection import Connection
from pybroker.server.metrics import Metrics
from pybroker.server.protocol import read_frame
from pybroker.server.storage import Storage

log = logging.getLogger(__name__)


class BrokerServer:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9090,
        db_path: str = "data/broker.db",
        metrics_interval: float = 30.0,
    ):
        self._host = host
        self._port = port
        self._storage = Storage(db_path)
        self._metrics = Metrics()
        self._broker = Broker(self._storage, self._metrics)
        self._metrics_interval = metrics_interval

    async def start(self):
        await self._storage.initialize()
        await self._broker.restore()

        server = await asyncio.start_server(
            self._handle_client, self._host, self._port
        )
        log.info("PyBroker started on %s:%d", self._host, self._port)

        async with server:
            tasks = [
                asyncio.create_task(self._timeout_loop()),
                asyncio.create_task(self._expiry_loop()),
                asyncio.create_task(self._metrics_loop()),
            ]
            try:
                await server.serve_forever()
            finally:
                for task in tasks:
                    task.cancel()
                await self._storage.close()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        connection = Connection(reader, writer)
        self._broker.register(connection)

        try:
            while True:
                frame = await read_frame(reader)
                if frame is None:
                    break
                await self._broker.handle_frame(connection, frame)
        except Exception:
            log.exception("Error handling client %s", connection.peer)
        finally:
            await self._broker.unregister(connection)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _timeout_loop(self):
        while True:
            await asyncio.sleep(1)
            try:
                await self._broker.check_timeouts()
            except Exception:
                log.exception("Error in timeout check")

    async def _expiry_loop(self):
        while True:
            await asyncio.sleep(1)
            try:
                await self._broker.purge_expired()
            except Exception:
                log.exception("Error in expiry purge")

    async def _metrics_loop(self):
        while True:
            await asyncio.sleep(self._metrics_interval)
            log.info("metrics: %s", self._metrics.format())
