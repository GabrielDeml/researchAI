"""The 24/7 supervisor loop: pop queue -> run one project -> digest -> repeat.

Runs under launchd (`KeepAlive=true`) via `python -m harness supervise`, but
behaves identically run by hand. This module owns none of the research logic
-- that lives in harness.pipeline and harness.journal, which are imported
lazily (inside functions, not at module scope) both because they're built in
parallel with this file and so tests can monkeypatch
`harness.pipeline.run_project` / `propose_topic` and
`harness.journal.write_digest` regardless of when this module was imported.

The supervisor itself must never die from a project failure: every exception
raised while doing work is caught, logged loudly, and the loop continues.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

from .config import Config, load_config
from .state import FAILED, PAUSED, RUNNING, ProjectState

# Brief backoff after an unexpected exception in a cycle, distinct from the
# configured idle_sleep_seconds used when there's genuinely no work to do.
CYCLE_ERROR_BACKOFF_SECONDS = 5


def _setup_logging(cfg: Config) -> logging.Logger:
    """Line-buffered, human-readable logging to both stdout and cfg.supervisor_log."""
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("researchai.supervisor")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()  # main() may be called more than once per process (tests)
    logger.propagate = False
    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z"
    )
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)
    file_handler = logging.FileHandler(cfg.supervisor_log, mode="a")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    return logger


def _heartbeat_loop(cfg: Config, log: logging.Logger, stop_event: threading.Event) -> None:
    """Touch cfg.heartbeat_file on its own thread so it keeps ticking while a
    project (and its blocking codex/LLM calls) run on the main thread."""
    while not stop_event.is_set():
        try:
            cfg.heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
            cfg.heartbeat_file.touch()
        except OSError:
            log.exception("failed to touch heartbeat file %s", cfg.heartbeat_file)
        stop_event.wait(timeout=cfg.supervisor.heartbeat_seconds)


def _check_health(cfg: Config) -> bool:
    try:
        resp = httpx.get(
            f"{cfg.proxy.base_url}/models",
            headers={"Authorization": f"Bearer {cfg.proxy.api_key}"},
            timeout=10.0,
        )
        return resp.status_code < 400
    except httpx.HTTPError:
        return False


def _pick_resume_target(cfg: Config) -> ProjectState | None:
    """Oldest project left mid-run after a crash/restart: status running, or
    paused (only once STOP has been lifted -- caller guarantees that here)."""
    eligible = [
        p for p in ProjectState.load_all(cfg.root)
        if p.status == RUNNING or (p.status == PAUSED and not cfg.stop_file.exists())
    ]
    eligible.sort(key=lambda p: p.created_at)
    return eligible[0] if eligible else None


def _pop_queue_file(cfg: Config) -> Path | None:
    files = sorted(cfg.queue_dir.glob("*.md"))
    return files[0] if files else None


def _ack_queue_file(cfg: Config, queue_file: Path, state, log: logging.Logger) -> None:
    """Acknowledge a queue item based on how its run actually ended.

    done/skipped: work is finished, remove the file. paused: the project persists
    in projects/ and resumes from state.json, so the file is also safe to remove.
    failed: move to queue/failed/ (a dead-letter dir the queue scan ignores) so a
    transient model/codex/filesystem error never silently discards the request —
    move it back into queue/ to retry."""
    try:
        if getattr(state, "status", FAILED) == FAILED:
            dead_dir = cfg.queue_dir / "failed"
            dead_dir.mkdir(parents=True, exist_ok=True)
            dest = dead_dir / queue_file.name
            queue_file.rename(dest)
            log.error(
                "project %r FAILED (%s); queue item moved to %s for retry",
                getattr(state, "slug", "?"), getattr(state, "error", ""), dest,
            )
        else:
            queue_file.unlink()
    except OSError:
        log.exception("failed to acknowledge queue file %s", queue_file)


def _disk_ok(cfg: Config, log: logging.Logger) -> bool:
    """Fail closed when the volume is nearly full: no new work below the floor."""
    min_free = cfg.limits.min_free_disk_gb * 1024 ** 3
    if not min_free:
        return True
    try:
        free = shutil.disk_usage(cfg.root).free
    except OSError:
        log.exception("free-disk check failed; failing closed")
        return False
    if free < min_free:
        log.error(
            "!!! free disk %.1fGB is below the %dGB floor; no new work will start !!!",
            free / 1024 ** 3, cfg.limits.min_free_disk_gb,
        )
        return False
    return True


def _budget_blocked(cfg: Config) -> str | None:
    """Return a reason string when a configured daily cap is exhausted.

    All caps default to 0 = unlimited (per this project's model policy quota is
    not rationed); when a cap is set, it is enforced here — before work starts."""
    lim = cfg.limits
    today = dt.date.today().isoformat()

    if lim.max_projects_per_day:
        started = sum(
            1 for p in ProjectState.load_all(cfg.root) if p.created_at[:10] == today
        )
        if started >= lim.max_projects_per_day:
            return f"max_projects_per_day={lim.max_projects_per_day} reached"

    if lim.daily_max_requests or lim.daily_max_tokens:
        requests = tokens = 0
        if cfg.usage_log.exists():
            for line in cfg.usage_log.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if str(rec.get("ts", ""))[:10] == today:
                    requests += 1
                    tokens += int(rec.get("total_tokens", 0) or 0)
        if lim.daily_max_requests and requests >= lim.daily_max_requests:
            return f"daily_max_requests={lim.daily_max_requests} reached ({requests})"
        if lim.daily_max_tokens and tokens >= lim.daily_max_tokens:
            return f"daily_max_tokens={lim.daily_max_tokens} reached ({tokens})"
    return None


def _write_digest(cfg: Config, log: logging.Logger) -> None:
    try:
        from . import journal
        path = journal.write_digest(cfg)
        log.info("digest written: %s", path)
    except Exception:
        log.exception("!!! journal digest generation failed !!!")


def _publish_results(cfg: Config, log: logging.Logger) -> None:
    """Commit+push research outputs to the results branch after each project.

    Uses the dedicated .results-worktree so the harness's own working tree is
    never touched. Copies exclude experiment venvs. Any failure (offline, auth,
    missing worktree) is logged loudly and the loop continues — publishing is
    best-effort, never load-bearing."""
    if not cfg.results.publish:
        return
    wt = cfg.root / ".results-worktree"
    if not (wt / ".git").exists():
        log.warning("results.publish enabled but %s missing; "
                    "run scripts/setup_results_branch.sh", wt)
        return
    try:
        patterns = shutil.ignore_patterns(
            ".venv", "venv", "__pycache__", ".git", "node_modules",
            ".podman-data", ".docker", ".cache", "archived-*",
        )

        def ignore(src: str, names: list[str]) -> set[str]:
            # Also skip anything GitHub would reject (hard limit 100MB) — one
            # oversized workspace artifact otherwise wedges every future push.
            skip = set(patterns(src, names))
            for n in names:
                if n in skip:
                    continue
                p = os.path.join(src, n)
                if os.path.isfile(p) and os.path.getsize(p) > 95 * 1024 * 1024:
                    log.warning("results publish: skipping oversized file %s", p)
                    skip.add(n)
            return skip

        for name in ("projects", "journal", "digests"):
            src = cfg.root / name
            if src.exists():
                dest = wt / name
                shutil.rmtree(dest, ignore_errors=True)
                shutil.copytree(src, dest, ignore=ignore)

        def _git(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git", "-C", str(wt), *args],
                capture_output=True, text=True, timeout=180,
            )

        _git("add", "-A")
        if _git("diff", "--cached", "--quiet").returncode == 0:
            return  # nothing new
        stamp = dt.datetime.now().isoformat(timespec="seconds")
        commit = _git("commit", "-m", f"results: {stamp}")
        if commit.returncode != 0:
            log.error("results commit failed: %s", commit.stderr.strip()[:400])
            return
        push = _git("push", "origin", cfg.results.branch)
        if push.returncode != 0:
            log.error("!!! results push failed (will retry after next project): %s !!!",
                      push.stderr.strip()[:400])
        else:
            log.info("results published to origin/%s", cfg.results.branch)
    except Exception:
        log.exception("!!! results publishing failed !!!")


def _reexec(log: logging.Logger, drain: bool) -> None:
    """Replace this process with a fresh supervisor so just-merged code takes
    effect. Python file descriptors are close-on-exec, so the runner flock
    releases at exec and the successor immediately re-acquires it."""
    mode = "drain" if drain else "supervise"
    log.info("re-exec: %s -m harness %s", sys.executable, mode)
    os.execv(sys.executable, [sys.executable, "-m", "harness", mode])


def _maybe_self_update(cfg: Config, log: logging.Logger, drain: bool) -> None:
    """ff-only pull from origin; on new code, re-exec (does not return then)."""
    try:
        from . import self_improve
        if self_improve.maybe_pull_update(cfg, log):
            log.info("harness updated from origin; restarting to load new code")
            _reexec(log, drain)
    except Exception:
        log.exception("!!! self-update check failed !!!")


def _maybe_self_improve(cfg: Config, log: logging.Logger, drain: bool) -> None:
    """Cadence-gated self-improvement after a project; on an applied change,
    re-exec (does not return then)."""
    try:
        from . import self_improve
        if self_improve.maybe_run(cfg, log):
            log.info("self-improvement applied; restarting to load new code")
            _reexec(log, drain)
    except Exception:
        log.exception("!!! self-improvement cycle failed !!!")


def _run_one_unit_of_work(
    cfg: Config, log: logging.Logger, allow_auto_topics: bool = True,
) -> bool:
    """Do at most one unit of work (resume a crashed project, pop the queue,
    or self-ideate). Returns True if a project ran, False if there was
    nothing to do (caller should idle-sleep)."""
    from . import pipeline

    resume_target = _pick_resume_target(cfg)
    if resume_target is not None:
        log.info(
            "resuming project %r (status=%s) after crash/restart",
            resume_target.slug, resume_target.status,
        )
        try:
            pipeline.run_project(cfg, resume_slug=resume_target.slug)
        finally:
            _write_digest(cfg, log)
            _publish_results(cfg, log)
        return True

    queue_file = _pop_queue_file(cfg)
    if queue_file is not None:
        topic = queue_file.read_text()
        log.info("starting project from queue file %s", queue_file.name)
        try:
            state = pipeline.run_project(cfg, topic=topic)
        finally:
            _write_digest(cfg, log)
            _publish_results(cfg, log)
        _ack_queue_file(cfg, queue_file, state, log)
        return True

    if cfg.supervisor.auto_topics and allow_auto_topics:
        log.info("queue empty; self-ideating a topic")
        topic = pipeline.propose_topic(cfg)
        log.info("proposed topic: %s", topic)
        try:
            pipeline.run_project(cfg, topic=topic)
        finally:
            _write_digest(cfg, log)
            _publish_results(cfg, log)
        return True

    log.info("queue empty%s; idling",
             "" if cfg.supervisor.auto_topics else " and auto_topics disabled")
    return False


def main(max_cycles: int | None = None, drain: bool = False) -> None:
    """Run the supervisor loop. `max_cycles` (or env RESEARCHAI_MAX_CYCLES)
    caps the number of loop iterations -- for tests; unset means forever.

    `drain=True` is the no-daemon mode (`python -m harness drain`): resume any
    crashed projects, work through the queue, then exit instead of idling —
    self-ideation is skipped so the process always terminates. Do not run it
    while another `harness run`/`supervise` process is active: two runners
    would both pick up the same in-flight project."""
    cfg = load_config()
    log = _setup_logging(cfg)

    from .lockfile import RunnerActive, acquire_runner_lock
    try:
        runner_lock = acquire_runner_lock(cfg.root)  # noqa: F841 — held for process lifetime
    except RunnerActive as e:
        log.error("%s", e)
        return

    if max_cycles is None:
        env_val = os.environ.get("RESEARCHAI_MAX_CYCLES")
        max_cycles = int(env_val) if env_val else None

    shutdown_event = threading.Event()

    def _handle_signal(signum, _frame):
        log.info("received signal %s; shutting down after current step", signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    def _sleep(seconds: float) -> None:
        shutdown_event.wait(timeout=seconds)

    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop, args=(cfg, log, shutdown_event),
        daemon=True, name="researchai-heartbeat",
    )
    heartbeat_thread.start()

    log.info("supervisor starting (root=%s, drain=%s)", cfg.root, drain)

    stop_logged = False
    cycle = 0
    try:
        while not shutdown_event.is_set():
            cycle += 1

            if cfg.stop_file.exists():
                if drain:
                    log.warning("STOP file present; drain exiting (remove STOP and rerun)")
                    break
                if not stop_logged:
                    log.warning(
                        "STOP file present at %s; pausing, no new work will start",
                        cfg.stop_file,
                    )
                    stop_logged = True
                _sleep(cfg.supervisor.idle_sleep_seconds)
            else:
                if stop_logged:
                    log.info("STOP file removed; resuming")
                    stop_logged = False

                _maybe_self_update(cfg, log, drain)

                budget_reason = _budget_blocked(cfg)
                if not _disk_ok(cfg, log):
                    if drain:
                        log.error("drain exiting: below free-disk floor")
                        break
                    _sleep(cfg.supervisor.idle_sleep_seconds)
                elif budget_reason is not None:
                    log.warning("daily budget exhausted (%s); %s",
                                budget_reason, "drain exiting" if drain else "idling")
                    if drain:
                        break
                    _sleep(cfg.supervisor.idle_sleep_seconds)
                elif not _check_health(cfg):
                    log.error(
                        "!!! proxy health check failed (%s/models unreachable or erroring) !!!",
                        cfg.proxy.base_url,
                    )
                    if drain:
                        log.error("drain exiting: proxy unhealthy")
                        break
                    _sleep(cfg.supervisor.idle_sleep_seconds)
                else:
                    try:
                        did_work = _run_one_unit_of_work(
                            cfg, log, allow_auto_topics=not drain,
                        )
                    except Exception:
                        log.exception("!!! unhandled exception in supervisor cycle !!!")
                        _sleep(CYCLE_ERROR_BACKOFF_SECONDS)
                    else:
                        if did_work:
                            _maybe_self_improve(cfg, log, drain)
                            _sleep(0 if drain else cfg.supervisor.project_cooldown_seconds)
                        elif drain:
                            log.info("queue drained; exiting")
                            break
                        else:
                            _sleep(cfg.supervisor.idle_sleep_seconds)

            if max_cycles is not None and cycle >= max_cycles:
                log.info("max_cycles=%s reached; stopping", max_cycles)
                break
    finally:
        shutdown_event.set()
        log.info("supervisor stopped")


if __name__ == "__main__":
    main()
