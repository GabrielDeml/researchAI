"""Stage 3 — Hypothesis generation.

sol generates 8 hypotheses scored 0-10 on novelty / feasibility / info_gain,
explicitly handed the ideas ledger with an instruction not to repeat past ideas.
The parsed hypotheses are validated into Hypothesis models and the best-scoring
one is marked ``chosen``.
"""
from __future__ import annotations

from ..config import Config
from ..journal import ideas_ledger_text
from ..llm import LLM
from ..state import Hypothesis, ProjectState
from . import load_prompt

_N = 8


def _parse(data) -> list[Hypothesis]:
    if isinstance(data, dict):
        data = data.get("hypotheses") or data.get("ideas") or []
    out: list[Hypothesis] = []
    if not isinstance(data, list):
        return out
    for i, item in enumerate(data, 1):
        if not isinstance(item, dict):
            continue
        statement = str(item.get("statement") or item.get("hypothesis") or "").strip()
        if not statement:
            continue
        def _num(key: str) -> float:
            try:
                return max(0.0, min(10.0, float(item.get(key, 0))))
            except (TypeError, ValueError):
                return 0.0
        out.append(Hypothesis(
            id=i,
            statement=statement,
            rationale=str(item.get("rationale", "")).strip(),
            novelty=_num("novelty"),
            feasibility=_num("feasibility"),
            info_gain=_num("info_gain"),
        ))
    return out


def run(state: ProjectState, cfg: Config, llm: LLM) -> ProjectState:
    survey_path = state.dir(cfg.root) / "survey.md"
    survey = survey_path.read_text(encoding="utf-8")[:8000] if survey_path.exists() else "(no survey available)"
    ledger = ideas_ledger_text(cfg) or "(no prior hypotheses on record)"

    prompt = load_prompt(
        cfg, "ideate", n=_N, topic=state.topic, survey=survey, ledger=ledger,
    )

    hyps: list[Hypothesis] = []
    for attempt in range(2):
        data = llm.chat_json("reasoning", prompt, stage="ideate")
        hyps = _parse(data)
        if hyps:
            break
        # One retry with a stricter nudge if parsing produced nothing usable.
        prompt = prompt + (
            "\n\nIMPORTANT: reply with ONLY a JSON array of objects, each having "
            "keys statement, rationale, novelty, feasibility, info_gain."
        )

    if not hyps:  # last-resort guard so the pipeline never dies on a bad reply
        hyps = [Hypothesis(id=1, statement=f"A minimal empirical study of: {state.topic}",
                           rationale="Fallback hypothesis after unparseable ideation output.",
                           novelty=3.0, feasibility=8.0, info_gain=4.0)]

    best = max(range(len(hyps)), key=lambda i: hyps[i].score)
    hyps[best].chosen = True
    state.hypotheses = hyps
    return state
