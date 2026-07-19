# Artifact Reconciliation Experiment

This workspace contains a deterministic experiment comparing strict path
equality, committed-path subset checking, and cryptographically verified
role-aware release reconciliation.

Run it with:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python experiment.py
```

The run recreates `artifact_reconciliation_experiment/` from scratch. Detailed
metrics, decisions, per-case results, repository snapshots, release archives,
and canonical sidecar manifests are stored there. The required flat headline
metrics are in `results.json`, and the grouped acceptance chart is also copied
to `figures/reconciliation_acceptance.png`.
