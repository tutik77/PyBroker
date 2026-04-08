import asyncio
import logging
from typing import Awaitable, Callable

from pybroker.common.models import StompFrame
from pybroker.server.protocol import build_frame, read_frame

log = logging.getLogger(__name__)

MessageHandler = Callable[[StompFrame], Awaitable[None]]


class BrokerClient:
    def __init__(self, host: str = "localhost", port: int = 9090):
        self._host = host
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._handlers: dict[str, MessageHandler] = {}
        self._listener_task: asyncio.Task | None = None
        self._sub_counter = 0
        self._connected = False

    async def connect(self):
        self._reader, self._writer = await asyncio.open_connection(self._host, self._port)
        await self._send(StompFrame("CONNECT", {"accept-version": "1.2", "host": self._host}))

        response = await read_frame(self._reader)
        if not response or response.command != "CONNECTED":
            raise ConnectionError(f"Connection failed: {response}")

        self._connected = True
        self._listener_task = asyncio.create_task(self._listen())
        log.info("Connected to broker at %s:%d", self._host, self._port)

    async def close(self):
        if not self._connected:
            return
        self._connected = False
        try:
            await self._send(StompFrame("DISCONNECT", {}))
        except Exception:
            pass
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass

    async def publish(self, destination: str, body: str | bytes, headers: dict[str, str] | None = None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        h = {"destination": destination}
        if headers:
            h.update(headers)
        await self._send(StompFrame("SEND", h, body))

    async def subscribe(
        self,
        destination: str,
        callback: MessageHandler,
        ack_mode: str = "auto",
        headers: dict[str, str] | None = None,
    ) -> str:
        self._sub_counter += 1
        sub_id = f"sub-{self._sub_counter}"
        h = {"destination": destination, "id": sub_id, "ack": ack_mode}
        if headers:
            h.update(headers)
        self._handlers[sub_id] = callback
        await self._send(StompFrame("SUBSCRIBE", h))
        return sub_id

    async def unsubscribe(self, sub_id: str):
        self._handlers.pop(sub_id, None)
        await self._send(StompFrame("UNSUBSCRIBE", {"id": sub_id}))

    async def ack(self, message_id: str):
        await self._send(StompFrame("ACK", {"id": message_id}))

    async def nack(self, message_id: str):
        await self._send(StompFrame("NACK", {"id": message_id}))

    @property
    def connected(self) -> bool:
        return self._connected

    async def _send(self, frame: StompFrame):
        if self._writer is None:
            raise ConnectionError("Not connected")
        self._writer.write(build_frame(frame))
        await self._writer.drain()

    async def _listen(self):
        try:
            while self._connected and self._reader:
                frame = await read_frame(self._reader)
                if frame is None:
                    break
                if frame.command == "MESSAGE":
                    sub_id = frame.headers.get("subscription")
                    handler = self._handlers.get(sub_id) if sub_id else None
                    if handler:
                        try:
                            await handler(frame)
                        except Exception:
                            log.exception("Error in message handler for %s", sub_id)
                elif frame.command == "ERROR":
                    log.error("Server error: %s", frame.headers.get("message", "unknown"))
                elif frame.command == "RECEIPT":
                    pass
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Connection lost")
        finally:
            self._connected = False

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.close()
