"""Stage 4 — Experiment design.

sol turns the chosen hypothesis into a concrete ExperimentDesign that the codex
coding agent can implement: protocol, metrics, a time budget clamped to the
config ceiling, and expected outcomes both ways. Pure-computational only (code +
public data, deterministic seeds, Apple-Silicon Mac, no runtime internet beyond
pip install).

This stage doubles as the *revision* step: when the pipeline loops back here
after a broken/inconclusive analysis, the latest iteration's notes are folded
into the prompt so the redesign fixes what went wrong.
"""
from __future__ import annotations

from ..config import Config
from ..llm import LLM
from ..state import ExperimentDesign, ProjectState
from . import load_prompt


def _chosen_statement(state: ProjectState) -> tuple[str, str]:
    chosen = next((h for h in state.hypotheses if h.chosen), None)
    if chosen:
        return chosen.statement, chosen.rationale
    return state.topic, ""


def run(state: ProjectState, cfg: Config, llm: LLM) -> ProjectState:
    statement, rationale = _chosen_statement(state)
    ceiling = cfg.limits.experiment_timeout_minutes

    revision = ""
    prior = [it for it in state.iterations if it.notes]
    if prior:
        last = prior[-1]
        revision = (
            f"This is a REVISION. The previous experiment attempt returned "
            f"'{last.verdict.value}'. Analyst notes / required fixes:\n{last.notes}\n"
            "Produce a corrected, more robust design that directly addresses these."
        )

    prompt = load_prompt(
        cfg, "design",
        topic=state.topic, hypothesis=statement, rationale=rationale or "(none)",
        budget=ceiling, revision=revision or "(this is the first design)",
    )
    data = llm.chat_json("reasoning", prompt, stage="design")
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        data = {}

    try:
        budget = int(data.get("time_budget_minutes", ceiling))
    except (TypeError, ValueError):
        budget = ceiling
    budget = max(1, min(budget, ceiling))

    metrics = data.get("metrics", [])
    if isinstance(metrics, str):
        metrics = [metrics]
    metrics = [str(m).strip() for m in metrics if str(m).strip()] if isinstance(metrics, list) else []

    design = ExperimentDesign(
        summary=str(data.get("summary", statement)).strip(),
        protocol=str(data.get("protocol", "")).strip(),
        metrics=metrics,
        time_budget_minutes=budget,
        expected_if_true=str(data.get("expected_if_true", "")).strip(),
        expected_if_false=str(data.get("expected_if_false", "")).strip(),
    )
    state.design = design

    d = state.dir(cfg.root)
    d.mkdir(parents=True, exist_ok=True)
    md = (
        f"# Experiment design: {state.topic}\n\n"
        f"**Hypothesis:** {statement}\n\n"
        f"## Summary\n{design.summary}\n\n"
        f"## Protocol\n{design.protocol}\n\n"
        f"## Metrics\n" + ("".join(f"- {m}\n" for m in design.metrics) or "- (none specified)\n") +
        f"\n## Time budget\n{design.time_budget_minutes} minutes (ceiling {ceiling}).\n\n"
        f"## Expected outcomes\n"
        f"- **If supported:** {design.expected_if_true or '(unspecified)'}\n"
        f"- **If refuted:** {design.expected_if_false or '(unspecified)'}\n"
    )
    (d / "design.md").write_text(md, encoding="utf-8")
    return state
