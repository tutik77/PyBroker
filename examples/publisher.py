import asyncio
import json
import logging
import os

from pybroker.client.client import BrokerClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("publisher")


async def main():
    host = os.environ.get("BROKER_HOST", "localhost")
    port = int(os.environ.get("BROKER_PORT", "9090"))

    await asyncio.sleep(2)

    async with BrokerClient(host, port) as client:
        log.info("Connected to broker")

        for i in range(1, 11):
            await client.publish("/topic/events", f"Event #{i}")
            log.info("Published to /topic/events: Event #%d", i)

            task = json.dumps({"task_id": i, "action": "process"})
            await client.publish("/queue/tasks", task)
            log.info("Published to /queue/tasks: task #%d", i)

            await asyncio.sleep(2)

    log.info("Publisher finished")


if __name__ == "__main__":
    asyncio.run(main())
