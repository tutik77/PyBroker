from __future__ import annotations

import time
from collections import deque
from typing import TYPE_CHECKING

from pybroker.common.models import Message

if TYPE_CHECKING:
    from pybroker.server.connection import Connection


class MessageQueue:
    def __init__(self, name: str, queue_type: str = "FIFO", visibility_timeout: float = 30.0):
        self.name = name
        self.queue_type = queue_type
        self.messages: deque[Message] = deque()
        self.in_flight: dict[str, tuple[Message, float, int]] = {}
        self.consumers: list[tuple[Connection, str]] = []
        self.visibility_timeout = visibility_timeout
        self._consumer_index = 0

    def add_message(self, message: Message):
        self.messages.append(message)

    def pop_message(self) -> Message | None:
        if not self.messages:
            return None
        return self.messages.pop() if self.queue_type == "LIFO" else self.messages.popleft()

    def add_consumer(self, connection: Connection, sub_id: str):
        self.consumers.append((connection, sub_id))

    def remove_consumer(self, connection: Connection, sub_id: str | None = None):
        if sub_id is not None:
            self.consumers = [
                (c, s)
                for c, s in self.consumers
                if not (c is connection and s == sub_id)
            ]
        else:
            self.consumers = [(c, s) for c, s in self.consumers if c is not connection]

    def next_consumer(self) -> tuple[Connection, str] | None:
        if not self.consumers:
            return None
        idx = self._consumer_index % len(self.consumers)
        self._consumer_index = idx + 1
        return self.consumers[idx]

    def mark_in_flight(self, message: Message):
        prev = self.in_flight.get(message.id)
        count = prev[2] + 1 if prev else 1
        self.in_flight[message.id] = (message, time.time(), count)

    def ack(self, message_id: str) -> bool:
        return self.in_flight.pop(message_id, None) is not None

    def nack(self, message_id: str):
        entry = self.in_flight.pop(message_id, None)
        if entry:
            self.messages.appendleft(entry[0])

    def check_timeouts(self) -> list[Message]:
        now = time.time()
        expired: list[Message] = []
        for msg_id, (msg, locked_at, _count) in list(self.in_flight.items()):
            if now - locked_at >= self.visibility_timeout:
                del self.in_flight[msg_id]
                self.messages.appendleft(msg)
                expired.append(msg)
        return expired


class QueueManager:
    def __init__(self):
        self._queues: dict[str, MessageQueue] = {}

    def get_or_create(self, name: str, queue_type: str = "FIFO") -> MessageQueue:
        if name not in self._queues:
            self._queues[name] = MessageQueue(name, queue_type)
        return self._queues[name]

    def get(self, name: str) -> MessageQueue | None:
        return self._queues.get(name)

    def remove_connection(self, connection: Connection):
        for queue in self._queues.values():
            queue.remove_consumer(connection)

    def all_queues(self) -> list[MessageQueue]:
        return list(self._queues.values())
