# Signed publication-root gossip experiment

This workspace simulates 64 authenticated same-size split views and 64
consistent controls for a 64-leaf inventory transparency log. Each release
artifact carries a signed literal inventory root and a six-sibling inclusion
proof. The verifier's Ed25519 public key is deterministically configured by the
experiment and is never taken from an artifact.

Run the complete deterministic experiment with:

```sh
.venv/bin/python experiment.py
```

The run writes:

- `scenario_results.csv`: one row for each of the 128 scored scenarios.
- `results.json`: flat scalar metrics and the threshold-based outcome.
- `figures/checkpoint_gossip_results.png`: method alert rates by class.

## Verifier procedure

The verifier obtains the literal root from the artifact's lowercase `root`
field and decodes exactly 32 bytes. It reads the integer `tree_size` (which must
be 64), constructs the exact signed bytes
`b"INVCHKPT-v1\n" + tree_size.to_bytes(8, "big") + root`, and verifies the
64-byte Ed25519 signature with its public key pinned out of band. Only after
that authentication succeeds does it hash the UTF-8 record and follow the six
side-constrained proof siblings to check that the reconstructed root equals the
authenticated root.

In the comparison, peers exchange `(tree_size, root, signature)` once, verify
both signatures with the same pinned key, and alert if equal sizes authenticate
different roots.
