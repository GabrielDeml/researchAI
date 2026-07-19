#!/usr/bin/env python3
"""PID-1 fixture and dual logical monitor for the Docker experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import time
from typing import Any


POLL_SECONDS = 0.01
WORKER_SECONDS = 3.0
GRACE_SECONDS = 1.0
OUTPUT = Path("/work/result.dat")
RECORD = Path("/work/record.json")
FIXTURES = {
    "D1": ("cpu-child", False), "C1": ("cpu-child", True),
    "D2": ("output-child", False), "C2": ("output-child", True),
    "D3": ("cpu-output-child", False), "C3": ("cpu-output-child", True),
    "D4": ("cpu-grandchild", False), "C4": ("cpu-grandchild", True),
    "D5": ("output-grandchild", False), "C5": ("output-grandchild", True),
    "D6": ("split-children", False), "C6": ("split-children", True),
}
Identity = tuple[int, int]


def now() -> float:
    return time.monotonic()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def parse_stat_text(raw: str, expected_pid: int) -> tuple[Identity, int]:
    close = raw.rfind(")")
    if close < 0:
        raise RuntimeError(f"malformed /proc/{expected_pid}/stat")
    fields = raw[close + 2:].split()  # starts at field 3 (state)
    if len(fields) < 20:
        raise RuntimeError(f"short /proc/{expected_pid}/stat")
    return (expected_pid, int(fields[19])), int(fields[1])


def proc_stat(pid: int) -> tuple[Identity, int] | None:
    try:
        return parse_stat_text(Path(f"/proc/{pid}/stat").read_text(), pid)
    except (FileNotFoundError, ProcessLookupError):
        return None


def processes() -> dict[Identity, int]:
    answer: dict[Identity, int] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            item = proc_stat(pid)
        except PermissionError as error:
            if proc_stat(pid) is None:
                continue
            raise RuntimeError(f"persistent permission error reading /proc/{pid}/stat: {error}")
        if item is not None:
            answer[item[0]] = item[1]
    return answer


def output_holders(snapshot: dict[Identity, int]) -> list[dict[str, int]]:
    try:
        target_stat = OUTPUT.stat()
    except FileNotFoundError:
        return []
    target = (target_stat.st_dev, target_stat.st_ino)
    holders: list[dict[str, int]] = []
    for identity in sorted(snapshot):
        pid, starttime = identity
        directory = Path(f"/proc/{pid}/fd")
        try:
            entries = list(directory.iterdir())
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError as error:
            if proc_stat(pid) != (identity, snapshot[identity]):
                continue
            raise RuntimeError(f"persistent permission error reading {directory}: {error}")
        for fd in entries:
            try:
                descriptor_stat = fd.stat()
            except (FileNotFoundError, ProcessLookupError):
                continue
            except PermissionError as error:
                if proc_stat(pid) != (identity, snapshot[identity]):
                    continue
                raise RuntimeError(f"persistent permission error reading {fd}: {error}")
            if (descriptor_stat.st_dev, descriptor_stat.st_ino) == target:
                holders.append({"pid": pid, "starttime": starttime, "fd": int(fd.name)})
    return holders


def deterministic_bytes(seed: int) -> bytes:
    block = hashlib.sha256(seed.to_bytes(8, "big") + b"result.dat").digest()
    return (block * (4096 // len(block) + 1))[:4096]


def compute_until(deadline: float) -> None:
    payload = bytes(range(256)) * 16
    while now() < deadline:
        hashlib.sha256(payload).digest()


def terminal_worker(kind: str, seed: int, ready_fd: int) -> None:
    started = now()
    deadline = started + WORKER_SECONDS
    handle = None
    try:
        if "output" in kind:
            handle = OUTPUT.open("ab", buffering=0)
            handle.write(deterministic_bytes(seed))
            os.fsync(handle.fileno())
        if "cpu" in kind:
            # Readiness is emitted only after computation has actually begun.
            hashlib.sha256(bytes(range(256)) * 16).digest()
        os.write(ready_fd, b"R")
        os.close(ready_fd)
        if "cpu" in kind:
            compute_until(deadline)
        else:
            time.sleep(max(0.0, deadline - now()))
        if handle is not None:
            handle.close()
        os._exit(0)
    except BaseException:
        try:
            os.close(ready_fd)
        except OSError:
            pass
        os._exit(91)


def spawn_terminal(kind: str, seed: int, ready_read: int, ready_write: int) -> int:
    pid = os.fork()
    if pid == 0:
        os.close(ready_read)
        terminal_worker(kind, seed, ready_write)
    return pid


def wait_ok(pid: int) -> bool:
    _, status = os.waitpid(pid, 0)
    return os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0


def parent_main(fixture: str, seed: int, grace_fd: int) -> int:
    kind, clean = FIXTURES[fixture]
    ready_read, ready_write = os.pipe()
    direct: list[int] = []
    expected = 2 if kind == "split-children" else 1

    if kind in {"cpu-child", "output-child", "cpu-output-child"}:
        direct.append(spawn_terminal(kind.removesuffix("-child"), seed, ready_read, ready_write))
    elif kind == "split-children":
        direct.append(spawn_terminal("cpu", seed, ready_read, ready_write))
        direct.append(spawn_terminal("output", seed + 1, ready_read, ready_write))
    else:
        terminal_kind = "cpu" if kind == "cpu-grandchild" else "output"
        intermediate = os.fork()
        if intermediate == 0:
            grandchild = spawn_terminal(terminal_kind, seed, ready_read, ready_write)
            os.close(ready_read)
            os.close(ready_write)
            if clean:
                os._exit(0 if wait_ok(grandchild) else 92)
            time.sleep(0.75)
            os._exit(0)
        direct.append(intermediate)

    os.close(ready_write)
    readiness = b""
    while len(readiness) < expected:
        chunk = os.read(ready_read, expected - len(readiness))
        if not chunk:
            return 93
        readiness += chunk
    os.close(ready_read)

    os.write(grace_fd, b"G")
    os.close(grace_fd)
    grace_deadline = now() + GRACE_SECONDS
    time.sleep(max(0.0, grace_deadline - now()))

    if clean:
        for pid in direct:
            if not wait_ok(pid):
                return 94
        snapshot = processes()
        if output_holders(snapshot):
            return 95
    return 0


def status_code(status: int) -> int:
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return 255


def sample_tree(
    parent: Identity,
    tracked: set[Identity],
) -> tuple[dict[Identity, int], list[Identity], list[dict[str, int]]]:
    snapshot = processes()
    changed = True
    while changed:
        changed = False
        live_ancestors = {item[0] for item in tracked if item in snapshot}
        if parent in snapshot:
            live_ancestors.add(parent[0])
        for identity, ppid in snapshot.items():
            if identity != parent and identity not in tracked and ppid in live_ancestors:
                tracked.add(identity)
                changed = True
    alive = sorted(identity for identity in tracked if identity in snapshot)
    return snapshot, alive, output_holders(snapshot)


def run(fixture: str, seed: int, execution_id: str) -> int:
    random.seed(1729)
    OUTPUT.touch(exist_ok=False)
    os.chmod(OUTPUT, 0o644)
    container_start = now()
    grace_read, grace_write = os.pipe()
    os.set_blocking(grace_read, False)
    parent_pid = os.fork()
    if parent_pid == 0:
        os.close(grace_read)
        os._exit(parent_main(fixture, seed, grace_write))
    os.close(grace_write)
    first = proc_stat(parent_pid)
    if first is None:
        raise RuntimeError("designated parent disappeared before its identity was read")
    parent_identity = first[0]

    tracked: set[Identity] = set()
    output_samples: list[dict[str, Any]] = []
    invariant_failures: list[str] = []
    parent_exit_time: float | None = None
    naive_completion: float | None = None
    aware_completion: float | None = None
    parent_exit_code: int | None = None
    naive_at_exit = False
    aware_at_exit = False
    aware_earlier = False
    exact_alive: list[Identity] = []
    exact_holders: list[dict[str, int]] = []
    prior_alive: set[Identity] = set()
    prior_open = False
    last_descendant_exit = container_start
    final_output_close = container_start
    grace_seen = False
    grace_polls = 0
    monitor_error: str | None = None

    while aware_completion is None:
        loop_start = now()
        try:
            if not grace_seen:
                try:
                    grace_seen = os.read(grace_read, 1) == b"G"
                except BlockingIOError:
                    pass
            snapshot, alive, holders = sample_tree(parent_identity, tracked)
            sample_time = now()
            alive_set = set(alive)
            is_open = bool(holders)
            if prior_alive - alive_set:
                last_descendant_exit = sample_time
            if prior_open and not is_open:
                final_output_close = sample_time
            prior_alive = alive_set
            prior_open = is_open
            output_samples.append({
                "timestamp": sample_time,
                "open": is_open,
                "holders": holders,
            })
            if grace_seen and parent_exit_time is None:
                grace_polls += 1

            reaped_parent: int | None = None
            while True:
                try:
                    pid, status = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    break
                if pid == 0:
                    break
                if pid == parent_pid:
                    reaped_parent = status
            if reaped_parent is not None:
                parent_exit_time = now()
                parent_exit_code = status_code(reaped_parent)
                naive_completion = parent_exit_time if parent_exit_code == 0 else None
                naive_at_exit = parent_exit_code == 0
                # The exact parent-exit decisions use a fresh post-waitpid sample.
                snapshot, exact_alive, exact_holders = sample_tree(parent_identity, tracked)
                exact_time = now()
                exact_open = bool(exact_holders)
                output_samples.append({
                    "timestamp": exact_time,
                    "open": exact_open,
                    "holders": exact_holders,
                    "parent_exit_sample": True,
                })
                aware_at_exit = bool(parent_exit_code == 0 and not exact_alive and not exact_open)
                if aware_at_exit:
                    aware_completion = exact_time

            if parent_exit_time is not None and aware_completion is None:
                # Reap adopted orphans before deciding whether identities remain.
                while True:
                    try:
                        pid, _ = os.waitpid(-1, os.WNOHANG)
                    except ChildProcessError:
                        break
                    if pid == 0:
                        break
                _, alive, holders = sample_tree(parent_identity, tracked)
                decision_time = now()
                if not alive:
                    last_descendant_exit = max(last_descendant_exit, decision_time)
                if not holders and prior_open:
                    final_output_close = max(final_output_close, decision_time)
                if parent_exit_code == 0 and not alive and not holders:
                    aware_completion = decision_time
        except BaseException as error:
            monitor_error = f"{type(error).__name__}: {error}"
            break

        elapsed = now() - loop_start
        time.sleep(max(0.0, POLL_SECONDS - elapsed))

    os.close(grace_read)
    kind, clean = FIXTURES[fixture]
    if parent_exit_code != 0:
        invariant_failures.append(f"parent exit code was {parent_exit_code}")
    if grace_polls < 50:
        invariant_failures.append(f"only {grace_polls} readiness-grace polls; need at least 50")
    if clean and (exact_alive or exact_holders):
        invariant_failures.append("clean fixture had live descendant or open output at parent exit")
    if not clean and not (exact_alive or exact_holders):
        invariant_failures.append("dirty fixture had no live descendant and no open output at parent exit")
    if aware_earlier:
        invariant_failures.append("aware monitor accepted before the parent-exit sample")
    if monitor_error:
        invariant_failures.append(monitor_error)
    if aware_completion is None:
        invariant_failures.append("aware monitor never accepted")

    record = {
        "schema_version": 1,
        "execution_id": execution_id,
        "fixture_id": fixture,
        "dirty": not clean,
        "control": clean,
        "seed": seed,
        "image_id": os.environ.get("EXPERIMENT_IMAGE_ID", ""),
        "parent_pid": parent_identity[0],
        "parent_starttime": parent_identity[1],
        "parent_exit_code": parent_exit_code,
        "discovered_descendants": [
            {"pid": pid, "starttime": starttime} for pid, starttime in sorted(tracked)
        ],
        "declared_output_samples": output_samples,
        "parent_exit_timestamp": parent_exit_time,
        "naive_completion_timestamp": naive_completion,
        "aware_completion_timestamp": aware_completion,
        "last_descendant_exit_timestamp": last_descendant_exit,
        "final_output_close_timestamp": final_output_close,
        "naive_accept_at_parent_exit": naive_at_exit,
        "aware_accept_at_parent_exit": aware_at_exit,
        "aware_accepted_before_parent_exit": aware_earlier,
        "eventual_aware_accept": aware_completion is not None,
        "alive_descendants_at_parent_exit": [
            {"pid": pid, "starttime": starttime} for pid, starttime in exact_alive
        ],
        "output_holders_at_parent_exit": exact_holders,
        "readiness_grace_polls": grace_polls,
        "aware_safety_lag_seconds": (
            aware_completion - parent_exit_time
            if aware_completion is not None and parent_exit_time is not None else None
        ),
        "closure_lag_seconds": (
            max(last_descendant_exit, final_output_close) - parent_exit_time
            if parent_exit_time is not None else None
        ),
        "aware_after_closure_seconds": (
            aware_completion - max(last_descendant_exit, final_output_close)
            if aware_completion is not None else None
        ),
        "invariant_failures": invariant_failures,
    }
    atomic_json(RECORD, record)
    return 0 if not invariant_failures else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", choices=sorted(FIXTURES), required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--execution-id", required=True)
    args = parser.parse_args()
    return run(args.fixture, args.seed, args.execution_id)


if __name__ == "__main__":
    raise SystemExit(main())
