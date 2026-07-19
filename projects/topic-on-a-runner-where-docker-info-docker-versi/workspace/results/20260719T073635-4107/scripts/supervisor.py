#!/usr/bin/env python3
"""Container PID 1 for the completion-monitor experiment."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time


STATE = Path("/state")


def monotonic_ns() -> int:
    return time.monotonic_ns()


def atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{monotonic_ns()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def append_event(event: str, **fields: object) -> None:
    record = {"event": event, "monotonic_ns": monotonic_ns(), **fields}
    line = json.dumps(record, sort_keys=True, separators=(",", ":"))
    print(line, flush=True)


def decode_wait_status(status: int) -> int:
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return 255


def main() -> int:
    STATE.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "/experiment/fixture.py", *sys.argv[1:]]
    parent = subprocess.Popen(command, close_fds=True)
    atomic_write(STATE / "parent.pid", f"{parent.pid}\n")
    append_event("parent_started", pid=parent.pid)

    parent_exit_code: int | None = None
    while not (STATE / "stop").exists():
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if pid == 0:
                break
            exit_code = decode_wait_status(status)
            append_event("reaped", pid=pid, exit_code=exit_code)
            if pid == parent.pid:
                parent_exit_code = exit_code
                atomic_write(STATE / "parent-exit-code", f"{exit_code}\n")
        time.sleep(0.010)

    # The aware monitor only permits stop after all tracked descendants are gone,
    # but perform a final nonblocking reap to avoid leaving zombies in the log.
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        if pid == 0:
            break
        exit_code = decode_wait_status(status)
        append_event("reaped_at_stop", pid=pid, exit_code=exit_code)
        if pid == parent.pid:
            parent_exit_code = exit_code
            atomic_write(STATE / "parent-exit-code", f"{exit_code}\n")

    if parent_exit_code is None and (STATE / "parent-exit-code").exists():
        parent_exit_code = int((STATE / "parent-exit-code").read_text().strip())
    append_event("supervisor_stopping", parent_exit_code=parent_exit_code)
    return 0 if parent_exit_code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
