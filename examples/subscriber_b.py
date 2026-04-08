import asyncio
import logging
import os

from pybroker.client.client import BrokerClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("subscriber_b")


async def main():
    host = os.environ.get("BROKER_HOST", "localhost")
    port = int(os.environ.get("BROKER_PORT", "9090"))

    await asyncio.sleep(1)

    async with BrokerClient(host, port) as client:
        log.info("Connected to broker")

        async def on_event(frame):
            log.info("Received event: %s", frame.body.decode())

        async def on_task(frame):
            msg_id = frame.headers.get("message-id")
            log.info("Received task: %s", frame.body.decode())
            await client.ack(msg_id)
            log.info("ACK sent for message %s", msg_id)

        await client.subscribe("/topic/events", on_event)
        log.info("Subscribed to /topic/events")

        await client.subscribe("/queue/tasks", on_task, ack_mode="client")
        log.info("Subscribed to /queue/tasks")

        while client.connected:
            await asyncio.sleep(1)

    log.info("Subscriber B stopped")


if __name__ == "__main__":
    asyncio.run(main())
