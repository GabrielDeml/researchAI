#!/usr/bin/env python3
"""Validate artifact sets at integrity-only or relational depth."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator

from .generate import CSV_COLUMNS, DATA_FILES, MATRIX_FILE, RULES


ABS_TOLERANCE = 5e-10


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_csv(path: Path, expected_columns: list[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != expected_columns:
            raise ValueError(f"{path.name}: columns {reader.fieldnames!r} != {expected_columns!r}")
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"{path.name}: malformed row")
    return rows


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("numeric value is not finite")
    return result


def _parse_csv_types(filename: str, rows: list[dict[str, str]]) -> None:
    if filename == "observations.csv":
        for row in rows:
            if not row["seed_id"] or not row["observation_id"]:
                raise ValueError("empty observation identifier")
            _finite_float(row["value"])
    elif filename == "per_seed.csv":
        for row in rows:
            if not row["seed_id"]:
                raise ValueError("empty seed identifier")
            int(row["n"])
            _finite_float(row["mean"])
            _finite_float(row["sample_std"])
    elif filename == "summary.csv":
        for row in rows:
            int(row["seed_count"])
            int(row["total_observations"])
            _finite_float(row["grand_mean"])
    elif filename == "heatmap_cells.csv":
        for row in rows:
            int(row["row_index"])
            if not row["seed_id"] or not row["metric"]:
                raise ValueError("empty heatmap identifier")
            _finite_float(row["value"])


def checksum_only(output_dir: Path, schema_path: Path) -> dict[str, Any]:
    start = time.perf_counter()
    schema_pass = False
    parsing_pass = False
    checksum_verification_pass = False
    errors: list[str] = []
    manifest: dict[str, Any] | None = None

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        validation_errors = sorted(
            Draft202012Validator(schema).iter_errors(manifest), key=lambda error: list(error.path)
        )
        if validation_errors:
            errors.extend(f"manifest schema: {error.message}" for error in validation_errors)
        else:
            schema_pass = True
    except Exception as exc:  # invalid schema or unreadable manifest
        errors.append(f"manifest schema: {exc}")

    parsed: dict[str, Any] = {}
    checksum_results: list[bool] = []
    if schema_pass and manifest is not None:
        try:
            entries = manifest["files"]
            paths = [entry["path"] for entry in entries]
            if len(paths) != len(set(paths)) or set(paths) != set(DATA_FILES):
                raise ValueError("manifest must declare each canonical data file exactly once")
            for entry in entries:
                filename = entry["path"]
                path = output_dir / filename
                if not path.is_file():
                    raise ValueError(f"missing file: {filename}")
                checksum_results.append(
                    path.stat().st_size == entry["size_bytes"] and _sha256(path) == entry["sha256"]
                )
                if entry["format"] == "csv":
                    if entry["columns"] != CSV_COLUMNS[filename]:
                        raise ValueError(f"{filename}: noncanonical declared columns")
                    rows = _read_csv(path, entry["columns"])
                    _parse_csv_types(filename, rows)
                    if len(rows) != entry["data_rows"]:
                        raise ValueError(f"{filename}: declared row count mismatch")
                    parsed[filename] = rows
                elif entry["format"] == "npy":
                    if filename != MATRIX_FILE:
                        raise ValueError(f"unexpected NumPy file: {filename}")
                    matrix = np.load(path, allow_pickle=False)
                    if matrix.dtype.str != entry["dtype"]:
                        raise ValueError(f"{filename}: declared dtype mismatch")
                    if list(matrix.shape) != entry["shape"]:
                        raise ValueError(f"{filename}: declared shape mismatch")
                    if not np.isfinite(matrix).all():
                        raise ValueError(f"{filename}: non-finite value")
                    parsed[filename] = matrix
                else:
                    raise ValueError(f"unsupported format: {entry['format']}")
            parsing_pass = True
            checksum_verification_pass = all(checksum_results) and len(checksum_results) == len(DATA_FILES)
            if not checksum_verification_pass:
                errors.append("one or more size/SHA-256 checks failed")
        except Exception as exc:
            errors.append(f"parse: {exc}")

    passed = schema_pass and parsing_pass and checksum_verification_pass
    return {
        "mode": "checksum_only",
        "schema_pass": schema_pass,
        "parsing_pass": parsing_pass,
        "checksum_verification_pass": checksum_verification_pass,
        "checksum_only_pass": passed,
        "relational_pass": None,
        "failed_rules": [],
        "errors": errors,
        "elapsed_seconds": time.perf_counter() - start,
        "_parsed": parsed,
    }


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=ABS_TOLERANCE)


def _evaluate_rules(parsed: dict[str, Any]) -> list[str]:
    observations = parsed["observations.csv"]
    per_seed = parsed["per_seed.csv"]
    summary = parsed["summary.csv"]
    heatmap = parsed["heatmap_cells.csv"]
    matrix = parsed[MATRIX_FILE]
    failures: set[str] = set()

    observation_keys = [(row["seed_id"], row["observation_id"]) for row in observations]
    values_by_seed: dict[str, list[float]] = {}
    for row in observations:
        values_by_seed.setdefault(row["seed_id"], []).append(float(row["value"]))
    if len(observation_keys) != len(set(observation_keys)) or any(
        not values for values in values_by_seed.values()
    ):
        failures.add("R1")

    per_seed_ids = [row["seed_id"] for row in per_seed]
    per_seed_by_id = {row["seed_id"]: row for row in per_seed}
    if (
        set(per_seed_ids) != set(values_by_seed)
        or len(per_seed_ids) != len(set(per_seed_ids))
        or len(per_seed_by_id) != len(values_by_seed)
    ):
        failures.add("R2")

    for seed_id, row in per_seed_by_id.items():
        if seed_id not in values_by_seed or int(row["n"]) != len(values_by_seed[seed_id]):
            failures.add("R3")
            break

    for seed_id, row in per_seed_by_id.items():
        values = values_by_seed.get(seed_id)
        if not values:
            failures.add("R4")
            break
        mean = math.fsum(values) / len(values)
        if len(values) < 2:
            failures.add("R4")
            break
        sample_std = math.sqrt(
            math.fsum((value - mean) ** 2 for value in values) / (len(values) - 1)
        )
        if not _close(float(row["mean"]), mean) or not _close(
            float(row["sample_std"]), sample_std
        ):
            failures.add("R4")
            break

    if len(summary) != 1:
        failures.add("R5")
    else:
        summary_row = summary[0]
        all_values = [float(row["value"]) for row in observations]
        direct_mean = math.fsum(all_values) / len(all_values) if all_values else math.nan
        if (
            int(summary_row["seed_count"]) != len(values_by_seed)
            or int(summary_row["total_observations"]) != len(observations)
            or not _close(float(summary_row["grand_mean"]), direct_mean)
        ):
            failures.add("R5")

    sorted_seed_ids = sorted(per_seed_ids)
    expected_pairs = {
        (row_index, seed_id, metric)
        for row_index, seed_id in enumerate(sorted_seed_ids)
        for metric in ("n", "mean", "sample_std")
    }
    actual_pairs = [
        (int(row["row_index"]), row["seed_id"], row["metric"]) for row in heatmap
    ]
    if len(actual_pairs) != len(expected_pairs) or set(actual_pairs) != expected_pairs:
        failures.add("R6")

    for row in heatmap:
        per_seed_row = per_seed_by_id.get(row["seed_id"])
        if per_seed_row is None or row["metric"] not in ("n", "mean", "sample_std"):
            failures.add("R7")
            break
        expected_value = float(per_seed_row[row["metric"]])
        if not _close(float(row["value"]), expected_value):
            failures.add("R7")
            break

    if matrix.shape != (len(per_seed_ids), 3):
        failures.add("R8")
    else:
        heatmap_by_cell = {
            (int(row["row_index"]), row["metric"]): float(row["value"]) for row in heatmap
        }
        for row_index in range(len(per_seed_ids)):
            for column_index, metric in enumerate(("n", "mean", "sample_std")):
                expected_value = heatmap_by_cell.get((row_index, metric))
                if expected_value is None or not _close(
                    float(matrix[row_index, column_index]), expected_value
                ):
                    failures.add("R8")
                    break
            if "R8" in failures:
                break

    return [rule for rule in RULES if rule in failures]


def validate(output_dir: Path, schema_path: Path, mode: str) -> dict[str, Any]:
    start = time.perf_counter()
    result = checksum_only(output_dir, schema_path)
    parsed = result.pop("_parsed")
    if mode == "checksum_only":
        result["elapsed_seconds"] = time.perf_counter() - start
        return result
    if mode != "relational":
        raise ValueError(f"unsupported validation mode: {mode}")
    failed_rules = _evaluate_rules(parsed) if result["checksum_only_pass"] else []
    result.update(
        {
            "mode": "relational",
            "relational_pass": result["checksum_only_pass"] and not failed_rules,
            "failed_rules": failed_rules,
            "elapsed_seconds": time.perf_counter() - start,
        }
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--schema", type=Path, default=Path("manifest.schema.json"))
    parser.add_argument("--mode", choices=("checksum_only", "relational"), default="relational")
    args = parser.parse_args()
    result = validate(args.output, args.schema, args.mode)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if (result["relational_pass"] if args.mode == "relational" else result["checksum_only_pass"]) else 1)


if __name__ == "__main__":
    main()
