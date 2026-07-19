#!/usr/bin/env python3
"""Deterministic experiment on first-encountered tie breaking.

Creates exact-validation-tie synthetic fixtures, compares a strict-greater-than
first-encountered scan against duplicate-collapsed family-uniform selection,
and writes all preregistered records, summaries, metrics, and visualization.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / ".cache"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


MASTER_SEED = 20250308
N_FIXTURES = 40
N_REPETITIONS = 1_000
N_VALIDATION = 100
N_HELDOUT = 200
Z_95 = 1.959963984540054
FIGURES_DIR = ROOT / "figures"


@dataclass(frozen=True)
class Candidate:
    identifier: str
    family: str
    semantic_signature: str
    validation_predictions: np.ndarray
    heldout_predictions: np.ndarray
    validation_accuracy: float
    heldout_accuracy: float


@dataclass(frozen=True)
class Fixture:
    fixture: int
    gap_stratum: str
    a_minus_b_gap: float
    validation_labels: np.ndarray
    heldout_labels: np.ndarray
    candidates: tuple[Candidate, ...]


def exact_accuracy(labels: np.ndarray, predictions: np.ndarray) -> float:
    """Return accuracy after asserting compatible integer arrays."""
    assert labels.shape == predictions.shape
    assert labels.dtype.kind in "iu" and predictions.dtype.kind in "iu"
    return float(np.count_nonzero(labels == predictions) / labels.size)


def fixture_stratum(fixture: int) -> tuple[str, int, float]:
    """Return label, B error count, and A-minus-B held-out gap."""
    if fixture < 10:
        return "A-B=+0.10", 60, 0.10
    if fixture < 20:
        return "A-B=+0.02", 44, 0.02
    if fixture < 30:
        return "A-B=-0.02", 36, -0.02
    return "A-B=-0.10", 20, -0.10


def generate_fixture(fixture: int) -> Fixture:
    """Generate one exact-tie fixture and run all integrity assertions."""
    rng = np.random.default_rng(10_000 + fixture)
    validation_labels = rng.integers(0, 2, size=N_VALIDATION, dtype=np.int8)
    heldout_labels = rng.integers(0, 2, size=N_HELDOUT, dtype=np.int8)

    validation_order = rng.permutation(N_VALIDATION)
    a_validation = validation_labels.copy()
    b_validation = validation_labels.copy()
    a_validation[validation_order[:20]] = 1 - a_validation[validation_order[:20]]
    b_validation[validation_order[20:40]] = 1 - b_validation[validation_order[20:40]]

    stratum, b_error_count, a_minus_b_gap = fixture_stratum(fixture)
    heldout_order = rng.permutation(N_HELDOUT)
    a_heldout = heldout_labels.copy()
    b_heldout = heldout_labels.copy()
    a_heldout[heldout_order[:40]] = 1 - a_heldout[heldout_order[:40]]
    b_heldout[heldout_order[-b_error_count:]] = 1 - b_heldout[heldout_order[-b_error_count:]]

    a_validation_accuracy = exact_accuracy(validation_labels, a_validation)
    b_validation_accuracy = exact_accuracy(validation_labels, b_validation)
    a_heldout_accuracy = exact_accuracy(heldout_labels, a_heldout)
    b_heldout_accuracy = exact_accuracy(heldout_labels, b_heldout)

    candidates: list[Candidate] = []
    for index in range(8):
        candidates.append(
            Candidate(
                identifier=f"A_{index}",
                family="A",
                semantic_signature="A_semantic_0",
                validation_predictions=a_validation,
                heldout_predictions=a_heldout,
                validation_accuracy=a_validation_accuracy,
                heldout_accuracy=a_heldout_accuracy,
            )
        )
    candidates.append(
        Candidate(
            identifier="B_0",
            family="B",
            semantic_signature="B_semantic_0",
            validation_predictions=b_validation,
            heldout_predictions=b_heldout,
            validation_accuracy=b_validation_accuracy,
            heldout_accuracy=b_heldout_accuracy,
        )
    )

    # Exact validation-tie and semantic-duplication integrity checks.
    assert [candidate.identifier for candidate in candidates] == [
        "A_0", "A_1", "A_2", "A_3", "A_4", "A_5", "A_6", "A_7", "B_0"
    ]
    assert all(candidate.validation_accuracy == 80 / 100 for candidate in candidates)
    assert all(candidate.semantic_signature == "A_semantic_0" for candidate in candidates[:8])
    assert len({candidate.validation_predictions.tobytes() for candidate in candidates[:8]}) == 1
    assert len({candidate.heldout_predictions.tobytes() for candidate in candidates[:8]}) == 1
    assert all(candidate.validation_predictions is a_validation for candidate in candidates[:8])
    assert all(candidate.heldout_predictions is a_heldout for candidate in candidates[:8])
    assert a_validation.tobytes() != b_validation.tobytes()
    assert a_heldout_accuracy == 160 / 200
    assert b_heldout_accuracy == (N_HELDOUT - b_error_count) / N_HELDOUT
    assert np.isclose(a_heldout_accuracy - b_heldout_accuracy, a_minus_b_gap, atol=0.0)

    return Fixture(
        fixture=fixture,
        gap_stratum=stratum,
        a_minus_b_gap=a_minus_b_gap,
        validation_labels=validation_labels,
        heldout_labels=heldout_labels,
        candidates=tuple(candidates),
    )


def run_first_encountered(fixture: Fixture) -> list[dict[str, object]]:
    """Run the actual strict-greater-than scan over 1,000 fresh orders."""
    rng = np.random.default_rng(20_000 + fixture.fixture)
    records: list[dict[str, object]] = []
    for repetition in range(N_REPETITIONS):
        order = rng.permutation(len(fixture.candidates))
        best_score = -np.inf
        selected: Candidate | None = None
        for candidate_index in order:
            candidate = fixture.candidates[int(candidate_index)]
            if candidate.validation_accuracy > best_score:
                best_score = candidate.validation_accuracy
                selected = candidate
        assert selected is not None
        assert selected.identifier == fixture.candidates[int(order[0])].identifier
        records.append(
            {
                "fixture": fixture.fixture,
                "repetition": repetition,
                "method": "first_encountered",
                "selected_identifier": selected.identifier,
                "selected_family": selected.family,
                "semantic_signature": selected.semantic_signature,
                "validation_accuracy": selected.validation_accuracy,
                "heldout_accuracy": selected.heldout_accuracy,
                "gap_stratum": fixture.gap_stratum,
                "a_minus_b_heldout_gap": fixture.a_minus_b_gap,
            }
        )
    return records


def collapse_by_semantics(fixture: Fixture) -> dict[str, tuple[Candidate, ...]]:
    """Independently collapse identifiers by semantic signature and verify groups."""
    collapsed: dict[str, list[Candidate]] = {}
    for candidate in fixture.candidates:
        collapsed.setdefault(candidate.semantic_signature, []).append(candidate)

    result = {signature: tuple(group) for signature, group in collapsed.items()}
    assert sorted(result) == ["A_semantic_0", "B_semantic_0"]
    a_group = result["A_semantic_0"]
    b_group = result["B_semantic_0"]
    assert [candidate.identifier for candidate in a_group] == [f"A_{i}" for i in range(8)]
    assert [candidate.identifier for candidate in b_group] == ["B_0"]
    for group in result.values():
        reference = group[0]
        assert all(candidate.family == reference.family for candidate in group)
        assert all(candidate.validation_accuracy == reference.validation_accuracy for candidate in group)
        assert all(
            candidate.validation_predictions.tobytes() == reference.validation_predictions.tobytes()
            for candidate in group
        )
        assert all(
            candidate.heldout_predictions.tobytes() == reference.heldout_predictions.tobytes()
            for candidate in group
        )
    return result


def run_family_uniform(fixture: Fixture) -> list[dict[str, object]]:
    """Run duplicate-collapsed, qualifying-family-uniform selection."""
    rng = np.random.default_rng(30_000 + fixture.fixture)
    collapsed = collapse_by_semantics(fixture)
    semantic_candidates = [group[0] for group in collapsed.values()]
    maximum_score = max(candidate.validation_accuracy for candidate in semantic_candidates)
    qualifying_families = sorted(
        {candidate.family for candidate in semantic_candidates if candidate.validation_accuracy == maximum_score}
    )
    assert qualifying_families == ["A", "B"]
    canonical = {"A": fixture.candidates[0], "B": fixture.candidates[8]}

    records: list[dict[str, object]] = []
    for repetition in range(N_REPETITIONS):
        family = str(rng.choice(qualifying_families))
        selected = canonical[family]
        records.append(
            {
                "fixture": fixture.fixture,
                "repetition": repetition,
                "method": "family_uniform",
                "selected_identifier": selected.identifier,
                "selected_family": selected.family,
                "semantic_signature": selected.semantic_signature,
                "validation_accuracy": selected.validation_accuracy,
                "heldout_accuracy": selected.heldout_accuracy,
                "gap_stratum": fixture.gap_stratum,
                "a_minus_b_heldout_gap": fixture.a_minus_b_gap,
            }
        )
    return records


def wilson_interval(successes: int, trials: int, z: float = Z_95) -> tuple[float, float]:
    """Two-sided Wilson score interval for a binomial proportion."""
    proportion = successes / trials
    denominator = 1.0 + z * z / trials
    center = (proportion + z * z / (2.0 * trials)) / denominator
    half_width = (
        z
        * np.sqrt(proportion * (1.0 - proportion) / trials + z * z / (4.0 * trials * trials))
        / denominator
    )
    return float(center - half_width), float(center + half_width)


def build_fixture_summary(records: pd.DataFrame) -> pd.DataFrame:
    """Build one summary row per fixture."""
    rows: list[dict[str, object]] = []
    for fixture, group in records.groupby("fixture", sort=True):
        baseline = group[group["method"] == "first_encountered"]
        comparison = group[group["method"] == "family_uniform"]
        baseline_a_frequency = float((baseline["selected_family"] == "A").mean())
        comparison_a_frequency = float((comparison["selected_family"] == "A").mean())
        baseline_heldout_mean = float(baseline["heldout_accuracy"].mean())
        comparison_heldout_mean = float(comparison["heldout_accuracy"].mean())
        gap = float(group["a_minus_b_heldout_gap"].iloc[0])
        rows.append(
            {
                "fixture": int(fixture),
                "gap_stratum": str(group["gap_stratum"].iloc[0]),
                "a_minus_b_heldout_gap": gap,
                "baseline_a_frequency": baseline_a_frequency,
                "comparison_a_frequency": comparison_a_frequency,
                "a_frequency_difference": baseline_a_frequency - comparison_a_frequency,
                "baseline_mean_heldout_accuracy": baseline_heldout_mean,
                "comparison_mean_heldout_accuracy": comparison_heldout_mean,
                "baseline_minus_comparison_heldout_shift": baseline_heldout_mean
                - comparison_heldout_mean,
                "theoretical_heldout_shift": (7.0 / 18.0) * gap,
                "validation_tie_integrity": bool((group["validation_accuracy"] == 0.80).all()),
            }
        )
    summary = pd.DataFrame(rows)
    assert len(summary) == N_FIXTURES
    return summary


def create_figure(
    fixture_summary: pd.DataFrame,
    baseline_frequency: float,
    comparison_frequency: float,
    baseline_ci: tuple[float, float],
    comparison_ci: tuple[float, float],
    stratum_shifts: dict[str, float],
) -> None:
    """Create the preregistered two-panel visualization at 1600x700 pixels."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(16, 7), dpi=100)

    ax = axes[0]
    ax.axhspan(0.85, 0.92, color="#4c78a8", alpha=0.10, label="Baseline acceptance band")
    ax.axhspan(0.47, 0.53, color="#f58518", alpha=0.10, label="Comparison acceptance band")
    ax.axhline(8 / 9, color="#4c78a8", linestyle="--", linewidth=1.5, alpha=0.8)
    ax.axhline(1 / 2, color="#f58518", linestyle="--", linewidth=1.5, alpha=0.8)

    fixture_indices = fixture_summary["fixture"].to_numpy(dtype=float)
    jitter = np.linspace(-0.055, 0.055, N_FIXTURES)
    ax.scatter(
        np.zeros(N_FIXTURES) + jitter,
        fixture_summary["baseline_a_frequency"],
        color="#4c78a8",
        alpha=0.72,
        s=27,
        label="Fixture frequencies",
        zorder=3,
    )
    ax.scatter(
        np.ones(N_FIXTURES) + jitter[::-1],
        fixture_summary["comparison_a_frequency"],
        color="#f58518",
        alpha=0.72,
        s=27,
        zorder=3,
    )
    del fixture_indices  # Jitter is deterministic and only separates overlapping points.
    ax.errorbar(
        [0],
        [baseline_frequency],
        yerr=[[baseline_frequency - baseline_ci[0]], [baseline_ci[1] - baseline_frequency]],
        fmt="D",
        color="#173f5f",
        markersize=9,
        capsize=6,
        linewidth=2.2,
        label="Pooled frequency + 95% Wilson CI",
        zorder=5,
    )
    ax.errorbar(
        [1],
        [comparison_frequency],
        yerr=[[comparison_frequency - comparison_ci[0]], [comparison_ci[1] - comparison_frequency]],
        fmt="D",
        color="#a64b00",
        markersize=9,
        capsize=6,
        linewidth=2.2,
        zorder=5,
    )
    ax.set_xlim(-0.35, 1.35)
    ax.set_ylim(0.42, 0.96)
    ax.set_xticks([0, 1], ["First encountered", "Collapsed +\nfamily uniform"])
    ax.set_ylabel("Family-A selection frequency")
    ax.set_title("Selection frequency across 40 fixtures")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(loc="center right", fontsize=9)

    ax = axes[1]
    stratum_order = ["A-B=+0.10", "A-B=+0.02", "A-B=-0.02", "A-B=-0.10"]
    empirical = [stratum_shifts[stratum] for stratum in stratum_order]
    gaps = [0.10, 0.02, -0.02, -0.10]
    theoretical = [(7.0 / 18.0) * gap for gap in gaps]
    x = np.arange(len(stratum_order))
    ax.axhline(0.0, color="black", linewidth=1.2)
    ax.bar(x, empirical, width=0.58, color="#72b7b2", alpha=0.85, label="Empirical mean shift")
    ax.scatter(
        x,
        theoretical,
        marker="X",
        s=100,
        color="#e45756",
        label="Theoretical shift",
        zorder=4,
    )
    ax.set_xticks(x, ["+0.10", "+0.02", "−0.02", "−0.10"])
    ax.set_xlabel("A-minus-B held-out accuracy gap")
    ax.set_ylabel("Baseline minus comparison\nmean held-out accuracy")
    ax.set_title("Held-out consequences by gap stratum")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(loc="best")

    fig.suptitle(
        "Exact validation ties: identifier multiplicity changes family conclusions and held-out outcomes",
        fontsize=14,
    )
    fig.tight_layout()
    output = FIGURES_DIR / "selection_frequency.png"
    fig.savefig(output, dpi=100, bbox_inches=None)
    plt.close(fig)


def main() -> None:
    np.random.seed(MASTER_SEED)  # Metadata/master seed; step RNGs use default_rng below.
    fixtures = [generate_fixture(fixture) for fixture in range(N_FIXTURES)]
    fixture_integrity_assertions_passed = len(fixtures) == N_FIXTURES

    records: list[dict[str, object]] = []
    for fixture in fixtures:
        records.extend(run_first_encountered(fixture))
        records.extend(run_family_uniform(fixture))
    records_df = pd.DataFrame(records)

    expected_rows = 2 * N_FIXTURES * N_REPETITIONS
    assert len(records_df) == expected_rows
    assert records_df.groupby(["method", "fixture"]).size().eq(N_REPETITIONS).all()
    assert (records_df["validation_accuracy"] == 0.80).all()
    assert not records_df.isna().any().any()

    baseline = records_df[records_df["method"] == "first_encountered"]
    comparison = records_df[records_df["method"] == "family_uniform"]
    assert len(baseline) == len(comparison) == N_FIXTURES * N_REPETITIONS

    baseline_a_count = int((baseline["selected_family"] == "A").sum())
    comparison_a_count = int((comparison["selected_family"] == "A").sum())
    baseline_a_frequency = baseline_a_count / len(baseline)
    comparison_a_frequency = comparison_a_count / len(comparison)
    baseline_ci = wilson_interval(baseline_a_count, len(baseline))
    comparison_ci = wilson_interval(comparison_a_count, len(comparison))

    identifier_order = [f"A_{index}" for index in range(8)] + ["B_0"]
    identifier_frequencies = (
        baseline["selected_identifier"].value_counts(normalize=True).reindex(identifier_order, fill_value=0.0)
    )
    identifier_only_instability = baseline_a_frequency**2 - float(
        np.square(identifier_frequencies.loc[[f"A_{index}" for index in range(8)]].to_numpy()).sum()
    )

    cardinality_effect = baseline_a_frequency - comparison_a_frequency
    baseline_odds = baseline_a_frequency / (1.0 - baseline_a_frequency)
    comparison_odds = comparison_a_frequency / (1.0 - comparison_a_frequency)
    selection_odds_ratio = baseline_odds / comparison_odds

    fixture_summary = build_fixture_summary(records_df)
    stratum_order = ["A-B=+0.10", "A-B=+0.02", "A-B=-0.02", "A-B=-0.10"]
    stratum_shifts = {
        stratum: float(
            fixture_summary.loc[
                fixture_summary["gap_stratum"] == stratum,
                "baseline_minus_comparison_heldout_shift",
            ].mean()
        )
        for stratum in stratum_order
    }
    overall_signed_shift = float(fixture_summary["baseline_minus_comparison_heldout_shift"].mean())
    overall_mean_absolute_shift = float(
        fixture_summary["baseline_minus_comparison_heldout_shift"].abs().mean()
    )

    decision_baseline_in_band = 0.85 <= baseline_a_frequency <= 0.92
    decision_comparison_in_band = 0.47 <= comparison_a_frequency <= 0.53
    decision_effect_large_enough = cardinality_effect >= 0.32
    supported = bool(
        fixture_integrity_assertions_passed
        and decision_baseline_in_band
        and decision_comparison_in_band
        and decision_effect_large_enough
    )
    decision = "SUPPORTED" if supported else "REFUTED"

    metrics: dict[str, str | int | float | bool] = {
        "master_seed": MASTER_SEED,
        "python_requirement_met": True,
        "n_fixtures": N_FIXTURES,
        "repetitions_per_fixture_per_method": N_REPETITIONS,
        "selections_per_method": N_FIXTURES * N_REPETITIONS,
        "total_selection_records": expected_rows,
        "fixture_integrity_assertions_passed": fixture_integrity_assertions_passed,
        "all_validation_accuracies_exactly_0_80": bool((records_df["validation_accuracy"] == 0.80).all()),
        "baseline_family_a_count": baseline_a_count,
        "baseline_family_a_frequency": baseline_a_frequency,
        "baseline_family_a_frequency_theoretical": 8.0 / 9.0,
        "baseline_family_a_wilson_95_low": baseline_ci[0],
        "baseline_family_a_wilson_95_high": baseline_ci[1],
        "comparison_family_a_count": comparison_a_count,
        "comparison_family_a_frequency": comparison_a_frequency,
        "comparison_family_a_frequency_theoretical": 1.0 / 2.0,
        "comparison_family_a_wilson_95_low": comparison_ci[0],
        "comparison_family_a_wilson_95_high": comparison_ci[1],
        "grid_cardinality_effect": cardinality_effect,
        "grid_cardinality_effect_theoretical": 7.0 / 18.0,
        "selection_odds_ratio": selection_odds_ratio,
        "selection_odds_ratio_theoretical": 8.0,
        "identifier_only_instability": identifier_only_instability,
        "identifier_only_instability_theoretical": 56.0 / 81.0,
        "heldout_shift_gap_plus_0_10": stratum_shifts["A-B=+0.10"],
        "heldout_shift_gap_plus_0_10_theoretical": (7.0 / 18.0) * 0.10,
        "heldout_shift_gap_plus_0_02": stratum_shifts["A-B=+0.02"],
        "heldout_shift_gap_plus_0_02_theoretical": (7.0 / 18.0) * 0.02,
        "heldout_shift_gap_minus_0_02": stratum_shifts["A-B=-0.02"],
        "heldout_shift_gap_minus_0_02_theoretical": (7.0 / 18.0) * -0.02,
        "heldout_shift_gap_minus_0_10": stratum_shifts["A-B=-0.10"],
        "heldout_shift_gap_minus_0_10_theoretical": (7.0 / 18.0) * -0.10,
        "heldout_shift_overall_signed_mean": overall_signed_shift,
        "heldout_shift_overall_signed_mean_theoretical": 0.0,
        "heldout_shift_overall_mean_absolute": overall_mean_absolute_shift,
        "heldout_shift_overall_mean_absolute_theoretical": 7.0 / 300.0,
        "decision_baseline_frequency_in_acceptance_band": decision_baseline_in_band,
        "decision_comparison_frequency_in_acceptance_band": decision_comparison_in_band,
        "decision_grid_cardinality_effect_at_least_0_32": decision_effect_large_enough,
        "hypothesis_supported": supported,
        "decision": decision,
    }
    for identifier in identifier_order:
        metrics[f"baseline_identifier_frequency_{identifier.lower()}"] = float(
            identifier_frequencies.loc[identifier]
        )

    # Confirm that the required machine-readable output is strictly flat/scalar.
    assert all(not isinstance(value, (dict, list, tuple)) for value in metrics.values())

    records_df.to_csv(ROOT / "selection_records.csv", index=False, float_format="%.12g")
    fixture_summary.to_csv(ROOT / "fixture_summary.csv", index=False, float_format="%.12g")
    with (ROOT / "results.json").open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")

    create_figure(
        fixture_summary,
        baseline_a_frequency,
        comparison_a_frequency,
        baseline_ci,
        comparison_ci,
        stratum_shifts,
    )

    print("Ran 40 exact-validation-tie fixtures with 1,000 deterministic selections per method.")
    print(
        f"Family A: baseline={baseline_a_frequency:.6f} "
        f"(95% Wilson {baseline_ci[0]:.6f}-{baseline_ci[1]:.6f}), "
        f"comparison={comparison_a_frequency:.6f} "
        f"(95% Wilson {comparison_ci[0]:.6f}-{comparison_ci[1]:.6f})."
    )
    print(
        f"Grid-cardinality effect={cardinality_effect:.6f}; odds ratio={selection_odds_ratio:.6f}; "
        f"identifier-only instability={identifier_only_instability:.6f}."
    )
    print(
        "Held-out shifts (+0.10, +0.02, -0.02, -0.10): "
        + ", ".join(f"{stratum_shifts[stratum]:+.6f}" for stratum in stratum_order)
        + f"; mean absolute={overall_mean_absolute_shift:.6f}."
    )
    print(f"Hypothesis decision: {decision}.")


if __name__ == "__main__":
    main()
