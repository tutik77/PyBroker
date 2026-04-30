import logging
import uuid

from pybroker.common.models import Message, StompFrame
from pybroker.server.connection import Connection, Subscription
from pybroker.server.metrics import Metrics
from pybroker.server.queue import (
    DEFAULT_MAX_DELIVERIES,
    DLQ_SUFFIX,
    MessageQueue,
    QueueManager,
)
from pybroker.server.storage import Storage
from pybroker.server.topic import TopicManager

log = logging.getLogger(__name__)


class Broker:
    def __init__(self, storage: Storage, metrics: Metrics):
        self._topics = TopicManager()
        self._queues = QueueManager()
        self._storage = storage
        self._metrics = metrics
        self._connections: dict[str, Connection] = {}

    @property
    def metrics(self) -> Metrics:
        return self._metrics

    async def restore(self):
        await self._storage.reset_in_flight()
        for q in await self._storage.load_queues():
            queue = self._queues.get_or_create(
                q["name"], q["queue_type"], q["max_deliveries"]
            )
            queue.visibility_timeout = q["visibility_timeout"]
            messages = await self._storage.load_messages(q["name"])
            restored = 0
            for msg in messages:
                if msg.is_expired():
                    await self._storage.delete_message(msg.id)
                    continue
                queue.add_message(msg)
                restored += 1
            if restored:
                log.info("Restored %d messages for queue '%s'", restored, q["name"])

    def register(self, connection: Connection):
        self._connections[connection.id] = connection

    async def unregister(self, connection: Connection):
        self._topics.remove_connection(connection)
        self._queues.remove_connection(connection)
        self._connections.pop(connection.id, None)
        log.info("Client disconnected: %s", connection.peer)

    async def handle_frame(self, connection: Connection, frame: StompFrame):
        handlers = {
            "CONNECT": self._on_connect,
            "STOMP": self._on_connect,
            "SEND": self._on_send,
            "SUBSCRIBE": self._on_subscribe,
            "UNSUBSCRIBE": self._on_unsubscribe,
            "ACK": self._on_ack,
            "NACK": self._on_nack,
            "DISCONNECT": self._on_disconnect,
        }

        handler = handlers.get(frame.command)
        if not handler:
            await self._send_error(connection, f"Unknown command: {frame.command}")
            return

        try:
            await handler(connection, frame)
            receipt = frame.headers.get("receipt")
            if receipt and frame.command not in ("CONNECT", "STOMP", "DISCONNECT"):
                await connection.send_frame(StompFrame("RECEIPT", {"receipt-id": receipt}))
        except Exception as exc:
            log.exception("Error handling %s from %s", frame.command, connection.peer)
            await self._send_error(connection, str(exc))

    async def check_timeouts(self):
        for queue in self._queues.all_queues():
            expired = queue.check_timeouts()
            for message, attempt in expired:
                self._metrics.timeouts += 1
                log.info(
                    "Message %s timed out in queue '%s' (attempt %d)",
                    message.id, queue.name, attempt,
                )
                await self._handle_failed_delivery(queue, message, attempt, reason="timeout")
            if expired:
                await self._deliver_from_queue(queue.name)

    async def purge_expired(self):
        for queue in self._queues.all_queues():
            for message in queue.purge_expired():
                await self._storage.delete_message(message.id)
                log.info("Message %s expired in queue '%s'", message.id, queue.name)

    async def _on_connect(self, connection: Connection, frame: StompFrame):
        connection.connected = True
        await connection.send_frame(
            StompFrame("CONNECTED", {"version": "1.2", "server": "PyBroker/1.0"})
        )
        log.info("Client connected: %s", connection.peer)

    async def _on_send(self, connection: Connection, frame: StompFrame):
        destination = frame.headers.get("destination")
        if not destination:
            await self._send_error(connection, "Missing 'destination' header")
            return

        if destination.startswith("/topic/"):
            await self._publish_to_topic(destination, frame)
        elif destination.startswith("/queue/"):
            await self._publish_to_queue(destination, frame)
        else:
            await self._send_error(connection, f"Invalid destination: {destination}")

    async def _on_subscribe(self, connection: Connection, frame: StompFrame):
        destination = frame.headers.get("destination")
        sub_id = frame.headers.get("id")
        if not destination or not sub_id:
            await self._send_error(connection, "Missing 'destination' or 'id' header")
            return

        ack_mode = frame.headers.get("ack", "auto")
        connection.subscriptions[sub_id] = Subscription(sub_id, destination, ack_mode)

        if destination.startswith("/topic/"):
            self._topics.subscribe(destination, connection, sub_id)
            log.info("Subscribed %s to topic %s", connection.peer, destination)
        elif destination.startswith("/queue/"):
            queue_name = destination[7:]
            queue_type = frame.headers.get("x-queue-type", "FIFO").upper()
            queue = self._queues.get_or_create(queue_name, queue_type)
            queue.add_consumer(connection, sub_id)
            await self._storage.save_queue(
                queue_name, queue.queue_type, queue.visibility_timeout, queue.max_deliveries
            )
            log.info("Consumer %s subscribed to queue '%s'", connection.peer, queue_name)
            await self._deliver_from_queue(queue_name)

    async def _on_unsubscribe(self, connection: Connection, frame: StompFrame):
        sub_id = frame.headers.get("id")
        if not sub_id:
            await self._send_error(connection, "Missing 'id' header")
            return

        sub = connection.subscriptions.pop(sub_id, None)
        if not sub:
            return

        if sub.destination.startswith("/topic/"):
            self._topics.unsubscribe(connection, sub_id)
        elif sub.destination.startswith("/queue/"):
            queue = self._queues.get(sub.destination[7:])
            if queue:
                queue.remove_consumer(connection, sub_id)

    async def _on_ack(self, connection: Connection, frame: StompFrame):
        message_id = frame.headers.get("id")
        if not message_id:
            await self._send_error(connection, "Missing 'id' header")
            return

        for queue in self._queues.all_queues():
            if queue.ack(message_id):
                await self._storage.delete_message(message_id)
                self._metrics.acked += 1
                log.debug("ACK message %s from queue '%s'", message_id, queue.name)
                await self._deliver_from_queue(queue.name)
                return

    async def _on_nack(self, connection: Connection, frame: StompFrame):
        message_id = frame.headers.get("id")
        if not message_id:
            await self._send_error(connection, "Missing 'id' header")
            return

        for queue in self._queues.all_queues():
            taken = queue.take_in_flight(message_id)
            if taken is None:
                continue
            message, attempt = taken
            self._metrics.nacked += 1
            log.info(
                "NACK message %s in queue '%s' (attempt %d)",
                message_id, queue.name, attempt,
            )
            await self._handle_failed_delivery(queue, message, attempt, reason="nack")
            await self._deliver_from_queue(queue.name)
            return

    async def _on_disconnect(self, connection: Connection, frame: StompFrame):
        receipt = frame.headers.get("receipt")
        if receipt:
            await connection.send_frame(StompFrame("RECEIPT", {"receipt-id": receipt}))
        connection.close()

    async def _publish_to_topic(self, destination: str, frame: StompFrame):
        self._metrics.published += 1
        subscribers = self._topics.get_subscribers(destination)
        if not subscribers:
            return

        message_id = str(uuid.uuid4())
        extra = {
            k: v for k, v in frame.headers.items() if k not in ("destination", "receipt")
        }

        for conn, sub_id in subscribers:
            msg_frame = StompFrame(
                "MESSAGE",
                {
                    "destination": destination,
                    "message-id": message_id,
                    "subscription": sub_id,
                    **extra,
                },
                frame.body,
            )
            try:
                await conn.send_frame(msg_frame)
                self._metrics.delivered += 1
            except Exception:
                log.warning("Failed to deliver to subscriber %s", conn.peer)

    async def _publish_to_queue(self, destination: str, frame: StompFrame):
        queue_name = destination[7:]
        queue_type = frame.headers.get("x-queue-type", "FIFO").upper()
        queue = self._queues.get_or_create(queue_name, queue_type)

        extra = {
            k: v
            for k, v in frame.headers.items()
            if k not in ("destination", "receipt", "x-queue-type", "content-length")
        }

        message = Message.create(destination, frame.body, extra)
        if message.is_expired():
            log.info("Message %s expired before enqueue in '%s'", message.id, queue_name)
            return

        queue.add_message(message)
        await self._storage.save_queue(
            queue_name, queue.queue_type, queue.visibility_timeout, queue.max_deliveries
        )
        await self._storage.save_message(message, queue_name)
        self._metrics.published += 1
        log.debug("Message %s added to queue '%s'", message.id, queue_name)
        await self._deliver_from_queue(queue_name)

    async def _deliver_from_queue(self, queue_name: str):
        queue = self._queues.get(queue_name)
        if not queue:
            return

        while queue.ready_count > 0 and queue.consumers:
            consumer = queue.next_consumer()
            if not consumer:
                break
            conn, sub_id = consumer

            msg = queue.pop_message()
            if msg is None:
                break
            if msg.is_expired():
                await self._storage.delete_message(msg.id)
                log.info("Message %s expired before dispatch in '%s'", msg.id, queue.name)
                continue

            attempt = queue.mark_in_flight(msg)

            try:
                msg_frame = StompFrame(
                    "MESSAGE",
                    {
                        "destination": msg.destination,
                        "message-id": msg.id,
                        "subscription": sub_id,
                        **msg.headers,
                    },
                    msg.body,
                )
                await conn.send_frame(msg_frame)
                await self._storage.update_status(msg.id, "IN_FLIGHT")
                self._metrics.delivered += 1
            except Exception:
                queue.in_flight.pop(msg.id, None)
                queue.remove_consumer(conn, sub_id)
                log.warning("Failed to deliver to consumer %s, removed", conn.peer)
                await self._handle_failed_delivery(queue, msg, attempt, reason="connection_error")

    async def _handle_failed_delivery(
        self, queue: MessageQueue, message: Message, attempt: int, reason: str
    ):
        if attempt >= queue.max_deliveries:
            await self._move_to_dlq(queue, message, attempt, reason)
        else:
            queue.add_message(message)
            await self._storage.update_status(message.id, "READY")

    async def _move_to_dlq(
        self, queue: MessageQueue, message: Message, attempt: int, reason: str
    ):
        dlq_name = queue.name + DLQ_SUFFIX
        dlq = self._queues.get_or_create(dlq_name, "FIFO", DEFAULT_MAX_DELIVERIES)
        dlq_headers = {k: v for k, v in message.headers.items() if k != "x-ttl"}
        dlq_headers.update({
            "x-original-queue": queue.name,
            "x-original-id": message.id,
            "x-dlq-reason": reason,
            "x-delivery-count": str(attempt),
        })
        dlq_message = Message.create(f"/queue/{dlq_name}", message.body, dlq_headers)
        dlq.add_message(dlq_message)
        await self._storage.save_queue(
            dlq_name, dlq.queue_type, dlq.visibility_timeout, dlq.max_deliveries
        )
        await self._storage.delete_message(message.id)
        await self._storage.save_message(dlq_message, dlq_name)
        log.warning(
            "Message %s moved to DLQ '%s' (reason=%s, attempts=%d)",
            message.id, dlq_name, reason, attempt,
        )
        await self._deliver_from_queue(dlq_name)

    async def _send_error(self, connection: Connection, message: str):
        try:
            await connection.send_frame(
                StompFrame("ERROR", {"message": message}, message.encode("utf-8"))
            )
        except Exception:
            pass
