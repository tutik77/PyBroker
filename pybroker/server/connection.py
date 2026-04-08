import asyncio
import uuid
from dataclasses import dataclass

from pybroker.common.models import StompFrame
from pybroker.server.protocol import build_frame


@dataclass
class Subscription:
    id: str
    destination: str
    ack_mode: str = "auto"


class Connection:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.id = str(uuid.uuid4())
        self.reader = reader
        self.writer = writer
        self.connected = False
        self.subscriptions: dict[str, Subscription] = {}

    async def send_frame(self, frame: StompFrame):
        data = build_frame(frame)
        self.writer.write(data)
        await self.writer.drain()

    def close(self):
        self.writer.close()

    @property
    def peer(self) -> str:
        try:
            addr = self.writer.get_extra_info("peername")
            return f"{addr[0]}:{addr[1]}" if addr else "unknown"
        except Exception:
            return "unknown"

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, Connection) and self.id == other.id
