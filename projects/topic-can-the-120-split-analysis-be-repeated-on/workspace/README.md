# Preregistered 120-split tie-breaking experiment

This workspace contains a deterministic implementation of the fixed synthetic
classification protocol. The experiment writes and hashes `preregistration.json`
before importing NumPy or creating experiment arrays, freezes and hashes all
selections before replication generation, and validates every required artifact.

Run it from this directory with the pinned local environment:

```sh
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python experiment.py
```

The machine-readable headline metrics are in `results.json`, detailed tables are
the root CSV files, and the prespecified figure is under `figures/`.

An independent read-back check can be run without regenerating outcomes:

```sh
.venv/bin/python validate_results.py
```
