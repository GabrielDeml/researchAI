"""Singleton runner lock: at most one pipeline-executing process per repo root.

`run`, `drain`, and `supervise` all acquire this before doing any work. Without
it, a second runner sees in-flight projects (status=running) as crashed and
"resumes" them concurrently — double-running stages and racing on state.json
(this actually happened: a manual `drain` grabbed a live project mid-writeup).

flock releases automatically when the process exits — including SIGKILL — so a
crashed runner never wedges the lock. The dashboard (`serve`) is read-mostly and
deliberately not covered.
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import IO


class RunnerActive(RuntimeError):
    pass


def acquire_runner_lock(root: Path) -> IO[str]:
    """Take the exclusive runner lock or raise RunnerActive.

    The caller must keep the returned file object alive for the lifetime of the
    process (dropping it releases the lock)."""
    path = root / ".runner.lock"
    f = path.open("w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        raise RunnerActive(
            "another harness runner (run/drain/supervise) is already active in "
            f"{root}; refusing to start a second one"
        ) from None
    f.write(str(os.getpid()))
    f.flush()
    return f
