"""Persistent process-tree and declared-output descriptor monitor."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any

from common import CONTROL, RUN, atomic_json, event, monotonic_ns


ProcKey = tuple[int, int]


def proc_stat(pid: int) -> tuple[ProcKey, int] | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (FileNotFoundError, ProcessLookupError):
        return None
    close = raw.rfind(")")
    if close < 0:
        raise RuntimeError(f"malformed /proc/{pid}/stat")
    fields = raw[close + 2 :].split()
    if len(fields) < 20:
        raise RuntimeError(f"short /proc/{pid}/stat")
    return (pid, int(fields[19])), int(fields[1])


def scan_processes() -> dict[ProcKey, int]:
    processes: dict[ProcKey, int] = {}
    try:
        entries = list(Path("/proc").iterdir())
    except OSError as error:
        raise RuntimeError(f"cannot enumerate /proc: {error}") from error
    for entry in entries:
        if not entry.name.isdigit():
            continue
        result = proc_stat(int(entry.name))
        if result is not None:
            key, ppid = result
            processes[key] = ppid
    return processes


def output_inodes(paths: list[str]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for declared in paths:
        try:
            stat = os.stat(declared, follow_symlinks=True)
        except FileNotFoundError:
            continue
        values.append({"path": declared, "st_dev": stat.st_dev, "st_ino": stat.st_ino})
    return values


def descriptor_holders(
    processes: dict[ProcKey, int], inodes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    targets = {(item["st_dev"], item["st_ino"]): item["path"] for item in inodes}
    holders: list[dict[str, Any]] = []
    if not targets:
        return holders
    by_pid = {key[0]: (key, ppid) for key, ppid in processes.items()}
    for pid, (key, ppid) in by_pid.items():
        fd_dir = Path(f"/proc/{pid}/fd")
        try:
            fds = list(fd_dir.iterdir())
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError as error:
            raise RuntimeError(f"cannot inspect {fd_dir}: {error}") from error
        for fd_path in fds:
            try:
                stat = os.stat(fd_path)
                match = targets.get((stat.st_dev, stat.st_ino))
                if match is None:
                    continue
                target = os.readlink(fd_path)
            except (FileNotFoundError, ProcessLookupError):
                continue
            except PermissionError as error:
                raise RuntimeError(f"cannot inspect {fd_path}: {error}") from error
            holders.append(
                {
                    "pid": key[0],
                    "starttime": key[1],
                    "ppid": ppid,
                    "fd": int(fd_path.name),
                    "target": target,
                    "declared_output": match,
                    "st_dev": stat.st_dev,
                    "st_ino": stat.st_ino,
                }
            )
    holders.sort(key=lambda item: (item["pid"], item["fd"]))
    return holders


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def main() -> int:
    config = json.loads((RUN / "config.json").read_text(encoding="utf-8"))
    declared = config["declared_outputs"]
    tracked: set[ProcKey] = set()
    parent_key: ProcKey | None = None
    completed_requests: set[str] = set()
    samples = 0
    release_seen = False
    event("monitor_started")

    while not (CONTROL / "monitor_stop").exists():
        loop_started = monotonic_ns()
        try:
            processes = scan_processes()
            parent_record = read_json(RUN / "parent_pid.json")
            if parent_record is not None and parent_key is None:
                parent_pid = int(parent_record["pid"])
                matches = [key for key in processes if key[0] == parent_pid]
                if matches:
                    parent_key = matches[0]

            changed = True
            while changed:
                changed = False
                # Only a live PID tuple may contribute new PPID edges; a dead
                # retained tuple cannot create false lineage after PID reuse.
                ancestor_pids = {key[0] for key in tracked if key in processes}
                if parent_key is not None and parent_key in processes:
                    ancestor_pids.add(parent_key[0])
                for key, ppid in processes.items():
                    if key != parent_key and key not in tracked and ppid in ancestor_pids:
                        tracked.add(key)
                        changed = True

            inodes = output_inodes(declared)
            holders = descriptor_holders(processes, inodes)
            alive = [
                {"pid": key[0], "starttime": key[1], "ppid": processes[key]}
                for key in sorted(tracked)
                if key in processes
            ]
            parent_status = read_json(RUN / "parent_status.json")
            parent_ok = parent_status is not None and parent_status.get("exit_code") == 0
            state = {
                "monotonic_ns": monotonic_ns(),
                "sample_number": samples,
                "parent_pid_tuple": (
                    {"pid": parent_key[0], "starttime": parent_key[1]}
                    if parent_key is not None
                    else None
                ),
                "parent_exit_status": parent_status,
                "tracked_descendants": [
                    {"pid": key[0], "starttime": key[1]} for key in sorted(tracked)
                ],
                "live_descendants": alive,
                "declared_output_inodes": inodes,
                "output_descriptor_holders": holders,
                "naive_accept": bool(parent_ok),
                "tree_accept": bool(parent_ok and not alive and not holders),
                "monitor_error": None,
            }
            samples += 1
            # Sampling remains 10 ms; publish the heartbeat less often so bind
            # mount fsync latency does not become the sampling cadence.
            if samples <= 2 or samples % 10 == 0:
                atomic_json(RUN / "monitor_latest.json", state)
            if not release_seen and (RUN / "release").exists():
                release_seen = True
                event("release_observed")
            if samples == 2:
                atomic_json(
                    RUN / "monitor_ready.json",
                    {"monotonic_ns": monotonic_ns(), "samples": samples},
                )
                event("monitor_ready", samples=samples)

            requests = sorted((CONTROL / "snapshots").glob("*.request"))
            for request in requests:
                request_id = request.stem
                if request_id in completed_requests:
                    continue
                snapshot = {**state, "request_id": request_id}
                atomic_json(RUN / "snapshots" / f"{request_id}.json", snapshot)
                completed_requests.add(request_id)
        except Exception as error:
            failure = {
                "monotonic_ns": monotonic_ns(),
                "error": f"{type(error).__name__}: {error}",
            }
            atomic_json(RUN / "monitor_error.json", failure)
            event("monitor_error", error=failure["error"])
            return 2

        elapsed = monotonic_ns() - loop_started
        time.sleep(max(0.0, 0.01 - elapsed / 1e9))

    event("monitor_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
