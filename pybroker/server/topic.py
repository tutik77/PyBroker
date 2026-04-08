from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pybroker.server.connection import Connection


class TopicManager:
    def __init__(self):
        self._exact: dict[str, set[tuple[Connection, str]]] = {}
        self._wildcard: list[tuple[str, Connection, str]] = []

    def subscribe(self, destination: str, connection: Connection, sub_id: str):
        if "*" in destination:
            self._wildcard.append((destination, connection, sub_id))
        else:
            self._exact.setdefault(destination, set()).add((connection, sub_id))

    def unsubscribe(self, connection: Connection, sub_id: str):
        for subs in self._exact.values():
            subs.discard((connection, sub_id))
        self._wildcard = [
            (p, c, s)
            for p, c, s in self._wildcard
            if not (c is connection and s == sub_id)
        ]

    def remove_connection(self, connection: Connection):
        for subs in list(self._exact.values()):
            to_remove = {(c, s) for c, s in subs if c is connection}
            subs -= to_remove
        self._wildcard = [
            (p, c, s) for p, c, s in self._wildcard if c is not connection
        ]

    def get_subscribers(self, destination: str) -> list[tuple[Connection, str]]:
        result = list(self._exact.get(destination, set()))
        for pattern, conn, sub_id in self._wildcard:
            if _match(pattern, destination):
                result.append((conn, sub_id))
        return result


def _match(pattern: str, destination: str) -> bool:
    p_parts = pattern.split(".")
    d_parts = destination.split(".")
    if len(p_parts) != len(d_parts):
        return False
    return all(p == "*" or p == d for p, d in zip(p_parts, d_parts))
