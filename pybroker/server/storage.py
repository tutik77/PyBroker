import json
import os
import time

import aiosqlite

from pybroker.common.models import Message
from pybroker.server.queue import DEFAULT_MAX_DELIVERIES


class Storage:
    def __init__(self, db_path: str = "data/broker.db"):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self):
        directory = os.path.dirname(self._db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode = WAL")
        await self._db.execute("PRAGMA synchronous = NORMAL")
        await self._db.execute("PRAGMA cache_size = -64000")
        await self._db.execute("PRAGMA temp_store = MEMORY")
        await self._setup_tables()
        await self._migrate()

    async def _setup_tables(self):
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS queues (
                name                TEXT PRIMARY KEY,
                queue_type          TEXT NOT NULL DEFAULT 'FIFO',
                visibility_timeout  REAL NOT NULL DEFAULT 30.0,
                max_deliveries      INTEGER NOT NULL DEFAULT 5,
                created_at          REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id              TEXT PRIMARY KEY,
                queue_name      TEXT NOT NULL,
                body            BLOB NOT NULL,
                headers         TEXT NOT NULL DEFAULT '{}',
                status          TEXT NOT NULL DEFAULT 'READY',
                created_at      REAL NOT NULL,
                expires_at      REAL,
                locked_at       REAL,
                delivery_count  INTEGER NOT NULL DEFAULT 0,
                CONSTRAINT valid_status CHECK (status IN ('READY', 'IN_FLIGHT'))
            );

            CREATE INDEX IF NOT EXISTS idx_messages_queue_status
                ON messages(queue_name, status, created_at);

            CREATE INDEX IF NOT EXISTS idx_messages_locked_at
                ON messages(locked_at) WHERE status = 'IN_FLIGHT';

            CREATE INDEX IF NOT EXISTS idx_messages_expires_at
                ON messages(expires_at) WHERE expires_at IS NOT NULL;
            """
        )
        await self._db.commit()

    async def _migrate(self):
        message_cols = await self._table_columns("messages")
        if "expires_at" not in message_cols:
            await self._db.execute("ALTER TABLE messages ADD COLUMN expires_at REAL")
        queue_cols = await self._table_columns("queues")
        if "max_deliveries" not in queue_cols:
            await self._db.execute(
                f"ALTER TABLE queues ADD COLUMN max_deliveries INTEGER NOT NULL DEFAULT {DEFAULT_MAX_DELIVERIES}"
            )
        await self._db.commit()

    async def _table_columns(self, table: str) -> set[str]:
        cursor = await self._db.execute(f"PRAGMA table_info({table})")
        rows = await cursor.fetchall()
        return {row[1] for row in rows}

    async def save_queue(
        self,
        name: str,
        queue_type: str,
        visibility_timeout: float,
        max_deliveries: int,
    ):
        await self._db.execute(
            "INSERT OR IGNORE INTO queues "
            "(name, queue_type, visibility_timeout, max_deliveries, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, queue_type, visibility_timeout, max_deliveries, time.time()),
        )
        await self._db.commit()

    async def save_message(self, message: Message, queue_name: str):
        await self._db.execute(
            "INSERT INTO messages "
            "(id, queue_name, body, headers, status, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, 'READY', ?, ?)",
            (
                message.id,
                queue_name,
                message.body,
                json.dumps(message.headers),
                message.timestamp,
                message.expires_at,
            ),
        )
        await self._db.commit()

    async def update_status(self, message_id: str, status: str):
        if status == "IN_FLIGHT":
            await self._db.execute(
                "UPDATE messages SET status = ?, locked_at = ?, "
                "delivery_count = delivery_count + 1 WHERE id = ?",
                (status, time.time(), message_id),
            )
        else:
            await self._db.execute(
                "UPDATE messages SET status = ?, locked_at = NULL WHERE id = ?",
                (status, message_id),
            )
        await self._db.commit()

    async def delete_message(self, message_id: str):
        await self._db.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        await self._db.commit()

    async def load_queues(self) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT name, queue_type, visibility_timeout, max_deliveries FROM queues"
        )
        rows = await cursor.fetchall()
        return [
            {
                "name": row[0],
                "queue_type": row[1],
                "visibility_timeout": row[2],
                "max_deliveries": row[3],
            }
            for row in rows
        ]

    async def load_messages(self, queue_name: str) -> list[Message]:
        cursor = await self._db.execute(
            "SELECT id, queue_name, body, headers, created_at, expires_at FROM messages "
            "WHERE queue_name = ? AND status IN ('READY', 'IN_FLIGHT') "
            "ORDER BY created_at ASC",
            (queue_name,),
        )
        rows = await cursor.fetchall()
        return [
            Message(
                id=row[0],
                destination=f"/queue/{row[1]}",
                body=row[2],
                headers=json.loads(row[3]),
                timestamp=row[4],
                expires_at=row[5],
            )
            for row in rows
        ]

    async def reset_in_flight(self):
        await self._db.execute(
            "UPDATE messages SET status = 'READY', locked_at = NULL "
            "WHERE status = 'IN_FLIGHT'"
        )
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()
