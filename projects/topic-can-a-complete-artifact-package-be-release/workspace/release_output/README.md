# Complete synthetic artifact package

This repository generates deterministic synthetic observations, four related CSV
tables, a NumPy heatmap source matrix, schema-versioned SHA-256 manifests, 20
clean regeneration cases, and 40 independently checksum-refreshed cross-file
mutants. It compares integrity-only validation with rules R1–R8 for relational
consistency. Python 3.11 or newer is required. Matplotlib uses its noninteractive
`Agg` backend, and the experiment performs no runtime network access; dependency
installation is the only operation that may access the network.

The sole reproduction command is:

```sh
make reproduce
```

That target creates `.venv` when absent, installs the exact versions in
`requirements.lock`, runs the experiment, and writes the detailed evidence to
`results/results.json`. The required flat headline metrics are written to
`results.json`, and the 1600×900 detection figure is written to both
`results/detection_summary.png` and `figures/detection_summary.png`.

`release_output/` is a directly usable release package. It contains a byte-for-byte
copy of the canonical `clean_00` outputs and manifest, together with the source,
schema, lock file, Makefile, and these reproduction instructions.

