"""Literature grounding: arXiv + Semantic Scholar search, relevance triage, and
optional PDF skimming.

Everything here is defensive by construction — every network path degrades to
"fewer or no results" on timeout, 4xx/5xx, or transport failure and never raises
into the pipeline. The only exception that propagates is ``harness.llm.Paused``
(STOP pressed during an LLM call), which the pipeline needs in order to
checkpoint.

Public surface used by the survey stage::

    queries = derive_queries(llm, topic)
    abstracts_block, fulltext_block, citations = gather_literature(llm, topic, cfg)
"""
from __future__ import annotations

import io

import httpx
from pydantic import BaseModel

from .config import Config
from .llm import LLM, Paused
from .state import Citation
from .stages import load_prompt

S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_FIELDS = "title,authors,year,abstract,url,externalIds"
_UA = {"User-Agent": "researchAI/0.1 (autonomous literature survey)"}


class Candidate(BaseModel):
    title: str = ""
    authors: list[str] = []
    year: int | None = None
    abstract: str = ""
    url: str = ""
    source: str = ""       # arxiv id or semantic-scholar paper id
    arxiv_id: str = ""     # bare id (e.g. 2401.01234) when known, for PDF fetch

    def key(self) -> str:
        if self.arxiv_id:
            return "arxiv:" + self.arxiv_id.split("v")[0]
        return "title:" + "".join(self.title.lower().split())

    def to_citation(self) -> Citation:
        return Citation(
            title=self.title,
            authors=self.authors[:8],
            year=self.year,
            url=self.url,
            source=self.source,
        )


# --------------------------------------------------------------------------- #
# Query derivation (sol)
# --------------------------------------------------------------------------- #
def derive_queries(llm: LLM, topic: str, cfg: Config) -> list[str]:
    """Ask sol for 2-4 focused search queries. Falls back to the raw topic."""
    try:
        data = llm.chat_json(
            "reasoning",
            load_prompt(cfg, "survey_queries", topic=topic),
            stage="survey",
        )
    except Paused:
        raise
    except Exception:
        return [topic]
    queries: list[str] = []
    if isinstance(data, dict):
        data = data.get("queries", [])
    if isinstance(data, list):
        for q in data:
            q = (q if isinstance(q, str) else str(q)).strip()
            if q:
                queries.append(q)
    queries = queries[:4]
    return queries or [topic]


# --------------------------------------------------------------------------- #
# arXiv
# --------------------------------------------------------------------------- #
def search_arxiv(query: str, max_results: int = 8) -> list[Candidate]:
    try:
        import arxiv  # local import: keeps module import cheap and failure-isolated
        client = arxiv.Client(page_size=max_results, delay_seconds=1.0, num_retries=1)
        search = arxiv.Search(
            query=query, max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        out: list[Candidate] = []
        for r in client.results(search):
            short = r.get_short_id()
            out.append(Candidate(
                title=(r.title or "").strip().replace("\n", " "),
                authors=[a.name for a in r.authors],
                year=r.published.year if r.published else None,
                abstract=(r.summary or "").strip().replace("\n", " "),
                url=r.entry_id or f"https://arxiv.org/abs/{short}",
                source=f"arXiv:{short}",
                arxiv_id=short,
            ))
        return out
    except Exception:
        return []  # network down / parse error / arxiv package hiccup — degrade


# --------------------------------------------------------------------------- #
# Semantic Scholar Graph API (no key required for basic search)
# --------------------------------------------------------------------------- #
def search_semantic_scholar(query: str, max_results: int = 8) -> list[Candidate]:
    try:
        resp = httpx.get(
            S2_SEARCH_URL,
            params={"query": query, "limit": max_results, "fields": S2_FIELDS},
            headers=_UA, timeout=15.0,
        )
        if resp.status_code != 200:
            return []
        data = resp.json().get("data", []) or []
    except Exception:
        return []
    out: list[Candidate] = []
    for p in data:
        ext = p.get("externalIds") or {}
        arxiv_id = (ext.get("ArXiv") or "").strip()
        out.append(Candidate(
            title=(p.get("title") or "").strip(),
            authors=[a.get("name", "") for a in (p.get("authors") or [])],
            year=p.get("year"),
            abstract=(p.get("abstract") or "").strip(),
            url=p.get("url") or "",
            source="S2:" + str(p.get("paperId", "")),
            arxiv_id=arxiv_id,
        ))
    return out


def gather_candidates(llm: LLM, topic: str, cfg: Config, per_query: int = 6) -> list[Candidate]:
    """Run every derived query against both sources and dedupe."""
    queries = derive_queries(llm, topic, cfg)
    seen: dict[str, Candidate] = {}
    for q in queries:
        for cand in search_arxiv(q, per_query) + search_semantic_scholar(q, per_query):
            if not cand.title or not cand.abstract:
                continue
            seen.setdefault(cand.key(), cand)
    return list(seen.values())


# --------------------------------------------------------------------------- #
# Relevance triage (terra)
# --------------------------------------------------------------------------- #
def triage(llm: LLM, topic: str, candidates: list[Candidate], cfg: Config,
           keep: int = 10) -> list[Candidate]:
    """Select the ~``keep`` most relevant candidates. Falls back to the head of
    the list if the model can't be used or returns garbage."""
    if len(candidates) <= keep:
        return candidates
    listing = "\n".join(
        f"[{i}] {c.title} ({c.year or 'n.d.'}) — {c.abstract[:300]}"
        for i, c in enumerate(candidates)
    )
    try:
        data = llm.chat_json(
            "utility",
            load_prompt(cfg, "survey_triage", topic=topic, keep=keep, papers=listing),
            stage="survey",
        )
    except Paused:
        raise
    except Exception:
        return candidates[:keep]
    if isinstance(data, dict):
        data = data.get("selected") or data.get("indices") or []
    idxs: list[int] = []
    if isinstance(data, list):
        for x in data:
            try:
                i = int(x)
            except (TypeError, ValueError):
                continue
            if 0 <= i < len(candidates) and i not in idxs:
                idxs.append(i)
    chosen = [candidates[i] for i in idxs[:keep]]
    return chosen or candidates[:keep]


# --------------------------------------------------------------------------- #
# PDF skimming (best-effort)
# --------------------------------------------------------------------------- #
def fetch_pdf_text(arxiv_id: str, max_chars: int = 6000) -> str:
    """Download an arXiv PDF and extract truncated text. Returns "" on any
    failure (no PDF, parse error, network)."""
    if not arxiv_id:
        return ""
    bare = arxiv_id.split("v")[0]
    try:
        resp = httpx.get(f"https://arxiv.org/pdf/{bare}.pdf",
                         headers=_UA, timeout=30.0, follow_redirects=True)
        if resp.status_code != 200 or not resp.content:
            return ""
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(resp.content))
        parts: list[str] = []
        total = 0
        for page in reader.pages:
            txt = page.extract_text() or ""
            parts.append(txt)
            total += len(txt)
            if total >= max_chars:
                break
        return "".join(parts)[:max_chars].strip()
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# Top-level orchestration used by the survey stage
# --------------------------------------------------------------------------- #
def gather_literature(
    llm: LLM, topic: str, cfg: Config, *, keep: int = 10, deep_read: int = 2,
) -> tuple[str, str, list[Citation]]:
    """Return ``(abstracts_block, fulltext_block, citations)``.

    ``abstracts_block`` is a numbered, cite-ready digest of the triaged papers;
    ``fulltext_block`` is truncated body text from the top few arXiv PDFs;
    ``citations`` is the list to store on the project state. Any and all of these
    may be empty when the network is unavailable — the survey stage handles that.
    """
    candidates = gather_candidates(llm, topic, cfg)
    if not candidates:
        return "", "", []

    selected = triage(llm, topic, candidates, cfg, keep=keep)

    blocks = []
    for i, c in enumerate(selected, 1):
        authors = ", ".join(c.authors[:4]) + (" et al." if len(c.authors) > 4 else "")
        blocks.append(
            f"[{i}] {c.title} — {authors or 'unknown authors'} ({c.year or 'n.d.'})\n"
            f"    {c.source} {c.url}\n"
            f"    Abstract: {c.abstract[:900]}"
        )
    abstracts_block = "\n\n".join(blocks)

    fulltexts = []
    for c in selected:
        if len([f for f in fulltexts if f]) >= deep_read:
            break
        if c.arxiv_id:
            txt = fetch_pdf_text(c.arxiv_id)
            if txt:
                fulltexts.append(f"### Full text excerpt — {c.title} ({c.source})\n{txt}")
    fulltext_block = "\n\n".join(fulltexts)

    citations = [c.to_citation() for c in selected]
    return abstracts_block, fulltext_block, citations
