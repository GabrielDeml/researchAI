# Softmax-invisible rank-one grokking experiment

This workspace implements the full preregistered modular-addition experiment in
`experiment.py`.  It searches configurations A, B, and C in order, fits a
single norm threshold from four validated ordinary AdamW runs, audits an
exactly class-common rank-one output component in float64, and compares paired
no-decay and intervention forks.

The implementation uses full-batch CPU float32 training, float64 audits and
norms, one BLAS/PyTorch thread, deterministic PyTorch algorithms, and fixed
Python/NumPy/PyTorch seeds.

Reproduce from this directory:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
PYTHONHASHSEED=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python experiment.py
```

Run the quick implementation audit with:

```bash
PYTHONHASHSEED=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python experiment.py --smoke
```

Headline scalar metrics are in `results.json`; the detailed protocol outputs
are `results.csv`, `summary.json`, `baseline_search.csv`, `histories/`,
`checkpoints/`, `trajectories/`, and `figures/key_result.png`.
