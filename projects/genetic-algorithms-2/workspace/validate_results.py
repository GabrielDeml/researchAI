#!/usr/bin/env python3
"""Independently validate experiment artifacts from run_records.csv."""

from __future__ import annotations

import csv
import json
import struct
from collections import Counter
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parent
BUDGET = 20_000
FAILURE_SCORE = BUDGET + 1
EXPECTED_SEEDS = set(range(30))


def as_bool(value: str) -> bool:
    if value not in {"True", "False"}:
        raise AssertionError(f"Invalid Boolean CSV field: {value!r}")
    return value == "True"


def main() -> None:
    with (ROOT / "run_records.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    with (ROOT / "summary.json").open(encoding="utf-8") as handle:
        summary = json.load(handle)
    with (ROOT / "results.json").open(encoding="utf-8") as handle:
        results = json.load(handle)

    assert summary == results
    assert all(not isinstance(value, (dict, list)) for value in results.values())
    assert len(rows) == 60
    assert Counter(row["algorithm"] for row in rows) == {
        "muplus1": 30,
        "generational": 30,
    }

    by_algorithm: dict[str, dict[int, dict[str, str]]] = {}
    for algorithm in ("muplus1", "generational"):
        group = {int(row["seed"]): row for row in rows if row["algorithm"] == algorithm}
        assert set(group) == EXPECTED_SEEDS
        by_algorithm[algorithm] = group

        total_attempts = 0
        total_misses = 0
        for row in group.values():
            reached = as_bool(row["target_reached"])
            init_misses = int(row["initialization_misses"])
            offspring_attempts = int(row["offspring_attempts"])
            offspring_misses = int(row["offspring_cache_misses"])
            assert 0 <= init_misses <= 64
            assert 0 <= offspring_misses <= offspring_attempts
            assert init_misses + offspring_misses <= BUDGET
            assert reached or init_misses + offspring_misses == BUDGET

            target_miss = int(row["target_C_miss"]) if row["target_C_miss"] else None
            target_attempt = (
                int(row["target_C_attempt"]) if row["target_C_attempt"] else None
            )
            expected_s_miss = (
                target_miss
                if reached and target_miss is not None and target_miss <= BUDGET
                else FAILURE_SCORE
            )
            expected_s_attempt = (
                target_attempt
                if reached and target_attempt is not None and target_attempt <= BUDGET
                else FAILURE_SCORE
            )
            assert int(row["S_miss"]) == expected_s_miss
            assert int(row["S_attempt"]) == expected_s_attempt
            if offspring_misses:
                assert abs(
                    float(row["individual_offspring_ratio"])
                    - offspring_attempts / offspring_misses
                ) < 1e-12
            else:
                assert row["individual_offspring_ratio"] == ""
            total_attempts += offspring_attempts
            total_misses += offspring_misses

        expected_ratio = total_attempts / total_misses
        assert abs(summary[f"R_{algorithm}"] - expected_ratio) < 1e-12

    d_miss = []
    d_attempt = []
    for seed in sorted(EXPECTED_SEEDS):
        mu = by_algorithm["muplus1"][seed]
        gen = by_algorithm["generational"][seed]
        d_miss.append(int(gen["S_miss"]) - int(mu["S_miss"]))
        d_attempt.append(int(gen["S_attempt"]) - int(mu["S_attempt"]))
    assert summary["A_miss"] == median(d_miss)
    assert summary["A_attempt"] == median(d_attempt)

    expected_conditions = {
        "condition_R_muplus1_ge_1_8": summary["R_muplus1"] >= 1.8,
        "condition_R_generational_le_1_2": summary["R_generational"] <= 1.2,
        "condition_A_miss_gt_0": summary["A_miss"] > 0,
        "condition_A_attempt_le_half_A_miss": (
            summary["A_attempt"] <= 0.5 * summary["A_miss"]
        ),
    }
    for key, value in expected_conditions.items():
        assert summary[key] is value
    assert summary["hypothesis_supported"] is all(expected_conditions.values())
    assert summary["decision"] == (
        "supported" if summary["hypothesis_supported"] else "refuted"
    )

    figure_path = ROOT / "figures" / "royal_road_accounting.png"
    with figure_path.open("rb") as handle:
        assert handle.read(8) == b"\x89PNG\r\n\x1a\n"
        length = struct.unpack(">I", handle.read(4))[0]
        assert handle.read(4) == b"IHDR" and length == 13
        width, height = struct.unpack(">II", handle.read(8))
    assert (width, height) == (1600, 700)

    print(
        "Validation passed: 60 rows, flat matching JSON summaries, "
        "recomputed metrics/decision, and 1600x700 PNG."
    )


if __name__ == "__main__":
    main()
