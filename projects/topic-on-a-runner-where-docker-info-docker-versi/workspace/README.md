# Docker parent-exit completion experiment

`experiment.py` is the Python 3.12, standard-library-only host harness. It
strictly uses `DOCKER_HOST=unix:///var/run/docker.sock`, runs three independent
Docker gates, resolves a preloaded Linux Python 3.12 image to an immutable ID,
builds the fixture with `--network=none`, and runs a smoke container before the
timed section.

When preflight passes, it sequentially runs the fixed order
`D1,C1,...,D6,C6` and then the identical replay order. The fixture image runs
`fixture/monitor.py` as PID 1. That process creates each requested topology and
observes parent exit, retained PID/starttime descendant identities, and declared
output descriptors at a 10 ms cadence.

Run it with:

```sh
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PYTHONHASHSEED=1729 .venv/bin/python experiment.py
```

The required flat scalar metrics are written to `results.json`; complete gate
evidence and, when scheduled, atomic execution records are retained under the
timestamped `artifacts/` directory. The deterministic figure is
`figures/key_result.png`. If any infrastructure gate fails, the harness
schedules zero fixtures and records `hypothesis_evaluated=false` rather than
calling the hypothesis refuted.
