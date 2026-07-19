# researchAI

An autonomous "AI scientist" harness. It picks (or receives) a research topic,
grounds itself in the literature (arXiv / Semantic Scholar), generates
hypotheses, designs experiments, implements and runs them via the Codex CLI in
a sandboxed workspace, analyzes the results, iterates, and writes up a cited,
peer-reviewed report — then feeds what it learned into the next cycle.

All LLM calls go through a local [CLIProxyAPI](https://github.com/luispater/CLIProxyAPI)
instance; experiments are executed by `codex exec` with timeouts, disk quotas,
and process-group cleanup enforced by the harness.

## Prerequisites

- **Python ≥ 3.12** and [`uv`](https://docs.astral.sh/uv/)
- **CLIProxyAPI** running locally on `http://127.0.0.1:8317/v1` (see
  `proxy.base_url` in `config.yaml`), exposing the allowed models
  (`gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` — the harness hard-rejects
  anything else)
- **Codex CLI** on your `PATH` (used for the build/run stage and
  self-improvement)

## Setup

```sh
uv sync
```

The proxy API key is never stored in this repo. It is resolved at load time
from, in order:

1. the `RESEARCHAI_API_KEY` environment variable, or
2. the first `api-keys:` entry in CLIProxyAPI's own config
   (`/opt/homebrew/etc/cliproxyapi.conf`).

Optional, one-time: set up the `results` publishing branch (an orphan branch
checked out in `.results-worktree/` that outputs are committed and pushed to
after each project):

```sh
scripts/setup_results_branch.sh
```

Sanity-check everything offline (imports, config, model policy, CLI, prompts):

```sh
uv run python -m harness selfcheck
```

## Running

All commands run from the repo root. A singleton lock (`.runner.lock`) ensures
only one of `run` / `drain` / `supervise` / `improve` is active at a time.

```sh
# One research project, end-to-end
uv run python -m harness run --topic "your research question"

# Resume a crashed/interrupted project by its slug (directory name in projects/)
uv run python -m harness run --resume <slug>

# Work through the queue (and resume crashed projects), then exit
uv run python -m harness drain

# 24/7 supervisor loop: queue → project → digest → next
uv run python -m harness supervise

# Monitoring dashboard (default http://127.0.0.1:8780)
uv run python -m harness serve
```

### Queueing topics

Drop a Markdown file into `queue/`:

```markdown
# Topic

Your research question here.
```

`drain`/`supervise` pick items up in order. With `supervisor.auto_topics: true`,
the supervisor self-ideates a new topic when the queue is empty, and finished
projects auto-enqueue follow-up questions.

### Pausing

`touch STOP` in the repo root pauses all work (`drain` exits; `supervise` idles
without starting anything new). Remove the file to resume.

### Continuous operation (launchd)

For unattended 24/7 operation on macOS:

```sh
scripts/install_launchd.sh
```

This only copies the supervisor + dashboard plists into
`~/Library/LaunchAgents` and prints the `launchctl bootstrap` commands —
actually starting them is a deliberate switch you flip yourself.

## Layout

| Path | What it is |
|---|---|
| `config.yaml` | All knobs: proxy, model roles, limits, supervisor, dashboard, self-improvement |
| `harness/` | The code: CLI (`__main__.py`), pipeline, stages, codex runner, supervisor, web dashboard |
| `prompts/` | Prompt templates for every pipeline stage |
| `queue/` | Pending topic files (Markdown) |
| `projects/` | One directory per project: state, workspace, logs, report |
| `digests/`, `journal/` | Cross-project memory: run digests and accumulated lessons |
| `logs/` | Supervisor and self-improvement logs |
| `.results-worktree/` | Checkout of the `results` branch that outputs are published to |

Research outputs live on the `results` branch; code lives on `main`.

## Configuration highlights

See `config.yaml` for the full set. Notables:

- `models.roles` — which model handles reasoning, coding, review, polish, and
  utility work (reasoning-heavy work is pinned to `gpt-5.6-sol`)
- `limits` — iterations per project, per-experiment wall clock, disk quota,
  transcript cap, minimum free disk (fails closed), review-score threshold
- `results.publish` — auto-commit+push outputs to the results branch after each
  project

## Self-improvement & self-update

The harness maintains its own code (see `harness/self_improve.py`):

- **Auto-improve** — after every `self_improve.every_n_projects` finished
  projects (and via `uv run python -m harness improve` on demand), codex gets a
  fresh git worktree of this repo plus an evidence pack (supervisor errors,
  verdicts, reviewer scores, dead-lettered queue items, journal, past attempts)
  and makes one small improvement. It is adopted only if it avoids every
  `protected_paths` entry **and** passes `python -m harness selfcheck` (offline
  gate: imports, config, pinned model policy, CLI, prompts, tests). In `apply`
  mode the change fast-forwards the running branch and the supervisor re-execs;
  in `propose` mode it waits on a `self-improve/<ts>` branch for review.
  History: `logs/self_improve.jsonl` + `journal/improvements.md` (published to
  the results branch).
- **Auto-update** — with `self_update.pull` on, the supervisor does an ff-only
  pull from origin between projects and restarts itself when new code lands.

Guardrails: a dirty working tree always skips/downgrades to a proposal (user
work wins); the gate, this engine, and its prompt are protected paths, so the
improver can never weaken what judges it; `touch STOP` pauses improvement like
all other work; `enabled: false` in `config.yaml` turns it off.
