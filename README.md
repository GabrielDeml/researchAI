# researchAI

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
