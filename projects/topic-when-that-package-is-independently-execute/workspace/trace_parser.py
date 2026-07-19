"""Parse ``strace -ff -ttt -yy`` output for target-file provenance.

The parser is intentionally independent of the experiment runner so it can be
unit-tested with synthetic traces and reused to inspect captured run data.
"""

from __future__ import annotations

import ast
import copy
import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence


OPEN_CALLS = {"open", "openat", "openat2", "creat"}
READ_CALLS = {"read", "pread64", "readv"}
WRITE_CALLS = {"write", "pwrite64", "writev"}
RENAME_CALLS = {"rename", "renameat", "renameat2"}
FORK_CALLS = {"fork", "vfork", "clone", "clone3"}


@dataclass(frozen=True)
class ParsedCall:
    timestamp: float
    order: int
    pid: int
    name: str
    args: tuple[str, ...]
    result: int
    raw: str


@dataclass(frozen=True)
class FileEvent:
    timestamp: float
    order: int
    pid: int
    kind: str
    path: str
    byte_count: int | None = None
    syscall: str = ""


@dataclass
class _ProcessState:
    # Lists/dicts permit Linux CLONE_FS and CLONE_FILES sharing semantics.
    cwd_ref: list[str]
    fds: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TargetProvenance:
    created_after_start: bool
    wrote_positive_bytes: bool
    write_before_read: bool
    first_create_time: float | None
    first_write_time: float | None
    first_read_time: float | None


_LINE_RE = re.compile(
    r"^(?:(?:\[pid\s+(?P<bracket_pid>\d+)\]|(?P<plain_pid>\d+))\s+)?"
    r"(?P<timestamp>\d+(?:\.\d+)?)\s+(?P<body>.*)$"
)
_CALL_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\((?P<args>.*)\)\s+=\s+(?P<result>.*)$")
_RESUMED_RE = re.compile(r"^<\.\.\.\s+(?P<name>\w+)\s+resumed>(?P<rest>.*)$")
_FD_RE = re.compile(r"^\s*(?P<fd>-?\d+)(?:<(?P<path>.*)>)?")
_INT_RESULT_RE = re.compile(r"^\s*(-?\d+)")


def _pid_from_trace_path(path: Path) -> int:
    match = re.search(r"\.(\d+)$", path.name)
    return int(match.group(1)) if match else 0


def _split_args(text: str) -> tuple[str, ...]:
    """Split a syscall argument list while respecting strings and nesting."""
    if not text.strip():
        return ()
    parts: list[str] = []
    start = 0
    quote = False
    escape = False
    depths = {"(": 0, "[": 0, "{": 0}
    closing = {")": "(", "]": "[", "}": "{"}
    for index, char in enumerate(text):
        if quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                quote = False
            continue
        if char == '"':
            quote = True
        elif char in depths:
            depths[char] += 1
        elif char in closing:
            opener = closing[char]
            depths[opener] = max(0, depths[opener] - 1)
        elif char == "," and not any(depths.values()):
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return tuple(parts)


def _result_integer(result: str) -> int | None:
    match = _INT_RESULT_RE.match(result)
    return int(match.group(1)) if match else None


def _decode_c_string(token: str) -> str | None:
    token = token.strip()
    if not token.startswith('"'):
        return None
    # strace can append an ellipsis after a quoted string. At -s 4096 this is
    # unusual for paths, but stripping it is safer than rejecting the line.
    match = re.match(r'^("(?:\\.|[^"\\])*")', token)
    if not match:
        return None
    try:
        value = ast.literal_eval(match.group(1))
    except (SyntaxError, ValueError):
        return None
    return value if isinstance(value, str) else None


def _fd_and_annotation(token: str) -> tuple[int | None, str | None]:
    match = _FD_RE.match(token)
    if not match:
        return None, None
    path = match.group("path")
    if path:
        path = re.sub(r"\s+\(deleted\)$", "", path)
    return int(match.group("fd")), path


def _normalize(path: str) -> str:
    normalized = os.path.normpath(path)
    return normalized if normalized.startswith("/") else "/" + normalized


def _resolve_path(
    path_token: str,
    state: _ProcessState,
    dirfd_token: str | None = None,
) -> str | None:
    path = _decode_c_string(path_token)
    if path is None:
        return None
    if path.startswith("/"):
        return _normalize(path)
    base = state.cwd_ref[0]
    if dirfd_token and dirfd_token.strip() != "AT_FDCWD":
        fd, annotation = _fd_and_annotation(dirfd_token)
        if annotation and annotation.startswith("/"):
            base = annotation
        elif fd is not None and fd in state.fds:
            base = state.fds[fd]
        else:
            return None
    return _normalize(str(PurePosixPath(base) / path))


def parse_trace_files(paths: Sequence[Path]) -> list[ParsedCall]:
    """Read and globally order calls from all per-process trace files."""
    calls: list[ParsedCall] = []
    unfinished: dict[tuple[int, str], tuple[str, int]] = {}
    order = 0
    for path in sorted(paths, key=lambda item: item.name):
        inferred_pid = _pid_from_trace_path(path)
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                order += 1
                line = line.rstrip("\n")
                match = _LINE_RE.match(line)
                if not match:
                    continue
                pid_text = match.group("bracket_pid") or match.group("plain_pid")
                pid = int(pid_text) if pid_text else inferred_pid
                timestamp = float(match.group("timestamp"))
                body = match.group("body")
                if body.endswith("<unfinished ...>"):
                    prefix = body[: -len("<unfinished ...>")].rstrip()
                    name_match = re.match(r"^(\w+)\(", prefix)
                    if name_match:
                        unfinished[(pid, name_match.group(1))] = (prefix, order)
                    continue
                resumed = _RESUMED_RE.match(body)
                if resumed:
                    key = (pid, resumed.group("name"))
                    pending = unfinished.pop(key, None)
                    if pending is None:
                        continue
                    body = pending[0] + resumed.group("rest")
                parsed = _CALL_RE.match(body)
                if not parsed:
                    continue
                result = _result_integer(parsed.group("result"))
                if result is None:
                    continue
                calls.append(
                    ParsedCall(
                        timestamp=timestamp,
                        order=order,
                        pid=pid,
                        name=parsed.group("name"),
                        args=_split_args(parsed.group("args")),
                        result=result,
                        raw=line,
                    )
                )
    return sorted(calls, key=lambda call: (call.timestamp, call.order))


def _state_for(states: dict[int, _ProcessState], pid: int, initial_cwd: str) -> _ProcessState:
    return states.setdefault(pid, _ProcessState([_normalize(initial_cwd)]))


def _path_for_fd(token: str, state: _ProcessState) -> tuple[int | None, str | None]:
    fd, annotation = _fd_and_annotation(token)
    if annotation and annotation.startswith("/"):
        path = _normalize(annotation)
        if fd is not None:
            state.fds[fd] = path
        return fd, path
    return fd, state.fds.get(fd) if fd is not None else None


def build_file_events(
    calls: Iterable[ParsedCall],
    targets: Iterable[str],
    *,
    initial_cwd: str = "/",
    initially_absent: Mapping[str, bool] | None = None,
) -> list[FileEvent]:
    """Resolve descriptors and convert successful syscalls into file events."""
    target_set = {_normalize(path) for path in targets}
    absent = {
        target: (True if initially_absent is None else bool(initially_absent.get(target, True)))
        for target in target_set
    }
    exists = {target: not was_absent for target, was_absent in absent.items()}
    states: dict[int, _ProcessState] = {}
    events: list[FileEvent] = []

    for call in calls:
        state = _state_for(states, call.pid, initial_cwd)
        args = call.args

        if call.name in FORK_CALLS and call.result > 0:
            share_files = call.name.startswith("clone") and any("CLONE_FILES" in arg for arg in args)
            share_fs = call.name.startswith("clone") and any("CLONE_FS" in arg for arg in args)
            child_state = _ProcessState(
                state.cwd_ref if share_fs else list(state.cwd_ref),
                state.fds if share_files else copy.copy(state.fds),
            )
            states[call.result] = child_state
            continue

        if call.name in OPEN_CALLS and call.result >= 0:
            if call.name in {"open", "creat"} and args:
                path = _resolve_path(args[0], state)
                flag_text = "O_CREAT" if call.name == "creat" else (args[1] if len(args) > 1 else "")
            elif len(args) >= 2:
                path = _resolve_path(args[1], state, args[0])
                flag_text = " ".join(args[2:])
            else:
                path = None
                flag_text = ""
            _, returned_annotation = _fd_and_annotation(str(call.result))
            if path is not None:
                state.fds[call.result] = path
                if path in target_set and "O_CREAT" in flag_text and not exists[path]:
                    events.append(FileEvent(call.timestamp, call.order, call.pid, "create", path, syscall=call.name))
                    exists[path] = True
            elif returned_annotation:
                state.fds[call.result] = _normalize(returned_annotation)
            continue

        if call.name in READ_CALLS | WRITE_CALLS and args and call.result > 0:
            _, path = _path_for_fd(args[0], state)
            if path in target_set:
                kind = "read" if call.name in READ_CALLS else "write"
                events.append(
                    FileEvent(call.timestamp, call.order, call.pid, kind, path, call.result, call.name)
                )
            continue

        if call.name == "close" and args and call.result == 0:
            fd, _ = _fd_and_annotation(args[0])
            if fd is not None:
                state.fds.pop(fd, None)
            continue

        if call.name in {"dup", "dup2", "dup3"} and args and call.result >= 0:
            old_fd, old_path = _path_for_fd(args[0], state)
            if old_fd is not None and old_path is not None:
                state.fds[call.result] = old_path
            continue

        if call.name == "chdir" and args and call.result == 0:
            path = _resolve_path(args[0], state)
            if path:
                state.cwd_ref[0] = path
            continue

        if call.name == "fchdir" and args and call.result == 0:
            _, path = _path_for_fd(args[0], state)
            if path:
                state.cwd_ref[0] = path
            continue

        if call.name in RENAME_CALLS and call.result == 0:
            if call.name == "rename" and len(args) >= 2:
                old_path = _resolve_path(args[0], state)
                new_path = _resolve_path(args[1], state)
            elif len(args) >= 4:
                old_path = _resolve_path(args[1], state, args[0])
                new_path = _resolve_path(args[3], state, args[2])
            else:
                old_path = new_path = None
            if new_path in target_set and not exists[new_path]:
                events.append(FileEvent(call.timestamp, call.order, call.pid, "create", new_path, syscall=call.name))
                exists[new_path] = True
            if old_path and new_path:
                # Writes made before the rename remain attributed to old_path;
                # later accesses through an already-open descriptor use new_path.
                for process in states.values():
                    for fd, fd_path in list(process.fds.items()):
                        if fd_path == old_path:
                            process.fds[fd] = new_path
            continue

    return sorted(events, key=lambda event: (event.timestamp, event.order))


def summarize_target(
    events: Iterable[FileEvent], target: str, launch_epoch: float
) -> TargetProvenance:
    target = _normalize(target)
    selected = [event for event in events if event.path == target]
    creates = [event.timestamp for event in selected if event.kind == "create"]
    writes = [event.timestamp for event in selected if event.kind == "write" and (event.byte_count or 0) > 0]
    reads = [event.timestamp for event in selected if event.kind == "read" and (event.byte_count or 0) > 0]
    first_create = min(creates) if creates else None
    first_write = min(writes) if writes else None
    first_read = min(reads) if reads else None
    wrote = first_write is not None
    return TargetProvenance(
        created_after_start=first_create is not None and first_create > launch_epoch,
        wrote_positive_bytes=wrote,
        write_before_read=wrote and (first_read is None or first_write < first_read),
        first_create_time=first_create,
        first_write_time=first_write,
        first_read_time=first_read,
    )


def analyze_trace_set(
    trace_paths: Sequence[Path],
    targets: Sequence[str],
    launch_epoch: float,
    *,
    initial_cwd: str = "/",
    initially_absent: Mapping[str, bool] | None = None,
) -> dict[str, TargetProvenance]:
    calls = parse_trace_files(trace_paths)
    events = build_file_events(
        calls,
        targets,
        initial_cwd=initial_cwd,
        initially_absent=initially_absent,
    )
    return {target: summarize_target(events, target, launch_epoch) for target in targets}
