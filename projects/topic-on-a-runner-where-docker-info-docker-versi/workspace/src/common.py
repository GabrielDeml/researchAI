"""Shared, standard-library-only helpers for container processes."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any


RUN = Path("/runexp")
CONTROL = RUN / "control"
EVENTS = RUN / "events.jsonl"


def monotonic_ns() -> int:
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{monotonic_ns()}.tmp")
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def event(kind: str, **fields: Any) -> None:
    record = {"event": kind, "monotonic_ns": monotonic_ns(), **fields}
    encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    fd = os.open(EVENTS, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, encoded)
        os.fsync(fd)
    finally:
        os.close(fd)
