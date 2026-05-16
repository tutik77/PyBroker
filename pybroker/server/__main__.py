import asyncio
import logging
import os

from pybroker.server.server import BrokerServer


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    host = os.environ.get("BROKER_HOST", "0.0.0.0")
    port = int(os.environ.get("BROKER_PORT", "9090"))
    db_path = os.environ.get("BROKER_DB", "data/broker.db")
    web_port = int(os.environ.get("BROKER_WEB_PORT", "8080"))

    server = BrokerServer(host=host, port=port, db_path=db_path, web_port=web_port)
    asyncio.run(server.start())


if __name__ == "__main__":
    main()
