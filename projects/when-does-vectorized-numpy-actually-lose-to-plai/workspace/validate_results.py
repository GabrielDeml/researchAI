#!/usr/bin/env python3
"""Independently validate the completed benchmark artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parent
MASK_TYPES = ("random_50pct", "all_true")
K_VALUES = tuple(range(1, 21))
ROUNDS = 15
THRESHOLD = 1.05


def crossover(speedups: list[float]) -> int | None:
    for index, k in enumerate(K_VALUES):
        if all(value >= THRESHOLD for value in speedups[index:]):
            return k
    return None


def main() -> None:
    environment = json.loads((ROOT / "environment.json").read_text(encoding="utf-8"))
    results = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))
    summary = json.loads((ROOT / "summary.json").read_text(encoding="utf-8"))
    with (ROOT / "results.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert environment["machine"] == "arm64"
    assert environment["python_version"].startswith(("3.11.", "3.12."))
    assert environment["numpy_version"] == "2.1.3"
    assert environment["matplotlib_version"] == "3.9.2"
    assert len(rows) == ROUNDS * len(K_VALUES) * len(MASK_TYPES) * 2 == 1200
    assert all(not isinstance(value, (dict, list)) for value in results.values())

    # Rows for each visited condition must be adjacent and contain both implementations.
    for offset in range(0, len(rows), 2):
        first, second = rows[offset : offset + 2]
        assert (first["round"], first["k"], first["mask_type"]) == (
            second["round"],
            second["k"],
            second["mask_type"],
        )
        assert {first["implementation"], second["implementation"]} == {"numpy", "python"}

    lookup = {
        (int(row["round"]), row["mask_type"], int(row["k"]), row["implementation"]): float(
            row["ns_per_call"]
        )
        for row in rows
    }
    paired = np.empty((len(MASK_TYPES), len(K_VALUES), ROUNDS), dtype=np.float64)
    observed_crossovers: dict[str, int | None] = {}
    for mask_index, mask_type in enumerate(MASK_TYPES):
        speedups = []
        for k_index, k in enumerate(K_VALUES):
            ratios = [
                lookup[(round_index, mask_type, k, "python")]
                / lookup[(round_index, mask_type, k, "numpy")]
                for round_index in range(ROUNDS)
            ]
            paired[mask_index, k_index] = ratios
            median = float(np.median(ratios))
            assert np.isclose(median, results[f"{mask_type}_k{k}_median_speedup"], rtol=1e-14)
            speedups.append(median)
        observed_crossovers[mask_type] = crossover(speedups)

    bootstrap_rng = np.random.default_rng(271828)
    sampled_rounds = bootstrap_rng.integers(0, ROUNDS, size=(10_000, ROUNDS))
    bootstrap_speedups = np.empty((10_000, len(MASK_TYPES), len(K_VALUES)))
    for mask_index in range(len(MASK_TYPES)):
        for k_index in range(len(K_VALUES)):
            bootstrap_speedups[:, mask_index, k_index] = np.median(
                paired[mask_index, k_index, sampled_rounds], axis=1
            )
            mask_type = MASK_TYPES[mask_index]
            lower, upper = np.percentile(
                bootstrap_speedups[:, mask_index, k_index], [2.5, 97.5]
            )
            assert np.isclose(lower, results[f"{mask_type}_k{K_VALUES[k_index]}_bootstrap_p2_5"])
            assert np.isclose(upper, results[f"{mask_type}_k{K_VALUES[k_index]}_bootstrap_p97_5"])

    bootstrap_crossovers = np.full((10_000, len(MASK_TYPES)), -1, dtype=np.int16)
    for replicate in range(10_000):
        for mask_index in range(len(MASK_TYPES)):
            value = crossover(bootstrap_speedups[replicate, mask_index])
            if value is not None:
                bootstrap_crossovers[replicate, mask_index] = value
    finite = np.all(bootstrap_crossovers >= 0, axis=1)
    differences = bootstrap_crossovers[finite, 1] - bootstrap_crossovers[finite, 0]
    difference_percentiles = np.percentile(differences, [2.5, 50.0, 97.5])
    assert int(np.count_nonzero(finite)) == results["bootstrap_both_finite_count"]
    assert np.isclose(np.mean(finite), results["bootstrap_both_finite_fraction"])
    assert np.allclose(
        difference_percentiles,
        [
            results["bootstrap_difference_p2_5"],
            results["bootstrap_difference_p50"],
            results["bootstrap_difference_p97_5"],
        ],
    )

    expected_random = observed_crossovers["random_50pct"]
    expected_all_true = observed_crossovers["all_true"]
    serialized_random = expected_random if expected_random is not None else "not_observed"
    serialized_all_true = (
        expected_all_true if expected_all_true is not None else "not_observed"
    )
    assert serialized_random == results["crossover_random_bin"]
    assert serialized_all_true == results["crossover_all_true_bin"]
    difference = (
        expected_all_true - expected_random
        if expected_random is not None and expected_all_true is not None
        else None
    )
    serialized_difference = difference if difference is not None else "not_observed"
    assert serialized_difference == results["crossover_bin_difference_all_true_minus_random"]
    interval_low = results["bootstrap_difference_p2_5"]
    expected_supported = bool(
        difference is not None
        and difference >= 1
        and float(results["bootstrap_both_finite_fraction"]) >= 0.95
        and isinstance(interval_low, (int, float))
        and interval_low >= 1
    )
    expected_decision = "supported" if expected_supported else "refuted"
    assert summary["decision"] == results["decision"] == expected_decision

    expected_checksum = 0.0
    for k in K_VALUES:
        n = 2**k
        data_rng = np.random.default_rng(20000 + k)
        a = np.ascontiguousarray(data_rng.standard_normal(n, dtype=np.float64))
        b = np.ascontiguousarray(data_rng.standard_normal(n, dtype=np.float64))
        random_mask = np.zeros(n, dtype=np.bool_)
        random_mask[: n // 2] = True
        np.random.default_rng(10000 + k).shuffle(random_mask)
        all_true = np.ones(n, dtype=np.bool_)
        for mask in (random_mask, all_true):
            selected = np.where(mask, a, b)
            expected_checksum += 2 * ROUNDS * (float(selected[0]) + float(selected[-1]))
    # The benchmark accumulates contributions in shuffled timing order, so allow
    # only the few ulps attributable to a different floating-point sum order.
    assert np.isclose(expected_checksum, results["checksum"], rtol=0.0, atol=1e-11)

    with Image.open(ROOT / "figures" / "crossover_where.png") as image:
        assert image.format == "PNG"
        assert image.size == (2500, 1500)
        dpi = image.info.get("dpi")
        assert dpi is not None and abs(dpi[0] - 200.0) < 0.1 and abs(dpi[1] - 200.0) < 0.1

    print(
        "Validation passed: 1200 paired timing rows, flat scalar results.json, "
        "independently reproduced checksum/bootstrap/crossovers/D/decision, and a 200-DPI PNG."
    )


if __name__ == "__main__":
    main()
