"""Project state: the single source of truth shared by pipeline, supervisor,
and dashboard.

One research project = one directory under projects/<slug>/ containing:
    state.json            (this model, atomically written)
    topic.md              original topic text
    survey.md             literature survey (stage 2)
    design.md             experiment design doc (stage 4)
    workspace/            codex-owned experiment sandbox
    logs/codex_iter<N>.log codex transcript per iteration
    report.md             final write-up (stage 7)
    review.md             peer review (stage 8)

The dashboard only ever reads these files; the pipeline only ever writes them
through ProjectState.save() so readers never see torn JSON.
"""
from __future__ import annotations

import datetime as dt
import os
import re
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"
    BROKEN = "broken"
    PENDING = "pending"


class Stage(str, Enum):
    INTAKE = "intake"
    SURVEY = "survey"
    IDEATE = "ideate"
    DESIGN = "design"
    IMPLEMENT = "implement"
    ANALYZE = "analyze"
    WRITEUP = "writeup"
    REVIEW = "review"
    ARCHIVE = "archive"
    DONE = "done"


STAGE_ORDER: list[Stage] = [
    Stage.INTAKE, Stage.SURVEY, Stage.IDEATE, Stage.DESIGN, Stage.IMPLEMENT,
    Stage.ANALYZE, Stage.WRITEUP, Stage.REVIEW, Stage.ARCHIVE,
]

# status values for ProjectState.status
RUNNING, PAUSED, DONE, FAILED, SKIPPED = "running", "paused", "done", "failed", "skipped"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def slugify(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:max_len].rstrip("-")
    return slug or "untitled"


class Citation(BaseModel):
    title: str
    authors: list[str] = []
    year: int | None = None
    url: str = ""
    source: str = ""  # e.g. arXiv id or Semantic Scholar id


class Hypothesis(BaseModel):
    id: int
    statement: str
    rationale: str = ""
    novelty: float = 0.0       # 0-10, judged against survey + journal
    feasibility: float = 0.0   # 0-10, runnable on this machine within budget
    info_gain: float = 0.0     # 0-10
    chosen: bool = False
    outcome: Verdict = Verdict.PENDING

    @property
    def score(self) -> float:
        return self.novelty + self.feasibility + self.info_gain


class ExperimentDesign(BaseModel):
    summary: str
    protocol: str              # concrete steps codex will implement
    metrics: list[str] = []
    time_budget_minutes: int = 30
    expected_if_true: str = ""
    expected_if_false: str = ""


class Iteration(BaseModel):
    index: int
    started_at: str = ""
    finished_at: str = ""
    codex_exit: int | None = None
    timed_out: bool = False
    verdict: Verdict = Verdict.PENDING
    notes: str = ""            # analyst's summary / revision instructions


class CodexResult(BaseModel):
    """Return type of harness.codex_runner.run_codex()."""
    exit_code: int
    timed_out: bool
    transcript_path: str
    duration_s: float


class ProjectState(BaseModel):
    slug: str
    topic: str
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    stage: Stage = Stage.INTAKE
    status: str = RUNNING      # running | paused | done | failed | skipped
    completed_stages: list[Stage] = []

    survey_path: str = ""
    citations: list[Citation] = []
    hypotheses: list[Hypothesis] = []
    design: ExperimentDesign | None = None
    iterations: list[Iteration] = []
    verdict: Verdict = Verdict.PENDING
    report_path: str = ""
    review_path: str = ""
    reviewer_score: float | None = None
    error: str = ""

    # --- persistence -------------------------------------------------------
    def dir(self, root: Path) -> Path:
        return root / "projects" / self.slug

    def workspace(self, root: Path) -> Path:
        return self.dir(root) / "workspace"

    def save(self, root: Path) -> None:
        d = self.dir(root)
        d.mkdir(parents=True, exist_ok=True)
        self.updated_at = now_iso()
        tmp = d / "state.json.tmp"
        tmp.write_text(self.model_dump_json(indent=2))
        os.replace(tmp, d / "state.json")  # atomic: dashboard never sees torn JSON

    @classmethod
    def load(cls, root: Path, slug: str) -> "ProjectState":
        return cls.model_validate_json((root / "projects" / slug / "state.json").read_text())

    @classmethod
    def load_all(cls, root: Path) -> list["ProjectState"]:
        out = []
        pdir = root / "projects"
        if pdir.exists():
            for f in sorted(pdir.glob("*/state.json")):
                try:
                    out.append(cls.model_validate_json(f.read_text()))
                except Exception:
                    continue  # skip corrupt/partial state rather than crash readers
        return out
