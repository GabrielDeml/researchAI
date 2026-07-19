# Locked-image CSV provenance experiment

Run the experiment from this directory:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python experiment.py
```

The runner requires `experiment_manifest.json` with the exact schema described
by the experiment protocol and a running Docker or Podman Linux engine. It is
fail-closed: missing inputs or inability to execute `strace` produces an
`invalid` decision instead of guessed targets or digests.

Primary outputs are `results.json`, `results.csv`, `summary.json`,
`environment.json`, `parser_unit_tests.txt`, and
`figures/provenance_digest_matrix.png`. Successful measured executions are kept
under `runs/`, and parser-control evidence is kept under `control_runs/`.
