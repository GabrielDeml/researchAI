"""The science pipeline: drive one project through stages 1-9 with checkpointing.

``run_project`` creates or resumes a ProjectState and advances it through
STAGE_ORDER, saving after every stage. Between stages it honors the STOP
(pause) and SKIP kill switches; a ``Paused`` raised mid-stage (STOP pressed
during an LLM call) is caught, checkpointed, and unwound cleanly — the stage
reruns from its start on resume, so every stage is written to be idempotent.

The implement→analyze iteration loop lives here: after an analysis that is
broken or inconclusive, and while under ``max_iterations``, the pipeline loops
back to DESIGN (which folds the analyst's revision notes into a corrected design)
and re-runs the experiment.

Nothing runs at import time; ``run_project`` is the only entry point (plus the
re-exported ``propose_topic`` for the supervisor).
"""
from __future__ import annotations

import sys
import traceback

from .config import Config
from .llm import LLM, Paused
from .state import (
    DONE, FAILED, PAUSED, RUNNING, SKIPPED, STAGE_ORDER,
    ProjectState, Stage, Verdict, slugify,
)
from .stages import analyze, archive, design, ideate, implement, review, survey, writeup
from .stages.intake import propose_topic, run as intake_run

__all__ = ["run_project", "propose_topic"]

_STAGE_FUNCS = {
    Stage.INTAKE: intake_run,
    Stage.SURVEY: survey.run,
    Stage.IDEATE: ideate.run,
    Stage.DESIGN: design.run,
    Stage.IMPLEMENT: implement.run,
    Stage.ANALYZE: analyze.run,
    Stage.WRITEUP: writeup.run,
    Stage.REVIEW: review.run,
    Stage.ARCHIVE: archive.run,
}

_REVISION_VERDICTS = {Verdict.BROKEN, Verdict.INCONCLUSIVE}


def _log(msg: str) -> None:
    print(f"[pipeline] {msg}", file=sys.stderr, flush=True)


def _next_stage(state: ProjectState, cfg: Config) -> Stage:
    """Compute the stage to run after the one that just completed, including the
    analyze→design revision back-edge and the iteration cap."""
    s = state.stage
    if s == Stage.ANALYZE:
        if state.verdict in _REVISION_VERDICTS and len(state.iterations) < cfg.limits.max_iterations:
            _log(f"verdict={state.verdict.value}; looping back to redesign "
                 f"(iteration {len(state.iterations)}/{cfg.limits.max_iterations})")
            return Stage.DESIGN
        return Stage.WRITEUP
    idx = STAGE_ORDER.index(s)
    return STAGE_ORDER[idx + 1] if idx + 1 < len(STAGE_ORDER) else Stage.DONE


def _mark_completed(state: ProjectState, stage: Stage) -> None:
    if stage not in state.completed_stages:
        state.completed_stages.append(stage)


def _create_state(cfg: Config, topic: str) -> ProjectState:
    slug = slugify(topic)
    # Disambiguate if a project with this slug already exists on disk.
    base, n = slug, 2
    while (cfg.projects_dir / slug / "state.json").exists():
        slug = f"{base}-{n}"
        n += 1
    state = ProjectState(slug=slug, topic=topic)
    state.save(cfg.root)
    return state


def run_project(
    cfg: Config, topic: str | None = None, resume_slug: str | None = None,
) -> ProjectState:
    """Run (or resume) one research project through the full pipeline.

    Returns the final ProjectState with status one of done / paused / skipped /
    failed. Never raises for expected control flow (STOP/SKIP/Paused/stage error);
    unexpected stage errors are captured on ``state.error`` with status=failed.
    """
    if resume_slug:
        state = ProjectState.load(cfg.root, resume_slug)
        _log(f"resuming '{state.slug}' at stage {state.stage.value}")
    elif topic:
        state = _create_state(cfg, topic)
        _log(f"starting '{state.slug}': {topic}")
    else:
        raise ValueError("run_project requires either a topic or a resume_slug")

    state.status = RUNNING
    state.error = ""
    state.save(cfg.root)
    llm = LLM(cfg, project=state.slug)

    while state.stage != Stage.DONE:
        stage = state.stage

        # --- stage-boundary kill switches -----------------------------------
        if cfg.stop_file.exists():
            _log("STOP present — pausing at stage boundary")
            state.status = PAUSED
            state.save(cfg.root)
            return state
        if cfg.skip_file.exists():
            _log("SKIP present — skipping project")
            state.status = SKIPPED
            state.save(cfg.root)
            try:
                cfg.skip_file.unlink()
            except FileNotFoundError:
                pass
            return state

        _log(f"stage: {stage.value}")
        try:
            state = _STAGE_FUNCS[stage](state, cfg, llm)
        except Paused:
            _log(f"paused during {stage.value} — checkpointing")
            state.status = PAUSED
            state.save(cfg.root)
            return state
        except Exception as e:  # noqa: BLE001 — surface, don't crash the supervisor
            _log(f"stage {stage.value} FAILED: {e}")
            traceback.print_exc(file=sys.stderr)
            state.status = FAILED
            state.error = f"{stage.value}: {e}"
            state.save(cfg.root)
            return state

        _mark_completed(state, stage)
        state.stage = _next_stage(state, cfg)
        state.save(cfg.root)

    state.status = DONE
    state.save(cfg.root)
    _log(f"done '{state.slug}': verdict={state.verdict.value} "
         f"score={state.reviewer_score}")
    return state
