from dataclasses import dataclass, field
import time
import uuid


@dataclass
class StompFrame:
    command: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""


@dataclass
class Message:
    id: str
    destination: str
    body: bytes
    headers: dict[str, str]
    timestamp: float

    @classmethod
    def create(cls, destination: str, body: bytes, headers: dict[str, str] | None = None) -> "Message":
        return cls(
            id=str(uuid.uuid4()),
            destination=destination,
            body=body,
            headers=headers or {},
            timestamp=time.time(),
        )
