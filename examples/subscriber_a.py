import asyncio
import logging
import os

from pybroker.client.client import BrokerClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("subscriber_a")


async def main():
    host = os.environ.get("BROKER_HOST", "localhost")
    port = int(os.environ.get("BROKER_PORT", "9090"))

    await asyncio.sleep(1)

    async with BrokerClient(host, port) as client:
        log.info("Connected to broker")

        async def on_event(frame):
            log.info("Received event: %s", frame.body.decode())

        await client.subscribe("/topic/events", on_event)
        log.info("Subscribed to /topic/events")

        while client.connected:
            await asyncio.sleep(1)

    log.info("Subscriber A stopped")


if __name__ == "__main__":
    asyncio.run(main())
