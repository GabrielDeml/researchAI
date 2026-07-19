# Exact-validation-tie selection experiment

This workspace contains the deterministic 40-fixture experiment comparing
strict first-encountered selection across nine identifiers with
duplicate-collapsed, family-uniform selection.

Run from this directory:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python experiment.py
.venv/bin/python validate_results.py
```

The experiment writes `selection_records.csv`, `fixture_summary.csv`, the flat
scalar `results.json`, and `figures/selection_frequency.png`. Re-running with
the same code and dependency versions deterministically reproduces the data and
figure.
