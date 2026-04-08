import asyncio

from pybroker.common.models import StompFrame

MAX_FRAME_SIZE = 1024 * 1024

_ESCAPE = {"\\n": "\n", "\\c": ":", "\\\\": "\\"}


def _unescape(value: str) -> str:
    result: list[str] = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            pair = value[i : i + 2]
            if pair in _ESCAPE:
                result.append(_ESCAPE[pair])
                i += 2
                continue
        result.append(value[i])
        i += 1
    return "".join(result)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(":", "\\c")


async def read_frame(reader: asyncio.StreamReader) -> StompFrame | None:
    while True:
        try:
            line = await reader.readline()
        except (asyncio.IncompleteReadError, ConnectionResetError, ConnectionError):
            return None
        if not line:
            return None
        command = line.decode("utf-8").strip()
        if command:
            break

    headers: dict[str, str] = {}
    total = len(command)
    while True:
        try:
            line = await reader.readline()
        except (asyncio.IncompleteReadError, ConnectionResetError, ConnectionError):
            return None
        if not line:
            return None
        raw = line.decode("utf-8").rstrip("\r\n")
        total += len(raw) + 1
        if total > MAX_FRAME_SIZE:
            raise ValueError("Frame exceeds maximum size")
        if not raw:
            break
        key, _, value = raw.partition(":")
        headers[_unescape(key)] = _unescape(value)

    if "content-length" in headers:
        length = int(headers["content-length"])
        if length > MAX_FRAME_SIZE:
            raise ValueError("Frame exceeds maximum size")
        try:
            body = await reader.readexactly(length)
            await reader.readexactly(1)
        except (asyncio.IncompleteReadError, ConnectionResetError, ConnectionError):
            return None
    else:
        try:
            data = await reader.readuntil(b"\0")
        except (asyncio.IncompleteReadError, ConnectionResetError, ConnectionError):
            return None
        body = data[:-1]

    return StompFrame(command=command, headers=headers, body=body)


def build_frame(frame: StompFrame) -> bytes:
    lines = [frame.command]
    headers = dict(frame.headers)
    if frame.body:
        headers["content-length"] = str(len(frame.body))
    for key, value in headers.items():
        lines.append(f"{_escape(key)}:{_escape(value)}")
    lines.append("")
    header_part = ("\n".join(lines) + "\n").encode("utf-8")
    return header_part + frame.body + b"\0"
