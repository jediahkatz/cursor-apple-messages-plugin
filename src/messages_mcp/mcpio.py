from __future__ import annotations

import json
import sys
from typing import Any, BinaryIO


def read_message(stream: BinaryIO | None = None) -> dict[str, Any] | None:
    source = stream or sys.stdin.buffer
    while True:
        line = source.readline()
        if not line:
            return None
        if not line.strip():
            continue
        message = json.loads(line)
        if not isinstance(message, dict):
            raise ValueError("MCP message must be a JSON object")
        return message


def write_message(payload: dict[str, Any], stream: BinaryIO | None = None) -> None:
    destination = stream or sys.stdout.buffer
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    destination.write(data + b"\n")
    destination.flush()
