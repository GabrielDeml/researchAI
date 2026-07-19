#!/usr/bin/env python3
"""Apply independent format-valid cross-file mutations and refresh manifests."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from .generate import CSV_COLUMNS, refresh_manifest


MUTATION_CLASSES = {
    "M1": "raw_value_only",
    "M2": "raw_seed_only",
    "M3": "per_seed_count_only",
    "M4": "per_seed_mean_only",
    "M5": "summary_only",
    "M6": "heatmap_csv_only",
    "M7": "matrix_only",
    "M8": "coordinated_derived_files",
}


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    columns = CSV_COLUMNS[path.name]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _target_seed(index: int) -> str:
    if index not in range(5):
        raise ValueError("target index must be between 0 and 4")
    return f"S00{index}"


def apply_mutation(output_dir: Path, mutation_class: str, target_index: int) -> None:
    seed_id = _target_seed(target_index)
    observation_id = f"O00{target_index}"

    if mutation_class in ("M1", "M2"):
        path = output_dir / "observations.csv"
        rows = _read_rows(path)
        matched = 0
        for row in rows:
            if row["seed_id"] == seed_id and row["observation_id"] == observation_id:
                matched += 1
                if mutation_class == "M1":
                    row["value"] = f"{float(row['value']) + 5.0 + target_index / 10:.12f}"
                else:
                    row["seed_id"] = f"S9{target_index}0"
        if matched != 1:
            raise RuntimeError(f"expected one observation target, found {matched}")
        _write_rows(path, rows)

    elif mutation_class in ("M3", "M4"):
        path = output_dir / "per_seed.csv"
        rows = _read_rows(path)
        matched = 0
        for row in rows:
            if row["seed_id"] == seed_id:
                matched += 1
                if mutation_class == "M3":
                    row["n"] = str(int(row["n"]) + 3)
                else:
                    row["mean"] = f"{float(row['mean']) + 0.5 + 0.1 * target_index:.12f}"
        if matched != 1:
            raise RuntimeError(f"expected one per-seed target, found {matched}")
        _write_rows(path, rows)

    elif mutation_class == "M5":
        path = output_dir / "summary.csv"
        rows = _read_rows(path)
        if len(rows) != 1:
            raise RuntimeError("summary must contain one row")
        rows[0]["grand_mean"] = (
            f"{float(rows[0]['grand_mean']) + 0.25 + 0.05 * target_index:.12f}"
        )
        _write_rows(path, rows)

    elif mutation_class == "M6":
        path = output_dir / "heatmap_cells.csv"
        rows = _read_rows(path)
        matched = 0
        for row in rows:
            if row["seed_id"] == seed_id and row["metric"] == "mean":
                matched += 1
                row["value"] = f"{float(row['value']) + 0.75 + 0.1 * target_index:.12f}"
        if matched != 1:
            raise RuntimeError(f"expected one heatmap target, found {matched}")
        _write_rows(path, rows)

    elif mutation_class == "M7":
        path = output_dir / "heatmap_matrix.npy"
        matrix = np.load(path, allow_pickle=False)
        matrix[target_index, 2] += 1.0 + 0.1 * target_index
        np.save(path, matrix.astype(np.float64, copy=False), allow_pickle=False)

    elif mutation_class == "M8":
        delta = 0.6 + 0.1 * target_index
        per_seed_path = output_dir / "per_seed.csv"
        per_seed_rows = _read_rows(per_seed_path)
        per_seed_matches = 0
        for row in per_seed_rows:
            if row["seed_id"] == seed_id:
                per_seed_matches += 1
                row["mean"] = f"{float(row['mean']) + delta:.12f}"
        if per_seed_matches != 1:
            raise RuntimeError(f"expected one per-seed target, found {per_seed_matches}")
        _write_rows(per_seed_path, per_seed_rows)

        heatmap_path = output_dir / "heatmap_cells.csv"
        heatmap_rows = _read_rows(heatmap_path)
        heatmap_matches = 0
        for row in heatmap_rows:
            if row["seed_id"] == seed_id and row["metric"] == "mean":
                heatmap_matches += 1
                row["value"] = f"{float(row['value']) + delta:.12f}"
        if heatmap_matches != 1:
            raise RuntimeError(f"expected one heatmap target, found {heatmap_matches}")
        _write_rows(heatmap_path, heatmap_rows)

        matrix_path = output_dir / "heatmap_matrix.npy"
        matrix = np.load(matrix_path, allow_pickle=False)
        matrix[target_index, 1] += delta
        np.save(matrix_path, matrix.astype(np.float64, copy=False), allow_pickle=False)
    else:
        raise ValueError(f"unknown mutation class: {mutation_class}")

    refresh_manifest(output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("mutation_class", choices=tuple(MUTATION_CLASSES))
    parser.add_argument("target_index", type=int)
    args = parser.parse_args()
    apply_mutation(args.output, args.mutation_class, args.target_index)


if __name__ == "__main__":
    main()
