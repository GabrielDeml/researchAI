"""Self-improvement and self-update: the harness maintains its own code.

Two capabilities, both driven from the supervisor loop:

* **Self-improvement** (``maybe_run`` / ``run_improvement``): every
  ``self_improve.every_n_projects`` finished projects, the coding model (codex)
  is pointed at a fresh git worktree of this repo (`.self-improve-worktree`, on
  a ``self-improve/<ts>`` branch) with an evidence pack -- supervisor
  warnings/errors, project verdicts and reviewer scores, dead-lettered queue
  items, journal tail, and past attempts so it never repeats itself -- and
  asked for exactly ONE small improvement. The change is adopted only if it
  (a) touches no protected path and (b) passes the offline ``harness.selfcheck``
  gate. Mode "apply" then fast-forwards the running branch (the supervisor
  re-execs so the new code takes effect); mode "propose" leaves the branch for
  human review. Every attempt lands in logs/self_improve.jsonl and
  journal/improvements.md.

* **Self-update** (``maybe_pull_update``): periodically fast-forward the
  current branch from origin so a deployed harness picks up code pushed from
  elsewhere; the supervisor re-execs after a successful pull.

Safety posture: user work always wins -- a dirty tree skips the attempt and a
non-fast-forward merge downgrades to a proposal, never an overwrite. The gate
and this module are themselves protected paths, so an improvement can never
weaken the guardrails that admitted it. STOP pauses this like all other work.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .config import Config
from .state import DONE, FAILED, SKIPPED, ProjectState

# Attempt outcomes recorded in logs/self_improve.jsonl.
APPLIED = "applied"        # merged into the running branch; caller should restart
PROPOSED = "proposed"      # left on a self-improve/<ts> branch for human review
REJECTED = "rejected"      # touched a protected path; discarded
GATE_FAILED = "gate-failed"  # selfcheck failed on the changed code; discarded
NO_CHANGE = "no-change"    # model found nothing worthwhile (honest no-op)
SKIPPED_RUN = "skipped"    # preconditions not met (dirty tree, not a repo)
ERROR = "error"            # codex/git failure; discarded

SUMMARY_FILE = "SELF_IMPROVE_SUMMARY.md"
GATE_TIMEOUT_SECONDS = 900
TERMINAL_STATUSES = {DONE, FAILED, SKIPPED}

_last_pull_check: float = 0.0  # monotonic; per-process (a restart re-checks at boot)


def _git(cwd: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=timeout,
    )


def _tree_clean(root: Path) -> bool:
    """Tracked files unmodified (untracked runtime state like projects/ is fine)."""
    return (
        _git(root, "diff", "--quiet").returncode == 0
        and _git(root, "diff", "--cached", "--quiet").returncode == 0
    )


def _tail_text(path: Path, max_bytes: int = 262144) -> str:
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


# --------------------------------------------------------------------------
# attempt history (cadence + "don't repeat yourself" evidence)

def _history(cfg: Config) -> list[dict]:
    if not cfg.self_improve_history.exists():
        return []
    recs = []
    for line in cfg.self_improve_history.read_text(encoding="utf-8").splitlines():
        try:
            recs.append(json.loads(line))
        except ValueError:
            continue
    return recs


def _record(cfg: Config, log: logging.Logger, **rec: object) -> None:
    rec.setdefault("ts", dt.datetime.now().isoformat(timespec="seconds"))
    try:
        cfg.logs_dir.mkdir(parents=True, exist_ok=True)
        with cfg.self_improve_history.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        log.exception("failed to append %s", cfg.self_improve_history)
    try:
        cfg.journal_dir.mkdir(parents=True, exist_ok=True)
        with cfg.improvements_log.open("a", encoding="utf-8") as f:
            f.write(f"\n## {rec['ts']} — {rec['result']}: "
                    f"{rec.get('subject') or '(no subject)'}\n")
            if rec.get("branch"):
                f.write(f"- branch: {rec['branch']}\n")
            if rec.get("files"):
                f.write(f"- files: {', '.join(rec['files'])}\n")  # type: ignore[arg-type]
            if rec.get("detail"):
                f.write(f"- detail: {rec['detail']}\n")
    except OSError:
        log.exception("failed to append %s", cfg.improvements_log)


def _finished_projects(cfg: Config) -> int:
    return sum(
        1 for p in ProjectState.load_all(cfg.root) if p.status in TERMINAL_STATUSES
    )


def _due(cfg: Config) -> bool:
    every = cfg.self_improve.every_n_projects
    if every <= 0:
        return False
    finished = _finished_projects(cfg)
    hist = _history(cfg)
    baseline = int(hist[-1].get("projects_finished", 0)) if hist else 0
    if finished < baseline:  # projects were deleted; don't stall forever
        baseline = 0
    return finished - baseline >= every


def _attempts_today(cfg: Config) -> int:
    today = dt.date.today().isoformat()
    return sum(1 for r in _history(cfg) if str(r.get("ts", ""))[:10] == today)


# --------------------------------------------------------------------------
# evidence pack

def gather_evidence(cfg: Config) -> str:
    """Operational evidence the improvement prompt is grounded in. Each section
    is bounded so the pack stays a few KB no matter how long the harness runs."""
    parts: list[str] = []

    states = sorted(ProjectState.load_all(cfg.root), key=lambda p: p.created_at)[-15:]
    if states:
        lines = []
        for p in states:
            line = (f"- {p.slug}: status={p.status} verdict={p.verdict.value} "
                    f"reviewer_score={p.reviewer_score} iterations={len(p.iterations)}")
            if p.error:
                line += f" error={p.error[:200]!r}"
            lines.append(line)
        parts.append("### Recent projects (oldest first)\n" + "\n".join(lines))

    if cfg.supervisor_log.exists():
        noisy = [
            l for l in _tail_text(cfg.supervisor_log).splitlines()
            if " WARNING " in l or " ERROR " in l
        ]
        if noisy:
            parts.append("### Supervisor warnings/errors (recent)\n"
                         + "\n".join(noisy[-60:]))

    failed_dir = cfg.queue_dir / "failed"
    dead = sorted(failed_dir.glob("*.md")) if failed_dir.exists() else []
    if dead:
        parts.append("### Dead-lettered queue items (projects that failed)\n"
                     + "\n".join(f"- {p.name}" for p in dead[-20:]))

    journal_md = cfg.journal_dir / "journal.md"
    if journal_md.exists():
        tail = _tail_text(journal_md, 6000).strip()
        if tail:
            parts.append("### Journal tail (lessons learned)\n" + tail[-3000:])

    hist = _history(cfg)[-10:]
    if hist:
        parts.append(
            "### Past self-improvement attempts (do NOT repeat these)\n" + "\n".join(
                f"- {r.get('ts', '?')} [{r.get('result', '?')}] {r.get('subject', '')}"
                + (f" (files: {', '.join(r.get('files', [])[:6])})"
                   if r.get("files") else "")
                for r in hist
            )
        )

    return "\n\n".join(parts) if parts else \
        "(no operational evidence yet — the harness has not run projects)"


# --------------------------------------------------------------------------
# worktree lifecycle

def _fresh_worktree(cfg: Config, log: logging.Logger) -> tuple[Path, str]:
    wt = cfg.self_improve_worktree
    if wt.exists():
        # Successful attempts always clean up, so this is a crashed attempt.
        log.warning("self-improve: removing stale worktree %s", wt)
        _discard_worktree_dir(cfg)
    branch = "self-improve/" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    res = _git(cfg.root, "worktree", "add", "-b", branch, str(wt), "HEAD")
    if res.returncode != 0:
        raise RuntimeError(f"git worktree add failed: {res.stderr.strip()[:300]}")
    return wt, branch


def _discard_worktree_dir(cfg: Config) -> None:
    _git(cfg.root, "worktree", "remove", "--force", str(cfg.self_improve_worktree))
    shutil.rmtree(cfg.self_improve_worktree, ignore_errors=True)
    _git(cfg.root, "worktree", "prune")


def _discard_attempt(cfg: Config, branch: str) -> None:
    _discard_worktree_dir(cfg)
    _git(cfg.root, "branch", "-D", branch)


def _changed_files(wt: Path) -> list[str]:
    """All paths touched in the worktree (renames contribute both sides)."""
    out = _git(wt, "status", "--porcelain=v1", "-z").stdout
    entries = out.split("\0")
    files: list[str] = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if not entry:
            continue
        files.append(entry[3:])
        if entry[0] in "RC":  # rename/copy: the next NUL entry is the source path
            files.append(entries[i])
            i += 1
    return [f for f in files if f]


def _protected_violations(files: list[str], protected: list[str]) -> list[str]:
    bad = []
    for f in files:
        for p in protected:
            p = p.rstrip("/")
            if f == p or f.startswith(p + "/"):
                bad.append(f)
                break
    return bad


def _run_gate(cfg: Config, wt: Path, deps_changed: bool) -> tuple[bool, str]:
    """Run harness.selfcheck against the *worktree's* code. `python -m` puts the
    cwd first on sys.path, so the worktree copy of harness/ is what gets
    imported even under the root venv's interpreter; a dependency change
    instead goes through `uv run` so the new deps are actually installed."""
    if deps_changed:
        uv = shutil.which("uv") or "/opt/homebrew/bin/uv"
        cmd = [uv, "run", "--directory", str(wt), "python", "-m", "harness", "selfcheck"]
    else:
        cmd = [sys.executable, "-m", "harness", "selfcheck"]
    env = {**os.environ, "RESEARCHAI_ROOT": str(wt)}
    try:
        proc = subprocess.run(
            cmd, cwd=str(wt), env=env, capture_output=True, text=True,
            timeout=GATE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"selfcheck did not run: {e}"
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()[-2000:]


# --------------------------------------------------------------------------
# the attempt itself

def run_improvement(
    cfg: Config, log: logging.Logger, mode: str | None = None,
) -> str:
    """One self-improvement attempt; returns an outcome constant (APPLIED,
    PROPOSED, REJECTED, GATE_FAILED, NO_CHANGE, SKIPPED_RUN, ERROR). Never
    raises — the supervisor treats this as best-effort side work."""
    # Lazy imports: same convention as the pipeline (tests monkeypatch run_codex).
    from .codex_runner import run_codex
    from .stages import load_prompt

    si = cfg.self_improve
    mode = mode or si.mode
    start = time.monotonic()

    if _git(cfg.root, "rev-parse", "--git-dir").returncode != 0:
        log.error("self-improve: %s is not a git repo; skipping", cfg.root)
        return SKIPPED_RUN
    if not _tree_clean(cfg.root):
        log.warning("self-improve: uncommitted changes in %s; skipping so user "
                    "work is never mixed with generated changes", cfg.root)
        return SKIPPED_RUN

    projects_finished = _finished_projects(cfg)
    try:
        wt, branch = _fresh_worktree(cfg, log)
    except (RuntimeError, OSError, subprocess.SubprocessError) as e:
        log.error("self-improve: could not create worktree: %s", e)
        return ERROR
    log.info("self-improve: attempting on branch %s (mode=%s)", branch, mode)

    def finish(result: str, **kw: object) -> str:
        _record(cfg, log, result=result, branch=branch, mode=mode,
                projects_finished=projects_finished,
                duration_s=round(time.monotonic() - start, 1), **kw)
        return result

    try:
        prompt = load_prompt(
            cfg, "self_improve",
            evidence=gather_evidence(cfg),
            protected=", ".join(si.protected_paths),
            selfcheck_cmd=f"{sys.executable} -m harness selfcheck",
            summary_file=SUMMARY_FILE,
        )
        codex_log = cfg.logs_dir / \
            f"self_improve_{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
        res = run_codex(
            prompt=prompt, workspace=wt, model=cfg.models.roles["coding"],
            timeout_minutes=si.timeout_minutes, log_path=codex_log, cfg=cfg,
        )
        if res.timed_out or res.exit_code != 0:
            log.error("self-improve: codex run failed (exit=%s timed_out=%s); see %s",
                      res.exit_code, res.timed_out, codex_log)
            _discard_attempt(cfg, branch)
            return finish(ERROR,
                          detail=f"codex exit={res.exit_code} timed_out={res.timed_out}")

        summary_path = wt / SUMMARY_FILE
        summary = summary_path.read_text(encoding="utf-8").strip() \
            if summary_path.exists() else ""
        if summary_path.exists():
            summary_path.unlink()
        summary_lines = [l.strip() for l in summary.splitlines()]
        subject = next((l for l in summary_lines if l), "(no summary provided)")[:72]
        body = summary.partition("\n")[2].strip()

        files = [f for f in _changed_files(wt) if f != SUMMARY_FILE]
        if not files or summary.upper().startswith("NO-CHANGE"):
            log.info("self-improve: no change made (%s)", subject)
            _discard_attempt(cfg, branch)
            return finish(NO_CHANGE, subject=subject,
                          detail="model declined or empty diff")

        violations = _protected_violations(files, si.protected_paths)
        if violations:
            log.error("!!! self-improve: change touches protected path(s) %s; "
                      "REJECTED outright !!!", violations)
            _discard_attempt(cfg, branch)
            return finish(REJECTED, subject=subject, files=files,
                          detail=f"protected paths touched: {violations}")

        deps_changed = any(f in ("pyproject.toml", "uv.lock") for f in files)
        gate_ok, gate_out = _run_gate(cfg, wt, deps_changed)
        if not gate_ok:
            log.error("!!! self-improve: selfcheck gate FAILED; change discarded !!!\n%s",
                      gate_out[-800:])
            _discard_attempt(cfg, branch)
            return finish(GATE_FAILED, subject=subject, files=files,
                          detail=gate_out[-800:])

        _git(wt, "add", "-A")
        msg = subject + (("\n\n" + body) if body else "") + \
            "\n\nAutomated self-improvement (selfcheck gate passed)."
        commit = _git(wt, "commit", "-m", msg)
        if commit.returncode != 0:
            log.error("self-improve: commit failed: %s", commit.stderr.strip()[:300])
            _discard_attempt(cfg, branch)
            return finish(ERROR, subject=subject, files=files,
                          detail="git commit failed: " + commit.stderr.strip()[:200])

        if mode == "propose":
            _discard_worktree_dir(cfg)  # the commit lives on the branch now
            log.warning(
                "self-improve: PROPOSED %r on branch %s — review with "
                "`git diff main...%s`, adopt with `git merge %s`",
                subject, branch, branch, branch,
            )
            return finish(PROPOSED, subject=subject, files=files)

        # mode "apply": fast-forward the running branch; user commits/dirt win.
        ff = _git(cfg.root, "merge", "--ff-only", branch) \
            if _tree_clean(cfg.root) else None
        if ff is None or ff.returncode != 0:
            detail = ("working tree changed during the attempt" if ff is None
                      else ff.stderr.strip()[:300])
            log.warning("self-improve: cannot fast-forward (%s); leaving branch %s "
                        "as a proposal", detail, branch)
            _discard_worktree_dir(cfg)
            return finish(PROPOSED, subject=subject, files=files, detail=detail)

        _discard_worktree_dir(cfg)
        _git(cfg.root, "branch", "-d", branch)
        log.warning("self-improve: APPLIED %r (%d file(s): %s)",
                    subject, len(files), ", ".join(files[:8]))

        if si.push:
            head = _git(cfg.root, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
            push = _git(cfg.root, "push", "origin", head, timeout=180)
            if push.returncode != 0:
                log.error("self-improve: push failed (non-fatal, applied locally): %s",
                          push.stderr.strip()[:300])

        return finish(APPLIED, subject=subject, files=files)

    except Exception as e:  # noqa: BLE001 — never take the supervisor down
        log.exception("!!! self-improve attempt errored; discarding worktree !!!")
        try:
            _discard_attempt(cfg, branch)
        except Exception:
            log.exception("self-improve: cleanup after error also failed")
        return finish(ERROR, detail=str(e)[:300])


def maybe_run(cfg: Config, log: logging.Logger) -> bool:
    """Cadence-gated self-improvement, called by the supervisor after each
    project. Returns True when new code was applied and the caller should
    re-exec to load it."""
    si = cfg.self_improve
    if not si.enabled or cfg.stop_file.exists():
        return False
    if not _due(cfg):
        return False
    if si.max_attempts_per_day and _attempts_today(cfg) >= si.max_attempts_per_day:
        log.warning("self-improve: due, but max_attempts_per_day=%d reached; skipping",
                    si.max_attempts_per_day)
        return False
    return run_improvement(cfg, log) == APPLIED


# --------------------------------------------------------------------------
# self-update from origin

def maybe_pull_update(cfg: Config, log: logging.Logger) -> bool:
    """Fast-forward the current branch from origin (at most once per
    check_minutes). Returns True when HEAD moved — the caller should re-exec."""
    global _last_pull_check
    if not cfg.self_update.pull:
        return False
    now = time.monotonic()
    if _last_pull_check and now - _last_pull_check < cfg.self_update.check_minutes * 60:
        return False
    _last_pull_check = now

    branch = _git(cfg.root, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
    if not branch:
        return False  # detached HEAD; nothing sensible to track
    try:
        fetch = _git(cfg.root, "fetch", "origin", branch, timeout=60)
    except subprocess.TimeoutExpired:
        log.info("self-update: fetch timed out; will retry later")
        return False
    if fetch.returncode != 0:
        log.info("self-update: fetch failed (offline?): %s",
                 fetch.stderr.strip()[:200])
        return False
    behind = _git(cfg.root, "rev-list", "--count", "HEAD..FETCH_HEAD").stdout.strip()
    if behind in ("", "0"):
        return False
    if not _tree_clean(cfg.root):
        log.warning("self-update: origin/%s is %s commit(s) ahead but the tree is "
                    "dirty; not updating", branch, behind)
        return False
    merge = _git(cfg.root, "merge", "--ff-only", "FETCH_HEAD")
    if merge.returncode != 0:
        log.warning("self-update: cannot fast-forward to origin/%s (diverged): %s",
                    branch, merge.stderr.strip()[:200])
        return False
    log.warning("self-update: fast-forwarded %s by %s commit(s) from origin",
                branch, behind)
    return True
