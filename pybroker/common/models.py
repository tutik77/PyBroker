from dataclasses import dataclass, field
import time
import uuid


DEFAULT_PRIORITY = 0


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
    expires_at: float | None = None

    @classmethod
    def create(
        cls,
        destination: str,
        body: bytes,
        headers: dict[str, str] | None = None,
    ) -> "Message":
        h = dict(headers or {})
        now = time.time()
        return cls(
            id=str(uuid.uuid4()),
            destination=destination,
            body=body,
            headers=h,
            timestamp=now,
            expires_at=_compute_expiry(h, now),
        )

    @property
    def priority(self) -> int:
        return _safe_int(self.headers.get("priority"), DEFAULT_PRIORITY)

    def is_expired(self, now: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now if now is not None else time.time()) >= self.expires_at


def _compute_expiry(headers: dict[str, str], now: float) -> float | None:
    ttl = headers.get("x-ttl")
    if ttl is None:
        return None
    try:
        ttl_seconds = float(ttl)
    except ValueError:
        return None
    if ttl_seconds <= 0:
        return None
    return now + ttl_seconds


def _safe_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default
