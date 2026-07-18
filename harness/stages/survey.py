"""Stage 2 — Literature survey.

Orchestrates harness.literature to gather grounded material, has sol write a
survey with inline citations, and always appends a machine-generated References
section so the citations exist even if the model omits them. Populates
``state.citations`` and ``state.survey_path``. Never crashes when the network is
down — it writes an honest "limited grounding" survey instead.
"""
from __future__ import annotations

from .. import literature
from ..config import Config
from ..llm import LLM
from ..state import ProjectState
from . import load_prompt


def _references_md(citations) -> str:
    if not citations:
        return "## References\n\n_No external sources were retrievable for this survey._\n"
    lines = ["## References\n"]
    for i, c in enumerate(citations, 1):
        authors = ", ".join(c.authors[:4]) + (" et al." if len(c.authors) > 4 else "")
        year = f" ({c.year})" if c.year else ""
        url = f" <{c.url}>" if c.url else ""
        src = f" [{c.source}]" if c.source else ""
        lines.append(f"{i}. {authors or 'Unknown'}{year}. *{c.title}*.{src}{url}")
    return "\n".join(lines) + "\n"


def run(state: ProjectState, cfg: Config, llm: LLM) -> ProjectState:
    abstracts_block, fulltext_block, citations = literature.gather_literature(
        llm, state.topic, cfg
    )
    state.citations = citations

    if abstracts_block:
        prompt = load_prompt(
            cfg, "survey_write",
            topic=state.topic,
            abstracts=abstracts_block,
            fulltext=fulltext_block or "(no full-text excerpts were retrieved)",
        )
        body = llm.chat("reasoning", prompt, stage="survey").strip()
    else:
        body = (
            f"# Literature survey: {state.topic}\n\n"
            "External literature sources (arXiv, Semantic Scholar) could not be "
            "reached for this project, so this survey is limited. The experiment "
            "that follows is designed to be self-contained and interpretable "
            "without external grounding, and its novelty claims should be read "
            "with that caveat.\n"
        )

    # Guarantee a References section grounded in the citations we actually have.
    if "## References" not in body:
        body = body.rstrip() + "\n\n" + _references_md(citations)

    d = state.dir(cfg.root)
    d.mkdir(parents=True, exist_ok=True)
    (d / "survey.md").write_text(body + "\n", encoding="utf-8")
    state.survey_path = "survey.md"
    return state
