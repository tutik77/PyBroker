from __future__ import annotations

import heapq
import itertools
import time
from typing import TYPE_CHECKING

from pybroker.common.models import Message

if TYPE_CHECKING:
    from pybroker.server.connection import Connection


DEFAULT_VISIBILITY_TIMEOUT = 30.0
DEFAULT_MAX_DELIVERIES = 5
DLQ_SUFFIX = ".DLQ"


class MessageQueue:
    def __init__(
        self,
        name: str,
        queue_type: str = "FIFO",
        visibility_timeout: float = DEFAULT_VISIBILITY_TIMEOUT,
        max_deliveries: int = DEFAULT_MAX_DELIVERIES,
    ):
        self.name = name
        self.queue_type = queue_type
        self.visibility_timeout = visibility_timeout
        self.max_deliveries = max_deliveries
        self.in_flight: dict[str, tuple[Message, float, int]] = {}
        self.consumers: list[tuple[Connection, str]] = []
        self._heap: list[tuple[int, int, str, Message]] = []
        self._seq = itertools.count()
        self._consumer_index = 0

    @property
    def ready_count(self) -> int:
        return len(self._heap)

    def add_message(self, message: Message) -> None:
        seq = next(self._seq)
        order = -seq if self.queue_type == "LIFO" else seq
        heapq.heappush(self._heap, (-message.priority, order, message.id, message))

    def pop_message(self) -> Message | None:
        if not self._heap:
            return None
        _, _, _, message = heapq.heappop(self._heap)
        return message

    def add_consumer(self, connection: Connection, sub_id: str) -> None:
        self.consumers.append((connection, sub_id))

    def remove_consumer(self, connection: Connection, sub_id: str | None = None) -> None:
        if sub_id is not None:
            self.consumers = [
                (c, s) for c, s in self.consumers
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

    def mark_in_flight(self, message: Message) -> int:
        prev = self.in_flight.get(message.id)
        attempt = (prev[2] if prev else 0) + 1
        self.in_flight[message.id] = (message, time.time(), attempt)
        return attempt

    def ack(self, message_id: str) -> bool:
        return self.in_flight.pop(message_id, None) is not None

    def take_in_flight(self, message_id: str) -> tuple[Message, int] | None:
        entry = self.in_flight.pop(message_id, None)
        if entry is None:
            return None
        message, _locked_at, attempt = entry
        return message, attempt

    def check_timeouts(self) -> list[tuple[Message, int]]:
        now = time.time()
        expired: list[tuple[Message, int]] = []
        for msg_id, (msg, locked_at, attempt) in list(self.in_flight.items()):
            if now - locked_at >= self.visibility_timeout:
                del self.in_flight[msg_id]
                expired.append((msg, attempt))
        return expired

    def purge_expired(self, now: float | None = None) -> list[Message]:
        moment = now if now is not None else time.time()
        expired: list[Message] = []
        kept: list[tuple[int, int, str, Message]] = []
        for entry in self._heap:
            message = entry[3]
            if message.is_expired(moment):
                expired.append(message)
            else:
                kept.append(entry)
        if expired:
            self._heap = kept
            heapq.heapify(self._heap)
        for msg_id, (message, _locked, _attempt) in list(self.in_flight.items()):
            if message.is_expired(moment):
                del self.in_flight[msg_id]
                expired.append(message)
        return expired


class QueueManager:
    def __init__(self):
        self._queues: dict[str, MessageQueue] = {}

    def get_or_create(
        self,
        name: str,
        queue_type: str = "FIFO",
        max_deliveries: int = DEFAULT_MAX_DELIVERIES,
    ) -> MessageQueue:
        queue = self._queues.get(name)
        if queue is None:
            queue = MessageQueue(name, queue_type, max_deliveries=max_deliveries)
            self._queues[name] = queue
        return queue

    def get(self, name: str) -> MessageQueue | None:
        return self._queues.get(name)

    def remove_connection(self, connection: Connection) -> None:
        for queue in self._queues.values():
            queue.remove_consumer(connection)

    def all_queues(self) -> list[MessageQueue]:
        return list(self._queues.values())
