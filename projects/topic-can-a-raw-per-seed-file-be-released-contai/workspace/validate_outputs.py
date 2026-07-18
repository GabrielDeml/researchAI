#!/usr/bin/env python3
"""Validate the experiment's serialized outputs and cross-file audit metrics."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import struct
from pathlib import Path

from experiment import AUDIT_COLUMNS, HEADER, METRIC_FIELDS, SEEDS, validate_runtime


WORKSPACE = Path(__file__).resolve().parent
CONDITIONS = (
    "independent_forward",
    "independent_reverse",
    "shared_forward",
    "shared_reverse",
)
RATIO_PATTERN = re.compile(r"^(?:0|[1-9][0-9]*)\.[0-9]{12}$")
INTEGER_PATTERN = re.compile(r"^(?:0|[1-9][0-9]*)$")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_csv(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    raw.decode("utf-8")
    assert raw.endswith(b"\n"), f"{path.name} lacks a final Unix newline"
    assert b"\r" not in raw, f"{path.name} contains non-Unix newlines"
    assert len(raw.splitlines()) == len(SEEDS) + 1

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == HEADER
        rows = list(reader)

    assert [row["seed"] for row in rows] == [str(seed) for seed in SEEDS]
    for row in rows:
        assert INTEGER_PATTERN.fullmatch(row["seed"])
        for algorithm in ("generational", "steady_state"):
            for field in METRIC_FIELDS:
                value = row[f"{algorithm}_{field}"]
                pattern = RATIO_PATTERN if field == "duplicate_ratio" else INTEGER_PATTERN
                assert pattern.fullmatch(value), f"bad serialization for {algorithm}_{field}: {value}"

            prefix = f"{algorithm}_"
            initialization_accepted = int(row[prefix + "initialization_accepted"])
            initialization_attempts = int(row[prefix + "initialization_attempts"])
            initialization_misses = int(row[prefix + "initialization_misses"])
            initialization_failed = int(row[prefix + "initialization_failed"])
            offspring_accepted = int(row[prefix + "offspring_accepted"])
            offspring_attempts = int(row[prefix + "offspring_attempts"])
            offspring_misses = int(row[prefix + "offspring_misses"])
            offspring_failed = int(row[prefix + "offspring_failed"])

            assert int(row[prefix + "initialization_target"]) == 64
            assert int(row[prefix + "offspring_target"]) == 2_048
            assert initialization_attempts == initialization_accepted + initialization_misses
            assert offspring_attempts == offspring_accepted + offspring_misses
            assert initialization_attempts <= 10_000
            assert offspring_attempts <= 100_000
            assert initialization_failed == int(initialization_accepted < 64)
            assert offspring_failed == int(offspring_accepted < 2_048)
            assert initialization_failed in (0, 1) and offspring_failed in (0, 1)
            assert 0 <= int(row[prefix + "best_score"]) <= 64

            denominator = initialization_attempts + offspring_attempts
            ratio = (
                (initialization_misses + offspring_misses) / denominator
                if denominator
                else 0.0
            )
            assert row[prefix + "duplicate_ratio"] == format(ratio, ".12f")
            if initialization_failed:
                assert offspring_attempts == offspring_misses == offspring_accepted == 0
                assert offspring_failed == 1

    return rows


def difference_counts(
    forward: list[dict[str, str]], reverse: list[dict[str, str]]
) -> tuple[dict[str, int], int]:
    counts = {
        column: sum(left[column] != right[column] for left, right in zip(forward, reverse))
        for column in AUDIT_COLUMNS
    }
    union_count = sum(
        any(left[column] != right[column] for column in AUDIT_COLUMNS)
        for left, right in zip(forward, reverse)
    )
    return counts, union_count


def main() -> None:
    validate_runtime()
    rows_by_condition = {
        condition: validate_csv(WORKSPACE / f"{condition}.csv") for condition in CONDITIONS
    }
    audit = json.loads((WORKSPACE / "audit_metrics.json").read_text(encoding="utf-8"))
    results = json.loads((WORKSPACE / "results.json").read_text(encoding="utf-8"))
    assert isinstance(results, dict) and all(
        isinstance(value, (bool, float, int, str)) for value in results.values()
    )

    for mode in ("independent", "shared"):
        forward_path = WORKSPACE / f"{mode}_forward.csv"
        reverse_path = WORKSPACE / f"{mode}_reverse.csv"
        hashes = audit["comparison_hashes"][mode]
        assert hashes["forward_sha256"] == digest(forward_path)
        assert hashes["reverse_sha256"] == digest(reverse_path)
        assert hashes["equal"] == (digest(forward_path) == digest(reverse_path))

        counts, union_count = difference_counts(
            rows_by_condition[f"{mode}_forward"], rows_by_condition[f"{mode}_reverse"]
        )
        for column, count in counts.items():
            assert audit["column_changes"][mode][column] == {
                "count": count,
                "rate": count / len(SEEDS),
            }
        assert audit["union_changes"][mode] == {
            "count": union_count,
            "rate": union_count / len(SEEDS),
        }

    independent_forward_lines = (WORKSPACE / "independent_forward.csv").read_bytes().splitlines()
    independent_reverse_lines = (WORKSPACE / "independent_reverse.csv").read_bytes().splitlines()
    identical_lines = sum(
        left == right
        for left, right in zip(independent_forward_lines[1:], independent_reverse_lines[1:])
    )
    assert audit["independent_identical_line_count"] == identical_lines
    assert results["independent_identical_line_count"] == identical_lines
    assert results["hypothesis_supported"] == audit["supported"]
    assert results["decision"] == audit["decision"]

    for condition, rows in rows_by_condition.items():
        for algorithm in ("generational", "steady_state"):
            for failure_field in ("initialization_failed", "offspring_failed"):
                column = f"{algorithm}_{failure_field}"
                expected_count = sum(int(row[column]) for row in rows)
                assert audit["failure_counts"][condition][column] == expected_count
                assert results[f"{condition}_{column}_count"] == expected_count

    png = (WORKSPACE / "figures" / "order_reversal_heatmap.png").read_bytes()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", png[16:24])
    assert (width, height) == (2_880, 2_240)

    print(
        "Validated four 30-row canonical CSVs, both JSON summaries, all audit "
        "recomputations, and the 2880x2240 PNG heatmap."
    )


if __name__ == "__main__":
    main()
