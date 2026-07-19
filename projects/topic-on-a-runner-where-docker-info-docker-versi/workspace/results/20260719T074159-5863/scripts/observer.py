#!/usr/bin/env python3
"""PID-reuse-safe /proc observer producing the shared monitor stream."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time


STATE = Path("/state")
DECLARED_OUTPUT = "/state/declared-output.bin"
SAMPLE_SECONDS = 0.020


def monotonic_ns() -> int:
    return time.monotonic_ns()


def atomic_touch(path: Path) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{monotonic_ns()}.tmp")
    with temporary.open("wb") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def emit(record: dict[str, object]) -> None:
    print(json.dumps(record, sort_keys=True, separators=(",", ":")), flush=True)


def read_stat(pid: int) -> tuple[int, int] | None:
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        closing = text.rfind(")")
        if closing < 0:
            return None
        fields = text[closing + 2 :].split()
        return int(fields[1]), int(fields[19])  # ppid (field 4), starttime (field 22)
    except (OSError, ValueError, IndexError):
        return None


def proc_snapshot() -> dict[int, tuple[int, int]]:
    snapshot: dict[int, tuple[int, int]] = {}
    try:
        entries = os.scandir("/proc")
    except OSError:
        return snapshot
    with entries:
        for entry in entries:
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            stat = read_stat(pid)
            if stat is not None:
                snapshot[pid] = stat
    return snapshot


def open_declared_output(pid: int) -> bool:
    try:
        entries = os.scandir(f"/proc/{pid}/fd")
    except OSError:
        return False
    with entries:
        for entry in entries:
            try:
                target = os.readlink(entry.path)
            except OSError:
                continue
            if target == DECLARED_OUTPUT or target == f"{DECLARED_OUTPUT} (deleted)":
                return True
    return False


def result_code() -> int | None:
    try:
        return int((STATE / "parent-result").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def main() -> int:
    observer_started_ns = monotonic_ns()
    while not (STATE / "parent.pid").exists():
        time.sleep(0.005)
    parent_pid = int((STATE / "parent.pid").read_text(encoding="utf-8").strip())

    parent_identity: tuple[int, int] | None = None
    tracked: set[tuple[int, int]] = set()
    observed_parent = False
    ready_written = False
    naive_event: dict[str, object] | None = None
    sample_index = 0
    next_sample = time.monotonic()

    while True:
        now_ns = monotonic_ns()
        snapshot = proc_snapshot()
        if parent_identity is None and parent_pid in snapshot:
            parent_identity = (parent_pid, snapshot[parent_pid][1])
        parent_exists = bool(
            parent_identity is not None
            and parent_pid in snapshot
            and snapshot[parent_pid][1] == parent_identity[1]
        )
        observed_parent = observed_parent or parent_exists

        # Discover the complete recursive tree only while the designated parent
        # identity is alive. Retain identities forever after discovery.
        if parent_exists:
            frontier = {parent_pid}
            descendants: set[int] = set()
            while frontier:
                current = frontier.pop()
                children = {pid for pid, (ppid, _start) in snapshot.items() if ppid == current}
                children -= descendants
                descendants.update(children)
                frontier.update(children)
            for pid in descendants:
                tracked.add((pid, snapshot[pid][1]))

        live_identities = sorted(
            identity
            for identity in tracked
            if identity[0] in snapshot and snapshot[identity[0]][1] == identity[1]
        )
        open_pids = [pid for pid, _start in live_identities if open_declared_output(pid)]
        output_open = bool(open_pids)

        if observed_parent and tracked and not ready_written:
            atomic_touch(STATE / "observer-ready")
            ready_written = True

        code = result_code()
        aware_now = (
            code == 0
            and not parent_exists
            and not live_identities
            and not output_open
        )
        sample = {
            "event": "sample",
            "sample_index": sample_index,
            "monotonic_ns": now_ns,
            "observer_elapsed_s": (now_ns - observer_started_ns) / 1e9,
            "parent_exists": parent_exists,
            "parent_result": code,
            "tracked_count": len(tracked),
            "live_descendant_count": len(live_identities),
            "live_identities": [[pid, start] for pid, start in live_identities],
            "declared_output_open": output_open,
            "declared_output_open_pids": open_pids,
            "naive_accept": code == 0 and not parent_exists,
            "aware_accept": aware_now,
        }
        emit(sample)

        if naive_event is None and sample["naive_accept"]:
            naive_event = dict(sample)
            emit({"event": "naive_acceptance", **{k: v for k, v in sample.items() if k != "event"}})

        if aware_now:
            emit({"event": "aware_acceptance", **{k: v for k, v in sample.items() if k != "event"}})
            emit({
                "event": "observer_summary",
                "monotonic_ns": monotonic_ns(),
                "observer_started_ns": observer_started_ns,
                "parent_pid": parent_pid,
                "parent_identity": list(parent_identity) if parent_identity else None,
                "tracked_identities": [list(item) for item in sorted(tracked)],
                "sample_count": sample_index + 1,
                "ready_written": ready_written,
                "naive_seen": naive_event is not None,
            })
            return 0

        sample_index += 1
        next_sample += SAMPLE_SECONDS
        delay = next_sample - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        else:
            next_sample = time.monotonic()


if __name__ == "__main__":
    raise SystemExit(main())
