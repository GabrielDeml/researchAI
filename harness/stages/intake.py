"""Stage 1 — Intake.

Normalize the incoming topic and write projects/<slug>/topic.md. Also exposes
``propose_topic(cfg)`` used by the supervisor when the queue is empty: sol reads
the lab journal and proposes ONE fresh, feasible, pure-computational topic.
"""
from __future__ import annotations

import re

from ..config import Config
from ..journal import context_block
from ..llm import LLM
from ..state import ProjectState
from . import load_prompt


def _normalize(topic: str) -> str:
    topic = topic.strip()
    # Drop a leading "Topic:" / markdown heading / bullet if a queue file used one.
    topic = re.sub(r"^\s*#+\s*", "", topic)
    topic = re.sub(r"^\s*(topic|research question|question)\s*[:\-]\s*", "", topic, flags=re.I)
    topic = re.sub(r"^\s*[-*]\s*", "", topic)
    return " ".join(topic.split())


def run(state: ProjectState, cfg: Config, llm: LLM) -> ProjectState:
    state.topic = _normalize(state.topic)
    d = state.dir(cfg.root)
    d.mkdir(parents=True, exist_ok=True)
    (d / "topic.md").write_text(f"# Topic\n\n{state.topic}\n", encoding="utf-8")
    return state


def propose_topic(cfg: Config) -> str:
    """Propose ONE new feasible research topic informed by the journal.

    Pure-computational, runnable on a Mac in under 30 minutes. Builds its own LLM
    so the supervisor can call it before a project (and thus a project LLM) exists.
    """
    llm = LLM(cfg, project="propose")
    memory = context_block(cfg, llm) or "(the lab journal is empty — this is the first project)"
    prompt = load_prompt(cfg, "intake_propose", journal=memory)
    topic = llm.chat("reasoning", prompt, stage="intake").strip()
    # Model may wrap the topic in quotes or a heading; take the first real line.
    for line in topic.splitlines():
        line = _normalize(line)
        if len(line) > 12:
            return line.strip("\"'")
    return _normalize(topic).strip("\"'") or "Empirical comparison of two data-structure implementations in Python"
