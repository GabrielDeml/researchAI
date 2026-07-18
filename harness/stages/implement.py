"""Stage 5 — Implement + run (delegated to the codex coding agent).

Builds a self-contained prompt from the experiment design plus the workspace
conventions, then calls ``harness.codex_runner.run_codex`` (written by a separate
agent; imported lazily so this module stays importable before it exists). Records
one Iteration entry per codex run. The pipeline drives the implement→analyze loop
and increments iterations; on a mid-stage resume the incomplete last iteration is
reused rather than duplicated.
"""
from __future__ import annotations

from ..config import Config
from ..llm import LLM
from ..state import Iteration, ProjectState, now_iso
from . import load_prompt


def _build_prompt(state: ProjectState, cfg: Config) -> str:
    d = state.design
    metrics = ", ".join(d.metrics) if d and d.metrics else "the metrics implied by the protocol"
    return load_prompt(
        cfg, "implement_codex",
        topic=state.topic,
        summary=(d.summary if d else state.topic),
        protocol=(d.protocol if d else "Design the experiment yourself from the topic."),
        metrics=metrics,
        expected_if_true=(d.expected_if_true if d else ""),
        expected_if_false=(d.expected_if_false if d else ""),
        budget=(d.time_budget_minutes if d else cfg.limits.experiment_timeout_minutes),
    )


def run(state: ProjectState, cfg: Config, llm: LLM) -> ProjectState:
    # Lazy import: codex_runner is delivered by a parallel agent and may not exist
    # at import time. Tests inject a fake module under this name.
    from harness.codex_runner import run_codex

    workspace = state.workspace(cfg.root)
    workspace.mkdir(parents=True, exist_ok=True)
    logs_dir = state.dir(cfg.root) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Reuse a never-completed iteration (resume after a mid-stage pause); else new.
    if state.iterations and not state.iterations[-1].finished_at:
        it = state.iterations[-1]
    else:
        it = Iteration(index=len(state.iterations) + 1, started_at=now_iso())
        state.iterations.append(it)

    log_path = logs_dir / f"codex_iter{it.index}.log"
    prompt = _build_prompt(state, cfg)
    model = cfg.models.roles.get("coding", "gpt-5.6-sol")
    timeout_minutes = state.design.time_budget_minutes if state.design else cfg.limits.experiment_timeout_minutes

    result = run_codex(prompt, workspace, model, timeout_minutes, log_path, cfg)

    it.finished_at = now_iso()
    it.codex_exit = result.exit_code
    it.timed_out = result.timed_out
    return state
