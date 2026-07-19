#!/usr/bin/env python3
"""Independent consistency checks for experiment output artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image


ROOT = Path(__file__).resolve().parent
Z = 1.959963984540054


def wilson(successes: int, trials: int) -> tuple[float, float]:
    proportion = successes / trials
    denominator = 1 + Z**2 / trials
    center = (proportion + Z**2 / (2 * trials)) / denominator
    half = Z * np.sqrt(proportion * (1 - proportion) / trials + Z**2 / (4 * trials**2)) / denominator
    return float(center - half), float(center + half)


def main() -> None:
    with (ROOT / "results.json").open(encoding="utf-8") as handle:
        results = json.load(handle)
    records = pd.read_csv(ROOT / "selection_records.csv")
    fixtures = pd.read_csv(ROOT / "fixture_summary.csv")

    assert isinstance(results, dict)
    assert all(isinstance(value, (str, int, float, bool)) for value in results.values())
    assert len(records) == 80_000
    assert len(fixtures) == 40
    assert set(records["method"]) == {"first_encountered", "family_uniform"}
    assert records.groupby(["fixture", "method"]).size().eq(1_000).all()
    assert records["validation_accuracy"].eq(0.8).all()
    assert records.isna().sum().sum() == 0

    baseline = records[records["method"] == "first_encountered"]
    comparison = records[records["method"] == "family_uniform"]
    baseline_count = int(baseline["selected_family"].eq("A").sum())
    comparison_count = int(comparison["selected_family"].eq("A").sum())
    baseline_frequency = baseline_count / 40_000
    comparison_frequency = comparison_count / 40_000
    baseline_ci = wilson(baseline_count, 40_000)
    comparison_ci = wilson(comparison_count, 40_000)
    effect = baseline_frequency - comparison_frequency
    odds_ratio = (
        baseline_frequency
        / (1 - baseline_frequency)
        / (comparison_frequency / (1 - comparison_frequency))
    )

    assert np.isclose(results["baseline_family_a_frequency"], baseline_frequency)
    assert np.isclose(results["comparison_family_a_frequency"], comparison_frequency)
    assert np.isclose(results["baseline_family_a_wilson_95_low"], baseline_ci[0])
    assert np.isclose(results["baseline_family_a_wilson_95_high"], baseline_ci[1])
    assert np.isclose(results["comparison_family_a_wilson_95_low"], comparison_ci[0])
    assert np.isclose(results["comparison_family_a_wilson_95_high"], comparison_ci[1])
    assert np.isclose(results["grid_cardinality_effect"], effect)
    assert np.isclose(results["selection_odds_ratio"], odds_ratio)

    identifier_frequencies = baseline["selected_identifier"].value_counts(normalize=True)
    expected_identifiers = {f"A_{index}" for index in range(8)} | {"B_0"}
    assert set(identifier_frequencies.index) == expected_identifiers
    for identifier in sorted(expected_identifiers):
        assert np.isclose(
            results[f"baseline_identifier_frequency_{identifier.lower()}"],
            identifier_frequencies.loc[identifier],
        )
    instability = baseline_frequency**2 - sum(identifier_frequencies[f"A_{index}"] ** 2 for index in range(8))
    assert np.isclose(results["identifier_only_instability"], instability)

    recomputed_fixture = records.pivot_table(
        index="fixture", columns="method", values="heldout_accuracy", aggfunc="mean"
    )
    recomputed_shift = recomputed_fixture["first_encountered"] - recomputed_fixture["family_uniform"]
    assert np.allclose(
        fixtures.sort_values("fixture")["baseline_minus_comparison_heldout_shift"],
        recomputed_shift.sort_index(),
    )
    assert np.isclose(results["heldout_shift_overall_signed_mean"], recomputed_shift.mean())
    assert np.isclose(results["heldout_shift_overall_mean_absolute"], recomputed_shift.abs().mean())

    supported = (
        bool(results["fixture_integrity_assertions_passed"])
        and 0.85 <= baseline_frequency <= 0.92
        and 0.47 <= comparison_frequency <= 0.53
        and effect >= 0.32
    )
    assert results["hypothesis_supported"] is supported
    assert results["decision"] == ("SUPPORTED" if supported else "REFUTED")

    figure_path = ROOT / "figures" / "selection_frequency.png"
    assert figure_path.is_file()
    with Image.open(figure_path) as image:
        assert image.format == "PNG"
        assert image.width >= 1_600 and image.height >= 700
        dimensions = f"{image.width}x{image.height}"

    print(
        "Validation passed: 80,000 records, 40 fixture summaries, flat scalar JSON, "
        f"recomputed decision {results['decision']}, and {dimensions} PNG."
    )


if __name__ == "__main__":
    main()
