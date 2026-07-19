#!/usr/bin/env python3
"""Designated parent and its single deterministic descendant."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import random
import subprocess
import sys
import time


STATE = Path("/state")
DECLARED_OUTPUT = STATE / "declared-output.bin"


def monotonic_ns() -> int:
    return time.monotonic_ns()


def atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{monotonic_ns()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_touch(path: Path) -> None:
    atomic_write(path, "")


def wait_for(path: Path, timeout_s: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out waiting for {path}")
        time.sleep(0.005)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("parent", "descendant"), default="parent")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--kind", choices=("cpu", "open"), required=True)
    parser.add_argument("--class-name", choices=("adversarial", "control"), required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--fixture-index", type=int, required=True)
    return parser.parse_args()


def descendant(args: argparse.Namespace) -> int:
    atomic_write(STATE / "descendant.pid", f"{os.getpid()}\n")
    atomic_touch(STATE / "descendant-ready")
    wait_for(STATE / "activate")

    if args.kind == "cpu":
        atomic_touch(STATE / "active")
        deadline = time.monotonic() + args.duration
        counter = 0
        material = f"{args.seed}:{args.fixture_index}".encode("ascii")
        digest = hashlib.sha256(material).digest()
        while time.monotonic() < deadline:
            digest = hashlib.sha256(digest + material + counter.to_bytes(8, "little")).digest()
            counter += 1
        atomic_write(STATE / "cpu-digest", f"{digest.hex()} {counter}\n")
    else:
        generator = random.Random(args.seed + args.fixture_index)
        payload = generator.randbytes(4096)
        with DECLARED_OUTPUT.open("ab", buffering=0) as handle:
            handle.write(payload)
            os.fsync(handle.fileno())
            atomic_touch(STATE / "active")
            deadline = time.monotonic() + args.duration
            while time.monotonic() < deadline:
                time.sleep(min(0.010, max(0.0, deadline - time.monotonic())))

    atomic_write(STATE / "descendant-result", "0\n")
    return 0


def parent(args: argparse.Namespace) -> int:
    child_command = [
        sys.executable,
        "/experiment/fixture.py",
        "--role", "descendant",
        "--fixture", args.fixture,
        "--kind", args.kind,
        "--class-name", args.class_name,
        "--duration", str(args.duration),
        "--seed", str(args.seed),
        "--fixture-index", str(args.fixture_index),
    ]
    child = subprocess.Popen(child_command, close_fds=True)
    atomic_write(STATE / "launched-descendant.pid", f"{child.pid}\n")
    wait_for(STATE / "descendant-ready")
    wait_for(STATE / "observer-ready")
    # Ensure at least 25 observer samples can discover the child while ancestry
    # is intact before the child is activated and the adversarial parent exits.
    deadline = time.monotonic() + 0.500
    while time.monotonic() < deadline:
        time.sleep(min(0.010, max(0.0, deadline - time.monotonic())))
    atomic_touch(STATE / "activate")
    wait_for(STATE / "active")

    if args.class_name == "control":
        child_exit_code = child.wait()
        atomic_write(STATE / "descendant-exit-code", f"{child_exit_code}\n")
        if child_exit_code != 0:
            atomic_write(STATE / "parent-result", f"{child_exit_code}\n")
            return child_exit_code
        # A process exit closes all of its descriptors. Verify the tracked PID
        # is gone before recording the control's closure guarantee.
        proc_path = Path(f"/proc/{child.pid}")
        verify_deadline = time.monotonic() + 1.0
        while proc_path.exists() and time.monotonic() < verify_deadline:
            time.sleep(0.002)
        if proc_path.exists():
            atomic_write(STATE / "parent-result", "70\n")
            return 70
        atomic_touch(STATE / "control-output-closed")

    atomic_write(STATE / "parent-result", "0\n")
    return 0


def main() -> int:
    args = parse_args()
    return descendant(args) if args.role == "descendant" else parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
