#!/usr/bin/env python3
"""Generate deterministic synthetic output sets and their manifests."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np


SCHEMA_VERSION = "1.0.0"
GENERATOR = "synthetic-cross-file-validation-v1"
CSV_COLUMNS: dict[str, list[str]] = {
    "observations.csv": ["seed_id", "observation_id", "value"],
    "per_seed.csv": ["seed_id", "n", "mean", "sample_std"],
    "summary.csv": ["seed_count", "total_observations", "grand_mean"],
    "heatmap_cells.csv": ["row_index", "seed_id", "metric", "value"],
}
MATRIX_FILE = "heatmap_matrix.npy"
DATA_FILES = [*CSV_COLUMNS, MATRIX_FILE]
RULES = [f"R{i}" for i in range(1, 9)]


def _write_csv(path: Path, columns: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _csv_row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.reader(handle)) - 1


def refresh_manifest(output_dir: Path) -> dict[str, Any]:
    """Rebuild all manifest metadata after content is complete."""
    entries: list[dict[str, Any]] = []
    for filename, columns in CSV_COLUMNS.items():
        path = output_dir / filename
        entries.append(
            {
                "path": filename,
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
                "format": "csv",
                "columns": columns,
                "data_rows": _csv_row_count(path),
            }
        )

    matrix_path = output_dir / MATRIX_FILE
    matrix = np.load(matrix_path, allow_pickle=False)
    entries.append(
        {
            "path": MATRIX_FILE,
            "sha256": _sha256(matrix_path),
            "size_bytes": matrix_path.stat().st_size,
            "format": "npy",
            "dtype": matrix.dtype.str,
            "shape": list(matrix.shape),
        }
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR,
        "files": entries,
        "relational_rules": RULES,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def generate_output_set(output_dir: Path, run_identifier: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    observation_rows: list[dict[str, str]] = []
    values_by_seed: dict[str, list[float]] = {}

    for seed_index in range(20):
        seed_id = f"S{seed_index:03d}"
        rng = np.random.default_rng(1_000_000 + 1_000 * run_identifier + seed_index)
        persisted_values = [
            float(f"{value:.12f}")
            for value in rng.normal(
                loc=seed_index / 10, scale=1 + 0.02 * seed_index, size=50
            )
        ]
        values_by_seed[seed_id] = persisted_values
        for observation_index, value in enumerate(persisted_values):
            observation_rows.append(
                {
                    "seed_id": seed_id,
                    "observation_id": f"O{observation_index:03d}",
                    "value": f"{value:.12f}",
                }
            )

    _write_csv(
        output_dir / "observations.csv", CSV_COLUMNS["observations.csv"], observation_rows
    )

    per_seed_rows: list[dict[str, str]] = []
    persisted_per_seed: list[tuple[str, int, str, str]] = []
    for seed_id in sorted(values_by_seed):
        values = values_by_seed[seed_id]
        n = len(values)
        mean = math.fsum(values) / n
        sample_std = math.sqrt(math.fsum((x - mean) ** 2 for x in values) / (n - 1))
        mean_text = f"{mean:.12f}"
        std_text = f"{sample_std:.12f}"
        persisted_per_seed.append((seed_id, n, mean_text, std_text))
        per_seed_rows.append(
            {"seed_id": seed_id, "n": str(n), "mean": mean_text, "sample_std": std_text}
        )
    _write_csv(output_dir / "per_seed.csv", CSV_COLUMNS["per_seed.csv"], per_seed_rows)

    all_values = [value for seed_id in sorted(values_by_seed) for value in values_by_seed[seed_id]]
    summary_rows = [
        {
            "seed_count": "20",
            "total_observations": "1000",
            "grand_mean": f"{math.fsum(all_values) / 1000:.12f}",
        }
    ]
    _write_csv(output_dir / "summary.csv", CSV_COLUMNS["summary.csv"], summary_rows)

    heatmap_rows: list[dict[str, str]] = []
    matrix_rows: list[list[float]] = []
    for row_index, (seed_id, n, mean_text, std_text) in enumerate(persisted_per_seed):
        fields = (("n", str(n)), ("mean", mean_text), ("sample_std", std_text))
        for metric, value_text in fields:
            heatmap_rows.append(
                {
                    "row_index": str(row_index),
                    "seed_id": seed_id,
                    "metric": metric,
                    "value": value_text,
                }
            )
        matrix_rows.append([float(n), float(mean_text), float(std_text)])
    _write_csv(
        output_dir / "heatmap_cells.csv",
        CSV_COLUMNS["heatmap_cells.csv"],
        heatmap_rows,
    )
    np.save(output_dir / MATRIX_FILE, np.asarray(matrix_rows, dtype=np.float64), allow_pickle=False)
    refresh_manifest(output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--run-identifier", type=int, default=0)
    args = parser.parse_args()
    generate_output_set(args.output, args.run_identifier)


if __name__ == "__main__":
    main()
