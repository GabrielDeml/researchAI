"""Stage 6 — Analyze.

sol reads workspace/results.json (falling back to the codex transcript tail when
results are missing or malformed) and issues a verdict of supported / refuted /
inconclusive / broken plus notes. On broken/inconclusive it also produces
concrete revision instructions, stored on the iteration so the design stage can
use them on the next loop.
"""
from __future__ import annotations

import json

from ..config import Config
from ..llm import LLM
from ..state import ProjectState, Verdict
from . import load_prompt

_VERDICTS = {v.value for v in Verdict}


def _read_results(state: ProjectState, cfg: Config) -> tuple[str, bool]:
    """Return (results_text, ok). ok is False when results.json is absent/broken."""
    path = state.workspace(cfg.root) / "results.json"
    if not path.exists():
        return "results.json was not produced by the experiment.", False
    raw = path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(raw)
        return json.dumps(parsed, indent=2)[:6000], True
    except ValueError:
        return "results.json exists but is not valid JSON:\n" + raw[:3000], False


def _transcript_tail(state: ProjectState, cfg: Config, limit: int = 4000) -> str:
    if not state.iterations:
        return ""
    log = state.dir(cfg.root) / "logs" / f"codex_iter{state.iterations[-1].index}.log"
    if not log.exists():
        return ""
    return log.read_text(encoding="utf-8", errors="replace")[-limit:]


def run(state: ProjectState, cfg: Config, llm: LLM) -> ProjectState:
    results_text, ok = _read_results(state, cfg)
    tail = "" if ok else _transcript_tail(state, cfg)
    chosen = next((h for h in state.hypotheses if h.chosen), None)
    it = state.iterations[-1] if state.iterations else None
    timed_out = bool(it and it.timed_out)

    prompt = load_prompt(
        cfg, "analyze",
        topic=state.topic,
        hypothesis=(chosen.statement if chosen else state.topic),
        expected_if_true=(state.design.expected_if_true if state.design else ""),
        expected_if_false=(state.design.expected_if_false if state.design else ""),
        results=results_text,
        transcript=(f"\nCodex transcript tail (results were unusable):\n{tail}" if tail else ""),
        timed_out=("yes" if timed_out else "no"),
    )
    data = llm.chat_json("reasoning", prompt, stage="analyze")
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        data = {}

    verdict_str = str(data.get("verdict", "")).strip().lower()
    verdict = Verdict(verdict_str) if verdict_str in _VERDICTS else (
        Verdict.BROKEN if not ok else Verdict.INCONCLUSIVE
    )
    notes = str(data.get("notes", "")).strip()
    revision = str(data.get("revision_instructions", "")).strip()

    state.verdict = verdict
    if chosen:
        chosen.outcome = verdict
    if it is not None:
        it.verdict = verdict
        it.notes = (notes + ("\n\nRevision instructions: " + revision if revision else "")).strip()
    return state
