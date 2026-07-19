# Fresh isolated `make reproduce` experiment

This package runs six primary and six paired replay executions of the literal
command `make reproduce` in new local Git clones and new network-disabled,
least-privilege Docker containers.  `verify.py` independently recomputes the
66 provenance categories, 18 primary/replay byte comparisons, and 18
primary/released-reference byte comparisons.

## Prerequisites

- macOS arm64 or Linux with Docker and Python 3.11+
- an architecture-matching Linux image containing CPython 3.12, `sh`, Git, and
  GNU Make, already present in the local Docker image store
- no network access is needed or used by the experiment

Package that already-local immutable image once (this never pulls):

```sh
.venv/bin/python provision_image.py python:3.12.8-bookworm
```

This creates `image/experiment-image.tar` plus `image.lock.json`, including the
archive SHA-256 and exact immutable image ID.  These two files are the offline
image package to transfer with the experiment.

## Run

```sh
python3 -m venv .venv
.venv/bin/python experiment.py
```

The preflight may start Docker Desktop on macOS and polls for at most 120
seconds. It never pulls an image. If Docker, permissions, or the packaged image
are unavailable, it writes an explicit `BROKEN` result without executing any
primary or replay run.

Successful runs produce:

- `preflight/`: separate Docker info, image inspection, and smoke-test streams
- `primary-01` ... `primary-06` and `replay-01` ... `replay-06`: preserved clones
- `evidence/`: canonical records and raw, separate stdout/stderr streams
- `verification.json`: detailed independent verifier counts and failures
- `figures/verification_summary.png`: deterministic 1200x700 summary figure
- `results.json`: flat scalar metrics and final classification

The artifact seed is fixed at `20250308`; no timed run reuses a checkout or a
container.
