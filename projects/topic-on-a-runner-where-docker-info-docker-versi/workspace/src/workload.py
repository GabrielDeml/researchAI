"""Designated parent and its exactly one workload descendant."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from common import RUN, event


def released() -> bool:
    return (RUN / "release").exists()


def write_compute(seed: int, iterations: int, mode: str, ready_fd: int) -> int:
    digest = seed.to_bytes(8, "big")
    for _ in range(iterations):
        digest = hashlib.sha256(digest).digest()
    output = RUN / "result.json"
    with output.open("w", encoding="utf-8") as handle:
        json.dump({"digest": digest.hex()}, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())

    if mode == "anomaly":
        # Enter continuing work before declaring readiness.
        for _ in range(10_000):
            digest = hashlib.sha256(digest).digest()
        event("descendant_ready", kind="compute", output_closed=True)
        os.write(ready_fd, b"R")
        os.close(ready_fd)
        while not released():
            for _ in range(10_000):
                digest = hashlib.sha256(digest).digest()
    else:
        event("descendant_ready", kind="compute", output_closed=True)
        os.write(ready_fd, b"R")
        os.close(ready_fd)
    event("descendant_exit", kind="compute")
    return 0


def deterministic_output(seed: int, size: int):
    emitted = 0
    counter = 0
    seed_bytes = seed.to_bytes(8, "big")
    while emitted < size:
        block = hashlib.sha256(seed_bytes + counter.to_bytes(8, "big")).digest()
        chunk = block[: min(len(block), size - emitted)]
        yield chunk
        emitted += len(chunk)
        counter += 1


def write_output(seed: int, size: int, mode: str, ready_fd: int) -> int:
    output = RUN / "declared_output.bin"
    with output.open("wb") as handle:
        for chunk in deterministic_output(seed, size):
            handle.write(chunk)
        handle.flush()
        os.fsync(handle.fileno())
        if mode == "anomaly":
            event("descendant_ready", kind="output", output_fd_open=True)
            os.write(ready_fd, b"R")
            os.close(ready_fd)
            while not released():
                time.sleep(0.01)
        else:
            handle.close()
            event("descendant_ready", kind="output", output_fd_open=False)
            os.write(ready_fd, b"R")
            os.close(ready_fd)
    event("descendant_exit", kind="output")
    return 0


def parent(args: argparse.Namespace) -> int:
    read_fd, write_fd = os.pipe()
    command = [
        sys.executable,
        "/app/workload.py",
        "child",
        "--kind",
        args.kind,
        "--mode",
        args.mode,
        "--seed",
        str(args.seed),
        "--parameter",
        str(args.parameter),
        "--ready-fd",
        str(write_fd),
    ]
    child = subprocess.Popen(command, pass_fds=(write_fd,), close_fds=True)
    os.close(write_fd)
    event("descendant_spawn", descendant_pid=child.pid)
    try:
        ready = os.read(read_fd, 1)
    finally:
        os.close(read_fd)
    if ready != b"R":
        event("parent_error", reason="descendant readiness pipe closed")
        return 2
    time.sleep(0.2)
    if args.mode == "control":
        code = child.wait()
        if code != 0:
            event("parent_error", reason="control descendant failed", child_code=code)
            return 3
    event("parent_exit", exit_code=0)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="role", required=True)
    for role in ("parent", "child"):
        child = subparsers.add_parser(role)
        child.add_argument("--kind", choices=("compute", "output"), required=True)
        child.add_argument("--mode", choices=("anomaly", "control"), required=True)
        child.add_argument("--seed", type=int, required=True)
        child.add_argument("--parameter", type=int, required=True)
        if role == "child":
            child.add_argument("--ready-fd", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.role == "parent":
        return parent(args)
    if args.kind == "compute":
        return write_compute(args.seed, args.parameter, args.mode, args.ready_fd)
    return write_output(args.seed, args.parameter, args.mode, args.ready_fd)


if __name__ == "__main__":
    raise SystemExit(main())
