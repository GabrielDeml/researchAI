"""Stage 8 — Peer review.

sol acts as a skeptical, independent reviewer on a *fresh* prompt (the writer's
conversation is never included) and returns JSON with a 0-10 score, strengths,
weaknesses, and required fixes. review.md is written and ``state.reviewer_score``
set. If the score is below the config threshold, one revision pass rewrites
report.md against the critique and the report is re-scored once.
"""
from __future__ import annotations

from ..config import Config
from ..llm import LLM
from ..state import ProjectState
from . import load_prompt


def _review_once(cfg: Config, llm: LLM, report: str) -> dict:
    data = llm.chat_json("reviewer", load_prompt(cfg, "review", report=report), stage="review")
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        data = {}
    try:
        score = float(data.get("score", 0))
    except (TypeError, ValueError):
        score = 0.0
    return {
        "score": max(0.0, min(10.0, score)),
        "strengths": data.get("strengths", []),
        "weaknesses": data.get("weaknesses", []),
        "required_fixes": data.get("required_fixes", []),
    }


def _as_bullets(items) -> str:
    if isinstance(items, str):
        items = [items]
    if not items:
        return "- (none)\n"
    return "".join(f"- {str(x).strip()}\n" for x in items if str(x).strip()) or "- (none)\n"


def _write_review_md(path, review: dict, revised: bool) -> None:
    md = (
        f"# Peer review\n\n"
        f"**Score:** {review['score']:g}/10"
        + ("  _(after one revision pass)_" if revised else "")
        + "\n\n## Strengths\n" + _as_bullets(review["strengths"])
        + "\n## Weaknesses\n" + _as_bullets(review["weaknesses"])
        + "\n## Required fixes\n" + _as_bullets(review["required_fixes"])
    )
    path.write_text(md, encoding="utf-8")


def run(state: ProjectState, cfg: Config, llm: LLM) -> ProjectState:
    d = state.dir(cfg.root)
    report_path = d / "report.md"
    report = report_path.read_text(encoding="utf-8") if report_path.exists() else "(report missing)"

    review = _review_once(cfg, llm, report)
    revised = False

    if review["score"] < cfg.limits.review_score_threshold and report_path.exists():
        fixes = _as_bullets(review["required_fixes"]) + _as_bullets(review["weaknesses"])
        new_report = llm.chat(
            "reasoning",
            load_prompt(cfg, "writeup_revise", report=report, critique=fixes),
            stage="review",
        ).strip()
        if len(new_report) >= 0.6 * len(report):
            report_path.write_text(new_report + "\n", encoding="utf-8")
            report = new_report
            revised = True
            review = _review_once(cfg, llm, report)  # re-score once

    _write_review_md(d / "review.md", review, revised)
    state.review_path = "review.md"
    state.reviewer_score = review["score"]
    return state
