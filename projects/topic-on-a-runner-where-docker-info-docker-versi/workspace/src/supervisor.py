"""PID-1 supervisor: start monitor, launch one parent, reap, await shutdown."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from common import CONTROL, RUN, atomic_json, event, monotonic_ns


def exit_code_from_wait(status: int) -> int:
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return 255


def main() -> int:
    CONTROL.mkdir(parents=True, exist_ok=True)
    (CONTROL / "snapshots").mkdir(parents=True, exist_ok=True)
    (RUN / "snapshots").mkdir(parents=True, exist_ok=True)
    config = json.loads((RUN / "config.json").read_text(encoding="utf-8"))
    signal.signal(signal.SIGTERM, lambda *_: (CONTROL / "shutdown").touch())
    event("container_start", pid=os.getpid())

    monitor = subprocess.Popen([sys.executable, "/app/monitor.py"], close_fds=True)
    parent_pid: int | None = None
    monitor_status: int | None = None
    parent_status: int | None = None

    while True:
        if parent_pid is None and (CONTROL / "start").exists():
            command = [
                sys.executable,
                "/app/workload.py",
                "parent",
                "--kind",
                config["kind"],
                "--mode",
                config["mode"],
                "--seed",
                str(config["seed"]),
                "--parameter",
                str(config["parameter"]),
            ]
            parent_pid = os.fork()
            if parent_pid == 0:
                os.execv(sys.executable, command)
            atomic_json(
                RUN / "parent_pid.json",
                {"pid": parent_pid, "monotonic_ns": monotonic_ns()},
            )
            event("parent_spawn", pid=parent_pid)

        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if pid == 0:
                break
            code = exit_code_from_wait(status)
            if pid == parent_pid and parent_status is None:
                parent_status = code
                record = {"pid": pid, "exit_code": code, "wait_status": status,
                          "monotonic_ns": monotonic_ns()}
                atomic_json(RUN / "parent_status.json", record)
                event("parent_reaped", **record)
            elif pid == monitor.pid:
                monitor_status = code
                event("monitor_reaped", exit_code=code)
            else:
                event("process_reaped", pid=pid, exit_code=code, wait_status=status)

        if monitor_status is not None and not (CONTROL / "monitor_stop").exists():
            atomic_json(
                RUN / "supervisor_error.json",
                {"monotonic_ns": monotonic_ns(), "error": "monitor exited early",
                 "monitor_exit_code": monitor_status},
            )
        if (CONTROL / "shutdown").exists():
            (CONTROL / "monitor_stop").touch()
            deadline = time.monotonic() + 2.0
            while monitor_status is None and time.monotonic() < deadline:
                try:
                    pid, status = os.waitpid(monitor.pid, os.WNOHANG)
                except ChildProcessError:
                    monitor_status = 0
                    break
                if pid:
                    monitor_status = exit_code_from_wait(status)
                    break
                time.sleep(0.01)
            if monitor_status is None:
                monitor.terminate()
            event("supervisor_shutdown", monitor_exit_code=monitor_status)
            return 0
        time.sleep(0.005)


if __name__ == "__main__":
    raise SystemExit(main())
