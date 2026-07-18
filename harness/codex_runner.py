"""Wrapper around `codex exec`: the sandboxed, timeout-enforced invocation of
the Codex CLI coding agent used for stage 5 (implement + run).

Codex is given `--sandbox workspace-write` confined to the project's
`workspace/` directory (macOS Seatbelt underneath), with network access
enabled inside that sandbox so it can `pip install`. On top of Codex's own
sandbox this module enforces a hard wall-clock timeout by running the process
in its own process group and killing the whole group if it overruns, *and*
walking the descendant process tree by PID and signaling those directly too
-- codex spawns each shell tool-call in its own process group, so a plain
`killpg` on codex's own group can leave a long-running command (e.g. a stray
`sleep`) behind as an orphan after codex itself exits.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from .config import Config
from .state import CodexResult

CODEX_BIN = (
    os.environ.get("RESEARCHAI_CODEX_BIN")
    or shutil.which("codex")
    or "/opt/homebrew/bin/codex"
)

# Grace period between SIGTERM and SIGKILL when a run overruns its timeout.
SIGTERM_GRACE_SECONDS = 10


def run_codex(
    prompt: str,
    workspace: Path,
    model: str,
    timeout_minutes: float,
    log_path: Path,
    cfg: Config,
) -> CodexResult:
    """Run `codex exec` non-interactively in `workspace`.

    Combined stdout+stderr is appended to `log_path` as it's produced (the
    dashboard tails this file live). Enforces a hard wall-clock timeout:
    on overrun, SIGTERM the whole process group, wait a short grace period,
    then SIGKILL it. Returns a CodexResult; never raises for a
    timeout/non-zero exit -- callers decide what a bad result means.
    """
    workspace.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    argv = [
        CODEX_BIN, "exec",
        "-m", model,
        "--sandbox", "workspace-write",
        "--cd", str(workspace),
        "--skip-git-repo-check",
        "-c", "approval_policy=never",
        "-c", "sandbox_workspace_write.network_access=true",
        prompt,
    ]

    start = time.monotonic()
    timed_out = False
    exit_code: int | None = None

    with log_path.open("a", buffering=1) as log_f:
        log_f.write(
            f"\n===== codex exec start {time.strftime('%Y-%m-%dT%H:%M:%S')} "
            f"model={model} timeout_minutes={timeout_minutes} workspace={workspace} =====\n"
        )
        log_f.flush()

        proc = subprocess.Popen(
            argv,
            cwd=str(workspace),
            stdin=subprocess.DEVNULL,  # never let codex block on "reading from stdin"
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # own process group -> killable as a unit
        )
        try:
            proc.wait(timeout=timeout_minutes * 60)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_process_group(proc, log_f)

        exit_code = proc.returncode if proc.returncode is not None else -9
        duration_s = time.monotonic() - start
        log_f.write(
            f"\n===== codex exec end exit={exit_code} timed_out={timed_out} "
            f"duration_s={duration_s:.1f} =====\n"
        )

        _warn_if_over_quota(workspace, cfg, log_f)

    return CodexResult(
        exit_code=exit_code,
        timed_out=timed_out,
        transcript_path=str(log_path),
        duration_s=duration_s,
    )


def _kill_process_group(proc: subprocess.Popen, log_f) -> None:
    """SIGTERM the process group, give it a grace period, then SIGKILL.

    A plain `killpg` on codex's own group is not always enough: codex spawns
    each shell tool-call in its own process group (observed directly -- a
    `sleep 300` it ran survived a killpg of codex's group and was left
    running, reparented to pid 1, after codex itself exited). So in addition
    to the group kill, walk the full descendant tree by PID *before* anything
    dies (a killed/reparented descendant loses its traceable ppid lineage)
    and signal those PIDs individually too.
    """
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        pgid = None

    descendants = _descendant_pids(proc.pid)

    log_f.write(
        f"\n!!!!! TIMEOUT: wall-clock limit exceeded, sending SIGTERM to pgid={pgid} "
        f"and {len(descendants)} descendant process(es) {descendants} !!!!!\n"
    )
    log_f.flush()
    if pgid is not None:
        _signal_group(pgid, signal.SIGTERM)
    _signal_pids(descendants, signal.SIGTERM)

    try:
        proc.wait(timeout=SIGTERM_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass

    survivors = [p for p in descendants if _pid_alive(p)]
    if not survivors and proc.returncode is not None:
        return

    log_f.write(
        f"\n!!!!! TIMEOUT: codex and/or descendant process(es) {survivors} survived "
        f"the {SIGTERM_GRACE_SECONDS}s SIGTERM grace period, sending SIGKILL !!!!!\n"
    )
    log_f.flush()
    if pgid is not None:
        _signal_group(pgid, signal.SIGKILL)
    _signal_pids(survivors, signal.SIGKILL)
    try:
        proc.wait(timeout=SIGTERM_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass  # nothing more we can do; returncode may stay None -> caller sees -9


def _signal_group(pgid: int, sig: int) -> None:
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


def _signal_pids(pids: list[int], sig: int) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just owned by someone else


def _descendant_pids(root_pid: int) -> list[int]:
    """All descendant PIDs of root_pid, any depth, via `ps` (no /proc on macOS)."""
    try:
        out = subprocess.run(
            ["ps", "-Ao", "pid=,ppid="], capture_output=True, text=True, timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    children: dict[int, list[int]] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        children.setdefault(ppid, []).append(pid)

    result: list[int] = []
    frontier = [root_pid]
    while frontier:
        kids = children.get(frontier.pop(), [])
        result.extend(kids)
        frontier.extend(kids)
    return result


def _dir_size_mb(path: Path) -> float:
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                total += p.stat().st_size
        except OSError:
            continue
    return total / (1024 * 1024)


def _warn_if_over_quota(workspace: Path, cfg: Config, log_f) -> None:
    """Log a loud warning if the workspace exceeds its disk quota. Never deletes anything."""
    quota_mb = cfg.limits.workspace_disk_quota_mb
    if not quota_mb:
        return
    try:
        size_mb = _dir_size_mb(workspace)
    except OSError as e:
        log_f.write(f"\n!!!!! WARNING: disk quota check failed: {e} !!!!!\n")
        return
    if size_mb > quota_mb:
        log_f.write(
            f"\n!!!!! WARNING: workspace {workspace} is {size_mb:.0f}MB, "
            f"exceeding the {quota_mb}MB disk quota. Nothing deleted automatically; "
            f"investigate manually. !!!!!\n"
        )
