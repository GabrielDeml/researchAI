"""Stage 7 — Write-up.

sol drafts report.md (abstract, background w/ citations, hypothesis, method,
results referencing figures by relative path, limitations, follow-up questions),
then terra does a prose-clarity polish pass that must not add claims or alter any
numbers or citations.
"""
from __future__ import annotations

import json

from ..config import Config
from ..llm import LLM
from ..state import ProjectState
from . import load_prompt


def _results_text(state: ProjectState, cfg: Config) -> str:
    path = state.workspace(cfg.root) / "results.json"
    if not path.exists():
        return "(no results.json was produced)"
    raw = path.read_text(encoding="utf-8")
    try:
        return json.dumps(json.loads(raw), indent=2)[:6000]
    except ValueError:
        return raw[:3000]


def _figures(state: ProjectState, cfg: Config) -> list[str]:
    fdir = state.workspace(cfg.root) / "figures"
    if not fdir.exists():
        return []
    return [f"workspace/figures/{p.name}" for p in sorted(fdir.glob("*.png"))]


def _citations_block(state: ProjectState) -> str:
    if not state.citations:
        return "(no external citations were gathered)"
    lines = []
    for i, c in enumerate(state.citations, 1):
        authors = ", ".join(c.authors[:3]) + (" et al." if len(c.authors) > 3 else "")
        lines.append(f"[{i}] {authors or 'Unknown'} ({c.year or 'n.d.'}). {c.title}. {c.url}")
    return "\n".join(lines)


def run(state: ProjectState, cfg: Config, llm: LLM) -> ProjectState:
    chosen = next((h for h in state.hypotheses if h.chosen), None)
    figures = _figures(state, cfg)
    figures_note = (
        "Figures available (embed each with markdown image syntax and discuss it):\n"
        + "\n".join(f"- {f}" for f in figures)
    ) if figures else "No figures were produced; do not invent any."

    draft_prompt = load_prompt(
        cfg, "writeup",
        topic=state.topic,
        hypothesis=(chosen.statement if chosen else state.topic),
        verdict=state.verdict.value,
        design=(state.design.protocol if state.design else "(no design on record)"),
        results=_results_text(state, cfg),
        figures=figures_note,
        citations=_citations_block(state),
    )
    draft = llm.chat("reasoning", draft_prompt, stage="writeup").strip()

    # Prose-only polish; instructed to preserve every number and citation.
    try:
        polished = llm.chat(
            "polish",
            load_prompt(cfg, "polish", document=draft),
            stage="writeup",
        ).strip()
        # Guard against a polish pass that collapses or truncates the report.
        report = polished if len(polished) >= 0.6 * len(draft) else draft
    except Exception:
        report = draft

    d = state.dir(cfg.root)
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.md").write_text(report + "\n", encoding="utf-8")
    state.report_path = "report.md"
    return state
