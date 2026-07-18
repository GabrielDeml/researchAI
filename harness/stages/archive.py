"""Stage 9 — Archive.

Writes the compressed lessons-learned entry to the journal, appends every
hypothesis + outcome to the ideas ledger, enqueues up to two follow-up questions
as new topic files, and marks the project DONE. This is the step that makes the
loop compounding rather than episodic.
"""
from __future__ import annotations

import json
import re

from .. import journal
from ..config import Config
from ..llm import LLM, Paused
from ..state import DONE, ProjectState, slugify
from . import load_prompt


def _key_numbers(state: ProjectState, cfg: Config) -> str:
    path = state.workspace(cfg.root) / "results.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    parts = []
    for k, v in data.items():
        if isinstance(v, (int, float, str, bool)):
            parts.append(f"{k}={v}")
        if len(parts) >= 8:
            break
    return "; ".join(parts)


def _lessons(state: ProjectState, cfg: Config, llm: LLM) -> str:
    """A short 'what I'd do differently'. Uses luna, degrading to iteration notes."""
    notes = state.iterations[-1].notes if state.iterations else ""
    try:
        return llm.chat(
            "utility_alt",
            load_prompt(
                cfg, "lessons",
                topic=state.topic, verdict=state.verdict.value,
                notes=notes or "(none)",
                iterations=len(state.iterations),
            ),
            stage="archive",
        ).strip()[:400]
    except Paused:
        raise
    except Exception:
        return (notes[:300] or "Refine the experiment design for a sharper, "
                "more decisive test next time.")


def _follow_ups(state: ProjectState, cfg: Config) -> list[str]:
    """Pull up to two follow-up questions from the report's dedicated section."""
    report = state.dir(cfg.root) / "report.md"
    if not report.exists():
        return []
    text = report.read_text(encoding="utf-8")
    m = re.search(r"#+\s*Follow-?up\s+questions?\s*\n(.+?)(?:\n#+\s|\Z)",
                  text, flags=re.I | re.S)
    if not m:
        return []
    questions = []
    for line in m.group(1).splitlines():
        line = re.sub(r"^\s*[-*\d.\)]+\s*", "", line).strip()
        if len(line) > 15:
            questions.append(line)
    return questions[:2]


def _enqueue(cfg: Config, slug: str, questions: list[str]) -> list[str]:
    cfg.queue_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for i, q in enumerate(questions, 1):
        name = f"auto-{slugify(slug + '-' + q, 56)}.md"
        path = cfg.queue_dir / name
        if path.exists():
            continue
        path.write_text(f"# Topic\n\n{q}\n\n_(auto-enqueued follow-up from {slug})_\n",
                        encoding="utf-8")
        written.append(name)
    return written


def run(state: ProjectState, cfg: Config, llm: LLM) -> ProjectState:
    chosen = next((h for h in state.hypotheses if h.chosen), None)
    if chosen:
        chosen.outcome = state.verdict

    journal.append_entry(
        cfg,
        project=state.slug,
        topic=state.topic,
        hypothesis=(chosen.statement if chosen else ""),
        verdict=state.verdict.value,
        key_numbers=_key_numbers(state, cfg),
        lessons=_lessons(state, cfg, llm),
    )
    journal.append_ideas(cfg, state.slug, state.hypotheses)
    _enqueue(cfg, state.slug, _follow_ups(state, cfg))

    state.status = DONE
    return state
