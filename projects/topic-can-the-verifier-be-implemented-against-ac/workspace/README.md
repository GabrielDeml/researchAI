# Authenticated Git object verification vs. `refs/replace`

This workspace contains a deterministic experiment that creates twelve synthetic
SHA-1 Git repositories and compares two traversals pinned to the same literal
commit ID:

- a raw loose-object verifier that never reads refs, the index, the worktree, or
  alternates; and
- ordinary `git ls-tree`, which honors `refs/replace` unless explicitly disabled.

Run it from this directory with:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python experiment.py
```

The aggregate machine-readable metrics are in `results.json`. Detailed case data
and authenticated fixtures are under `results/`, and figures are under `figures/`
with the protocol-required duplicate at `results/key_result.png`.
