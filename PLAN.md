# researchAI — Autonomous Frontier-Research Harness

A continuously running "AI scientist" on this Mac: it picks (or receives) a research
topic, grounds itself in the literature, generates hypotheses, implements and runs
experiments, analyzes results, iterates, and writes up a cited report — then feeds
what it learned into the next cycle.

## Verified environment

| Piece | Status |
|---|---|
| CLIProxyAPI | Running (homebrew service, port 8317), API key in `/opt/homebrew/etc/cliproxyapi.conf` |
| Models via ChatGPT login | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.3-codex-spark`, image models |
| Chat completions | Tested working (OpenAI-compatible, reports token usage, supports tool calls) |
| Codex CLI | 0.144.1 at `/opt/homebrew/bin/codex` (same ChatGPT account) |
| Runtime | Python 3.14.6, `uv`, Docker 28.3.3 |

Model policy: **use only `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`** — no other
models. **Anything involving logic/reasoning goes to `sol`**; terra and luna handle
non-reasoning utility work. OpenAI has removed hourly usage limits, so quota is not a
design constraint — 429/backoff handling stays in as cheap defensive insurance, but
the harness does not need to ration calls.

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │  supervisor (launchd, KeepAlive)         │
                    │  queue → run one project → digest → next │
                    └───────────────┬─────────────────────────┘
                                    │ per project
   ┌───────────┬───────────┬───────┴────┬────────────┬───────────┬──────────┐
   │ 1 intake  │ 2 survey  │ 3 ideate   │ 4 design   │ 5 build+run│ 6 analyze│
   │ topic from│ arXiv +   │ hypotheses,│ experiment │ Codex CLI  │ iterate ≤N│
   │ queue/ or │ Semantic  │ novelty/   │ plan +     │ exec in    │ or accept │
   │ self-pick │ Scholar   │ feasibility│ metrics    │ sandbox    │           │
   └───────────┴───────────┴────────────┴────────────┴───────────┴──────────┘
                                    │
                     ┌──────────────┴──────────────┐
                     │ 7 write-up → 8 peer review  │
                     │ (different model reviews)   │
                     └──────────────┬──────────────┘
                                    │
                       journal (memory) + digest
```

### Stage pipeline (state machine, checkpointed after every stage)

1. **Intake** — pop a topic file from `queue/`; if empty, the ideation model proposes
   a topic informed by `journal/` (what's been tried, what's open).
2. **Literature survey** — arXiv API + Semantic Scholar API (both free, no key needed
   for basic use). Fetch abstracts → model selects ~10 most relevant → fetch/skim
   PDFs → produce a grounded survey with citations. No reliance on model web access.
3. **Hypothesis generation** — generate ~8 candidate hypotheses; score each on
   novelty (vs. survey + journal), feasibility (runnable on this Mac in <30 min),
   and expected information gain; pick the best 1–2.
4. **Experiment design** — concrete protocol: what to build, datasets/inputs,
   success metrics, compute/time budget, expected outcomes either way.
5. **Implement + run** — delegate to **Codex CLI** (`codex exec --sandbox
   workspace-write --cd workspaces/<id>`) with the design doc as the prompt.
   Codex writes the code, creates a venv, runs the experiment, saves
   `results.json` + figures. Hard wall-clock timeout enforced by the supervisor.
6. **Analyze** — model reads results + logs; verdict: *supported / refuted /
   inconclusive / broken*. Broken or inconclusive → revise design and loop back to
   5 (max N iterations, default 4).
7. **Write-up** — `report.md`: abstract, background w/ citations, method, results
   (embedding the generated figures), limitations, follow-up questions.
8. **Peer review** — a *different* model variant reviews and scores the report
   (soundness, novelty, clarity); one revision pass if score < threshold. Review is
   attached to the report.
9. **Archive** — project folder finalized; journal updated with a compressed
   "lessons learned" entry; follow-up questions pushed to `queue/` as candidate
   future topics (this is what makes the loop compounding rather than episodic).

### Model role assignment (config-driven)

Policy: only the three `gpt-5.6` variants are allowed, and **every stage that
requires logic/reasoning uses `sol`**.

| Role | Model | Why |
|---|---|---|
| Ideation / hypothesis | `gpt-5.6-sol` | reasoning stage |
| Experiment design + analysis | `gpt-5.6-sol` | reasoning stage |
| Coding agent (via Codex CLI) | `gpt-5.6-sol` | reasoning stage (`codex exec --model gpt-5.6-sol`) |
| Peer reviewer | `gpt-5.6-sol` | reasoning stage |
| Write-up prose polish | `gpt-5.6-terra` | non-reasoning surface pass over sol's draft |
| Literature triage, log/journal summarization, digests | `gpt-5.6-terra` / `gpt-5.6-luna` | utility work, keeps sol calls focused |

All roles are entries in `config.yaml`, and the allowed-model list is enforced in
`llm.py` (any request for a model outside the three variants is rejected at the
client). One trade-off to be aware of: with sol both writing and reviewing reports,
the peer-review stage loses model diversity and will agree with itself more often —
if that shows up in practice, flipping the reviewer to terra is a one-line config
change.

### Continuous operation

- **Supervisor**: a Python process managed by a launchd agent
  (`~/Library/LaunchAgents/com.gdeml.researchai.plist`, `KeepAlive=true`). Serial
  (one project at a time) by default for machine sanity, but with no hourly API
  limits, bumping `max_parallel_projects` in config is a supported knob once the
  pipeline is proven.
- **Checkpointing**: every stage writes `projects/<slug>/state.json`; on crash or
  reboot the supervisor resumes mid-project.
- **Pacing (defensive, not rationing)**:
  - Quota is effectively unlimited, so there are no hard daily caps by default —
    optional caps exist in config but ship disabled.
  - Every response's `usage` is still logged to `usage.jsonl` for observability.
  - On 429 or 5xx: exponential backoff; persistent failure pauses the project and
    surfaces in the digest rather than hot-looping.
  - Idle behavior when the queue is empty: self-ideate a new topic, or sleep if
    `auto_topics: false`.
- **Kill switch**: `touch STOP` in the repo root pauses the loop at the next stage
  boundary; delete it to resume. `STOP` is checked before every LLM call and every
  Codex invocation.
- **Digest**: after each project (and daily at minimum), regenerate
  `digests/YYYY-MM-DD.md` — what ran, verdicts, one-paragraph findings, links to
  full reports. This is the thing you actually read.

### Monitoring web dashboard

A local webserver running alongside the supervisor so you can watch the loop live
instead of waiting for digests.

- **Stack**: FastAPI + uvicorn serving a single self-contained HTML/JS page (no
  frontend build step). Binds `127.0.0.1:8780`. It reads the same on-disk state the
  supervisor writes (`projects/*/state.json`, `usage.jsonl`, `queue/`, `journal/`,
  `logs/`), so the dashboard never holds state of its own and can restart freely.
- **Live updates** via SSE: the page streams supervisor log lines and re-renders
  status as stage checkpoints land — no manual refreshing.
- **Views**:
  - *Now*: current project, stage, iteration count, elapsed time, live log tail
    (including the Codex transcript while stage 5 runs).
  - *Queue*: pending topics, with an "add topic" form that drops a file in `queue/`.
  - *History*: all projects with verdict badges (supported / refuted /
    inconclusive / broken), reviewer scores, and rendered `report.md` + figures.
  - *Usage*: tokens and calls per model/stage over time from `usage.jsonl`.
  - *Journal*: rendered lab notebook.
- **Controls** (the only write paths): pause/resume (creates/removes `STOP`),
  skip current project, enqueue topic. Destructive actions stop there — no
  deletion or config editing from the browser.
- **Security**: localhost-only by default; if you later want it on Tailscale,
  gate it behind a bearer token in `config.yaml`.
- **Health**: supervisor and dashboard each expose a heartbeat; the dashboard
  shows loudly when the supervisor is down, the proxy is unreachable, or auth
  has expired.

### Sandboxing & guardrails

- Experiments run **only** in `workspaces/<id>/`; Codex CLI's own
  `--sandbox workspace-write` confines writes (macOS Seatbelt), and the supervisor
  additionally enforces wall-clock timeout and a disk quota per workspace.
- Command execution never leaves the harness user; no sudo; Codex runs
  non-interactive (`exec`) so nothing can prompt-and-hang.
- Phase-2 hardening option: run stage 5 inside a Docker container (Linux, no host
  FS, optional `--network none` after dependency install) for true isolation.
- Max iterations, max runtime, and max cost per project are config caps, not
  prompt suggestions.

### Memory (what makes cycle N+1 smarter than cycle N)

- `journal/journal.md` — running lab notebook: per-project entry with topic,
  hypothesis, verdict, key numbers, and "what I'd do differently".
- `journal/ideas.jsonl` — every hypothesis ever generated + its score/outcome, so
  ideation is explicitly told what's already been tried (prevents repetition, the
  #1 failure mode of looped agents).
- Both are summarized by `gpt-5.6-terra` into a bounded context block for prompts.

## Repository layout

```
researchAI/
  PLAN.md                  ← this file
  config.yaml              # endpoint, API key ref, model roles, budgets, limits
  pyproject.toml           # uv-managed; deps: openai, pydantic, httpx, arxiv, pyyaml, rich, fastapi, uvicorn
  harness/
    llm.py                 # OpenAI client → localhost:8317, retries, usage ledger
    literature.py          # arXiv + Semantic Scholar clients
    codex_runner.py        # codex exec wrapper: sandbox flags, timeout, log capture
    stages/                # intake, survey, ideate, design, implement, analyze,
                           #   writeup, review — one module each, same interface
    state.py               # pydantic project state, checkpoint/resume
    journal.py             # memory read/write + summarization
    supervisor.py          # the loop: queue → stages → digest; STOP + budget checks
    web/
      app.py               # FastAPI dashboard: state/SSE endpoints + controls
      static/index.html    # single-page UI (no build step)
  prompts/                 # one template per stage, versioned in git
  queue/                   # drop a .md topic file here to enqueue research
  projects/<slug>/         # state.json, survey.md, design.md, workspace/, report.md, review.md
  journal/
  digests/
  logs/                    # llm calls (jsonl), codex transcripts, supervisor log
```

## Build milestones

**M0 — Scaffolding (small)**
`git init`, uv project, `config.yaml`, `llm.py` with retry/backoff/usage-ledger,
model registry. Smoke test: one call per role model through the proxy.

**M1 — One full run, on demand (the core)**
`python -m harness run --topic "..."` executes stages 1→9 once, single iteration,
producing `report.md` end-to-end on a toy topic. Codex-CLI-backed stage 5 with
timeout. This proves the whole pipeline before any autonomy is added.

**M2 — Iteration + review + memory**
Analyze→redesign loop with iteration cap; peer-review stage with revision pass;
journal + ideas ledger feeding ideation; follow-ups auto-enqueued.

**M3 — Continuous mode**
Supervisor + launchd plist, checkpoint/resume, STOP file, defensive backoff (no
budget rationing), digest generation, and a minimal status page (current stage +
log tail) so the loop is never running blind. At this point it runs 24/7
unattended.

**M4 — Full monitoring dashboard**
The complete web UI from the dashboard section: SSE live views, queue management,
project history with rendered reports and figures, usage charts, journal view,
pause/skip controls, health indicators. Runs as its own launchd service.

**M5 — Hardening & polish (optional, as needed)**
Docker sandbox for stage 5 · notification on digest/failure · smarter topic
selection from journal trends · parallel projects (now viable early, since API
limits are gone — gate it on what the Mac can handle during experiment runs;
dashboard already renders multiple in-flight projects).

## Risks & mitigations

- **Looped-agent degeneration** (repeating ideas, trivial experiments) — ideas
  ledger in ideation context, novelty scoring against the journal, peer-review
  gate, iteration caps. Extra relevant now that sol reviews its own writing.
- **Local machine as the bottleneck** — with API limits gone, the constraint shifts
  to your Mac's CPU/GPU/disk during stage 5; timeouts, disk quotas, and the serial
  default protect the machine, not the quota.
- **Runaway experiments** — wall-clock timeout, workspace confinement, disk quota,
  `--network` restrictions in the Docker variant.
- **Silent quality drift** — digests keep a human (you) in the review loop daily;
  reviewer scores are tracked over time in the journal.
- **Proxy/auth expiry** — supervisor health-checks `GET /v1/models` at startup and
  between projects; on auth failure it pauses and writes a loud line to the digest
  instead of burning cycles.
