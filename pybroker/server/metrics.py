from dataclasses import asdict, dataclass


@dataclass
class Metrics:
    published: int = 0
    delivered: int = 0
    acked: int = 0
    nacked: int = 0
    timeouts: int = 0

    def snapshot(self) -> dict[str, int]:
        return asdict(self)

    def format(self) -> str:
        return " ".join(f"{key}={value}" for key, value in self.snapshot().items())
