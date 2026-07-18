"""Lab memory: the running journal, the ideas ledger, prompt-injection context,
and the daily digest.

Files (all under the repo root, created lazily):
    journal/journal.md    one compact human-readable section per finished project
    journal/ideas.jsonl   one JSON line per hypothesis ever generated + its outcome
    digests/YYYY-MM-DD.md  regenerated after every project by the supervisor

Nothing here is imported at module load beyond stdlib + config/state, so the
module is import-safe. LLM use (context compression, digest paragraphs) degrades
gracefully: if the model is paused or unreachable, callers still get a usable —
if blunter — result rather than an exception, except for ``context_block`` which
lets ``Paused`` propagate so the pipeline can checkpoint mid-stage.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from .config import Config
from .llm import LLM, Paused
from .state import ProjectState, now_iso


# --------------------------------------------------------------------------- #
# journal.md — per-project narrative
# --------------------------------------------------------------------------- #
def append_entry(
    cfg: Config,
    *,
    project: str,
    topic: str,
    hypothesis: str,
    verdict: str,
    key_numbers: str = "",
    lessons: str = "",
) -> Path:
    """Append one compact section to journal/journal.md and return its path.

    Idempotent per project: the archive stage can be replayed after a crash
    (append happens before the stage-completion checkpoint), and a duplicate
    entry would corrupt the memory injected into future ideation prompts."""
    cfg.journal_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.journal_dir / "journal.md"
    if path.exists() and re.search(
        rf"^## .* — {re.escape(project)}$", path.read_text(encoding="utf-8"), flags=re.M
    ):
        return path
    today = dt.date.today().isoformat()
    section = (
        f"\n## {today} — {project}\n\n"
        f"- **Topic:** {topic.strip()}\n"
        f"- **Hypothesis:** {hypothesis.strip() or '(none recorded)'}\n"
        f"- **Verdict:** {verdict}\n"
        f"- **Key numbers:** {key_numbers.strip() or '(none)'}\n"
        f"- **What I'd do differently:** {lessons.strip() or '(none)'}\n"
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(section)
    return path


# --------------------------------------------------------------------------- #
# ideas.jsonl — every hypothesis ever generated
# --------------------------------------------------------------------------- #
def append_ideas(cfg: Config, project: str, hypotheses: list) -> Path:
    """Append every hypothesis (with its scores + outcome) to ideas.jsonl.

    Idempotent per project (see append_entry): if any record for this project
    exists, the whole batch was already written — skip the replay."""
    cfg.journal_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.journal_dir / "ideas.jsonl"
    if any(rec.get("project") == project for rec in read_ideas(cfg)):
        return path
    ts = now_iso()
    with path.open("a", encoding="utf-8") as f:
        for h in hypotheses:
            rec = {
                "ts": ts,
                "project": project,
                "statement": getattr(h, "statement", ""),
                "novelty": getattr(h, "novelty", 0.0),
                "feasibility": getattr(h, "feasibility", 0.0),
                "info_gain": getattr(h, "info_gain", 0.0),
                "outcome": str(getattr(getattr(h, "outcome", ""), "value",
                                      getattr(h, "outcome", ""))),
            }
            f.write(json.dumps(rec) + "\n")
    return path


def read_ideas(cfg: Config) -> list[dict]:
    path = cfg.journal_dir / "ideas.jsonl"
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def ideas_ledger_text(cfg: Config, max_items: int = 60) -> str:
    """A plain-text list of previously tried hypotheses + outcomes, newest first.

    Injected verbatim into the ideation prompt so sol is told what not to repeat.
    Returns "" when the ledger is empty.
    """
    ideas = read_ideas(cfg)
    if not ideas:
        return ""
    lines = []
    for rec in ideas[-max_items:][::-1]:
        outcome = rec.get("outcome", "") or "untested"
        lines.append(
            f"- [{outcome}] {rec.get('statement', '').strip()} "
            f"(novelty {rec.get('novelty', 0)}, feasibility {rec.get('feasibility', 0)})"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# context_block — bounded prompt-injection summary of the whole lab memory
# --------------------------------------------------------------------------- #
def context_block(cfg: Config, llm: LLM, max_chars: int = 6000) -> str:
    """A bounded summary of journal + ideas for prompt injection.

    Returns "" when there is no memory yet. When the raw memory fits inside
    ``max_chars`` it is returned as-is; otherwise luna compresses it. ``Paused``
    is allowed to propagate so a STOP mid-stage checkpoints cleanly.
    """
    journal_path = cfg.journal_dir / "journal.md"
    journal_txt = journal_path.read_text(encoding="utf-8").strip() if journal_path.exists() else ""
    ideas_txt = ideas_ledger_text(cfg)
    if not journal_txt and not ideas_txt:
        return ""

    raw = ""
    if journal_txt:
        raw += "# Lab journal (past projects)\n" + journal_txt + "\n\n"
    if ideas_txt:
        raw += "# Ideas already tried\n" + ideas_txt + "\n"
    raw = raw.strip()

    if len(raw) <= max_chars:
        return raw

    # Too long: compress with luna. Feed it the tail (most recent memory) so the
    # summary is bounded even if the raw text is enormous.
    from .stages import load_prompt
    prompt = load_prompt(cfg, "journal_context",
                         words=max_chars // 5, memory=raw[-max_chars * 3:])
    try:
        summary = llm.chat("utility_alt", prompt, stage="journal_context").strip()
    except Paused:
        raise
    except Exception:
        # Model unreachable: fall back to a hard-truncated tail rather than crash.
        return raw[-max_chars:]
    return summary[:max_chars]


# --------------------------------------------------------------------------- #
# write_digest — the thing a human actually reads
# --------------------------------------------------------------------------- #
def _project_ran_today(st: ProjectState) -> bool:
    today = dt.date.today().isoformat()
    return st.updated_at[:10] == today or st.created_at[:10] == today


def _finding_paragraph(llm: LLM | None, st: ProjectState, cfg: Config) -> str:
    """One-paragraph finding for a project, via luna over its report, degrading
    to a mechanical summary when the model is unavailable or paused."""
    report = st.dir(cfg.root) / "report.md"
    chosen = next((h for h in st.hypotheses if h.chosen), None)
    hyp = chosen.statement if chosen else "(no hypothesis)"
    if llm is not None and report.exists():
        from .stages import load_prompt
        body = report.read_text(encoding="utf-8")[:8000]
        prompt = load_prompt(cfg, "digest", topic=st.topic, hypothesis=hyp,
                             verdict=st.verdict.value, report=body)
        try:
            return llm.chat("utility_alt", prompt, stage="digest").strip()
        except Exception:
            pass
    return (
        f"Verdict **{st.verdict.value}** on hypothesis: {hyp} "
        f"({len(st.iterations)} experiment iteration(s); "
        f"reviewer score {st.reviewer_score if st.reviewer_score is not None else 'n/a'})."
    )


def write_digest(cfg: Config) -> Path:
    """Regenerate digests/YYYY-MM-DD.md for today and return its path."""
    cfg.digests_dir.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    path = cfg.digests_dir / f"{today}.md"

    states = [s for s in ProjectState.load_all(cfg.root) if _project_ran_today(s)]
    states.sort(key=lambda s: s.updated_at, reverse=True)

    # Build the LLM lazily and tolerate a paused/unreachable model.
    llm: LLM | None
    try:
        llm = LLM(cfg, project="digest")
        if cfg.stop_file.exists():
            llm = None
    except Exception:
        llm = None

    lines = [f"# Research digest — {today}\n"]
    if not states:
        lines.append("_No projects ran today._\n")
    else:
        lines.append(f"{len(states)} project(s) touched today.\n")
        lines.append("| Project | Stage | Status | Verdict | Reviewer |")
        lines.append("|---|---|---|---|---|")
        for s in states:
            score = "-" if s.reviewer_score is None else f"{s.reviewer_score:g}/10"
            lines.append(
                f"| {s.slug} | {s.stage.value} | {s.status} | {s.verdict.value} | {score} |"
            )
        lines.append("")

        errors = [s for s in states if s.status in ("failed", "paused") and s.error]
        if errors:
            lines.append("## Attention\n")
            for s in errors:
                lines.append(f"- **{s.slug}** ({s.status}): {s.error.strip()[:400]}")
            lines.append("")

        lines.append("## Findings\n")
        for s in states:
            report_rel = (s.dir(cfg.root) / "report.md")
            link = f"projects/{s.slug}/report.md" if report_rel.exists() else "(no report)"
            lines.append(f"### {s.slug} — {s.topic}\n")
            lines.append(_finding_paragraph(llm, s, cfg))
            lines.append(f"\nReport: `{link}`\n")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
