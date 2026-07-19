#!/usr/bin/env python3
"""Prespecified simulation of tuning ties under a skew-logistic DGP.

This script implements the experiment without data-dependent adaptation.  It
computes population accuracies first, validates the population conditions, and
then consumes one PCG64 random stream sequentially for exactly 500 samples.
"""

from __future__ import annotations

import json
import math
import platform
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
from scipy.integrate import quad
from scipy.special import expit
from scipy.stats import norm


SEED = 20250308
N_SAMPLES = 500
SAMPLE_SIZE = 300
SHAPE = 5.0
LOCATION = -1.0
SCALE = 1.5
CUTOFFS = np.array([0.30 + 0.04 * j for j in range(11)], dtype=float)
EPSABS = 1e-12
EPSREL = 1e-12
QUAD_LIMIT = 500
WIDE_GAP = 0.001
TIE_COUNT_THRESHOLD = 75
WIDE_PROP_THRESHOLD = 0.80
BASELINE_INDEX = 5
ROOT = Path(__file__).resolve().parent
FIGURE_DIR = ROOT / "figures"


def skew_normal_density(x: float) -> float:
    """Density of skew-normal(shape=5, location=-1, scale=1.5)."""
    z = (x - LOCATION) / SCALE
    return float(2.0 * norm.pdf(z) * norm.cdf(SHAPE * z) / SCALE)


def population_accuracy(threshold: float) -> tuple[float, float, float]:
    """Compute population accuracy by the two required improper integrals."""

    def lower_integrand(x: float) -> float:
        return float(expit(-x) * skew_normal_density(x))

    def upper_integrand(x: float) -> float:
        return float(expit(x) * skew_normal_density(x))

    lower, lower_error = quad(
        lower_integrand,
        -np.inf,
        threshold,
        epsabs=EPSABS,
        epsrel=EPSREL,
        limit=QUAD_LIMIT,
    )
    upper, upper_error = quad(
        upper_integrand,
        threshold,
        np.inf,
        epsabs=EPSABS,
        epsrel=EPSREL,
        limit=QUAD_LIMIT,
    )
    return float(lower + upper), float(lower_error), float(upper_error)


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Two-sided 95% Wilson score interval."""
    if trials <= 0:
        return (math.nan, math.nan)
    proportion = successes / trials
    denominator = 1.0 + z * z / trials
    center = (proportion + z * z / (2.0 * trials)) / denominator
    half_width = (
        z
        * math.sqrt(proportion * (1.0 - proportion) / trials + z * z / (4.0 * trials * trials))
        / denominator
    )
    return (center - half_width, center + half_width)


def json_dump(path: Path, payload: dict[str, object]) -> None:
    """Write standards-compliant, deterministic JSON."""
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def save_figure(
    tie_rate: float,
    tie_interval: tuple[float, float],
    conditional_wide: float,
    conditional_interval: tuple[float, float],
    tied_ranges: np.ndarray,
    n_tie: int,
    n_wide: int,
) -> None:
    """Create the required 1600x700 two-panel result figure."""
    FIGURE_DIR.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(16, 7), dpi=100)

    values = np.array([tie_rate, conditional_wide])
    intervals = [tie_interval, conditional_interval]
    lower_errors = []
    upper_errors = []
    for value, (lower, upper) in zip(values, intervals, strict=True):
        if math.isfinite(lower) and math.isfinite(upper):
            lower_errors.append(value - lower)
            upper_errors.append(upper - value)
        else:
            lower_errors.append(0.0)
            upper_errors.append(0.0)
    x_positions = np.arange(2)
    axes[0].bar(
        x_positions,
        values,
        color=["#4472C4", "#ED7D31"],
        yerr=np.array([lower_errors, upper_errors]),
        capsize=7,
        edgecolor="black",
        linewidth=0.7,
    )
    axes[0].axhline(0.15, color="#4472C4", linestyle="--", linewidth=1.5, label="Tie-rate target (0.15)")
    axes[0].axhline(0.80, color="#ED7D31", linestyle="--", linewidth=1.5, label="Wide-gap target (0.80)")
    axes[0].set_xticks(x_positions, ["Exact tie rate", "Wide-gap proportion\nconditional on tie"])
    axes[0].set_ylim(0.0, 1.05)
    axes[0].set_ylabel("Proportion")
    axes[0].set_title("Observed proportions with 95% Wilson intervals")
    axes[0].legend(loc="center right", frameon=False)
    axes[0].grid(axis="y", alpha=0.25)

    if tied_ranges.size:
        axes[1].hist(tied_ranges, bins="auto", color="#70AD47", edgecolor="white", linewidth=0.8)
        axes[1].axvline(WIDE_GAP, color="#C00000", linestyle="--", linewidth=1.8, label="Wide-gap cutoff (0.001)")
        axes[1].legend(frameon=False)
    else:
        axes[1].text(0.5, 0.5, "No tie events", ha="center", va="center", transform=axes[1].transAxes, fontsize=16)
    axes[1].text(
        0.98,
        0.95,
        f"N_tie = {n_tie}\nN_wide = {n_wide}",
        ha="right",
        va="top",
        transform=axes[1].transAxes,
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85, "edgecolor": "0.7"},
    )
    axes[1].set_xlabel("Population-accuracy range among tied optimizers ($D_s$)")
    axes[1].set_ylabel("Number of tied samples")
    axes[1].set_title("Population separation within empirical optimum ties")
    axes[1].grid(axis="y", alpha=0.25)

    fig.tight_layout()
    figure_path = FIGURE_DIR / "tuning_tie_results.png"
    fig.savefig(figure_path, dpi=100)
    plt.close(fig)
    # The protocol names a root-level file, while workspace conventions require
    # figures/. Keep the canonical figure in figures/ and an identical named copy.
    shutil.copyfile(figure_path, ROOT / "tuning_tie_results.png")


def main() -> int:
    thresholds = np.log(CUTOFFS / (1.0 - CUTOFFS))

    # Population quantities are computed and checked before any simulation draw.
    quadrature_results = [population_accuracy(float(t)) for t in thresholds]
    accuracies = np.array([result[0] for result in quadrature_results])
    lower_errors = np.array([result[1] for result in quadrature_results])
    upper_errors = np.array([result[2] for result in quadrature_results])
    pairwise_differences = np.abs(accuracies[:, None] - accuracies[None, :])
    min_pairwise_difference = float(pairwise_differences[np.triu_indices(len(CUTOFFS), k=1)].min())
    finite_check = bool(np.isfinite(accuracies).all())
    distinct_check = bool(min_pairwise_difference > 1e-8)
    maximizing_indices = np.flatnonzero(accuracies == accuracies.max())
    unique_q50_check = bool(len(maximizing_indices) == 1 and maximizing_indices[0] == BASELINE_INDEX)
    population_checks_pass = finite_check and distinct_check and unique_q50_check

    optimum_accuracy = float(accuracies.max())
    deficits = optimum_accuracy - accuracies
    population_frame = pd.DataFrame(
        {
            "candidate_index": np.arange(len(CUTOFFS), dtype=int),
            "cutoff": CUTOFFS,
            "x_threshold": thresholds,
            "population_accuracy": accuracies,
            "deficit_from_population_optimum": deficits,
            "quadrature_lower_error_estimate": lower_errors,
            "quadrature_upper_error_estimate": upper_errors,
        }
    )
    population_frame.to_csv(ROOT / "population_accuracies.csv", index=False, float_format="%.15f")

    version_metrics: dict[str, object] = {
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "pandas_version": pd.__version__,
        "matplotlib_version": matplotlib.__version__,
    }

    if not population_checks_pass:
        invalid = {
            **version_metrics,
            "decision": "INVALID",
            "population_finite_check": finite_check,
            "population_distinct_check": distinct_check,
            "population_unique_q50_maximizer_check": unique_q50_check,
            "population_checks_pass": False,
            "min_pairwise_population_accuracy_difference": min_pairwise_difference,
            "seed": SEED,
            "n": SAMPLE_SIZE,
            "number_of_samples": N_SAMPLES,
        }
        json_dump(ROOT / "summary_metrics.json", invalid)
        json_dump(ROOT / "results.json", invalid)
        print("Experiment INVALID: a prespecified population-risk check failed; no simulation draws were made.")
        return 2

    rng = np.random.Generator(np.random.PCG64(SEED))
    delta = SHAPE / math.sqrt(1.0 + SHAPE * SHAPE)
    residual_scale = math.sqrt(1.0 - delta * delta)
    rows: list[dict[str, object]] = []

    for sample_index in range(N_SAMPLES):
        # Draw each complete sample in protocol order from the sole RNG stream.
        u = rng.normal(0.0, 1.0, size=SAMPLE_SIZE)
        v = rng.normal(0.0, 1.0, size=SAMPLE_SIZE)
        x = LOCATION + SCALE * (delta * np.abs(u) + residual_scale * v)
        r = rng.uniform(0.0, 1.0, size=SAMPLE_SIZE)
        y = r < expit(x)

        predictions = x[:, None] >= thresholds[None, :]
        counts = np.sum(predictions == y[:, None], axis=0, dtype=np.int64)
        maximum = int(counts.max())
        optimizer_indices = np.flatnonzero(counts == maximum)
        optimizer_count = int(len(optimizer_indices))
        tied = optimizer_count >= 2
        population_range = (
            float(accuracies[optimizer_indices].max() - accuracies[optimizer_indices].min()) if tied else math.nan
        )
        wide = bool(tied and population_range > WIDE_GAP)
        q50_member = bool(BASELINE_INDEX in optimizer_indices)
        # Competition ranking: one plus the number of candidates strictly above.
        q50_empirical_rank = int(1 + np.sum(counts > counts[BASELINE_INDEX]))

        row: dict[str, object] = {"sample_index": sample_index}
        row.update({f"score_j{j}": int(counts[j]) for j in range(len(CUTOFFS))})
        row.update(
            {
                "M_s": maximum,
                "optimizer_count": optimizer_count,
                "optimizer_cutoff_list": "|".join(f"{CUTOFFS[j]:.2f}" for j in optimizer_indices),
                "empirical_optimum_accuracy": maximum / SAMPLE_SIZE,
                "T_s": int(tied),
                "D_s": population_range,
                "W_s": int(wide),
                "q50_in_optimizer_set": q50_member,
                "population_best_empirical_rank": q50_empirical_rank,
            }
        )
        rows.append(row)

    sample_frame = pd.DataFrame(rows)
    sample_frame.to_csv(ROOT / "tie_samples.csv", index=False, float_format="%.15f", na_rep="")

    n_tie = int(sample_frame["T_s"].sum())
    tie_rate = n_tie / N_SAMPLES
    n_wide = int(sample_frame["W_s"].sum())
    conditional_wide = n_wide / n_tie if n_tie else 0.0
    tie_interval = wilson_interval(n_tie, N_SAMPLES)
    conditional_interval = wilson_interval(n_wide, n_tie)
    required_wide_count = math.ceil(WIDE_PROP_THRESHOLD * n_tie)

    multiplicity_1 = int((sample_frame["optimizer_count"] == 1).sum())
    multiplicity_2 = int((sample_frame["optimizer_count"] == 2).sum())
    multiplicity_3 = int((sample_frame["optimizer_count"] == 3).sum())
    multiplicity_4plus = int((sample_frame["optimizer_count"] >= 4).sum())
    baseline_sole = int(((sample_frame["optimizer_count"] == 1) & sample_frame["q50_in_optimizer_set"]).sum())
    baseline_tied = int(((sample_frame["optimizer_count"] >= 2) & sample_frame["q50_in_optimizer_set"]).sum())
    baseline_absent = int((~sample_frame["q50_in_optimizer_set"]).sum())

    decision = (
        "SUPPORTED"
        if n_tie >= TIE_COUNT_THRESHOLD and n_wide >= required_wide_count
        else "REFUTED"
    )

    summary: dict[str, object] = {
        **version_metrics,
        "seed": SEED,
        "bit_generator": "PCG64",
        "n": SAMPLE_SIZE,
        "number_of_samples": N_SAMPLES,
        "number_of_candidates": len(CUTOFFS),
        "quadrature_epsabs": EPSABS,
        "quadrature_epsrel": EPSREL,
        "quadrature_limit": QUAD_LIMIT,
        "population_finite_check": finite_check,
        "population_distinct_check": distinct_check,
        "population_unique_q50_maximizer_check": unique_q50_check,
        "population_checks_pass": population_checks_pass,
        "number_of_population_maximizers": int(len(maximizing_indices)),
        "min_pairwise_population_accuracy_difference": min_pairwise_difference,
        "population_optimum_cutoff": float(CUTOFFS[BASELINE_INDEX]),
        "population_optimum_accuracy": optimum_accuracy,
        "exact_tie_count": n_tie,
        "exact_tie_rate": tie_rate,
        "exact_tie_wilson_95_lower": tie_interval[0],
        "exact_tie_wilson_95_upper": tie_interval[1],
        "wide_gap_threshold": WIDE_GAP,
        "wide_gap_tie_count": n_wide,
        "conditional_wide_gap_proportion": conditional_wide,
        "conditional_wide_gap_wilson_95_lower": conditional_interval[0] if n_tie else None,
        "conditional_wide_gap_wilson_95_upper": conditional_interval[1] if n_tie else None,
        "multiplicity_1_count": multiplicity_1,
        "multiplicity_1_proportion": multiplicity_1 / N_SAMPLES,
        "multiplicity_2_count": multiplicity_2,
        "multiplicity_2_proportion": multiplicity_2 / N_SAMPLES,
        "multiplicity_3_count": multiplicity_3,
        "multiplicity_3_proportion": multiplicity_3 / N_SAMPLES,
        "multiplicity_4plus_count": multiplicity_4plus,
        "multiplicity_4plus_proportion": multiplicity_4plus / N_SAMPLES,
        "q50_sole_empirical_optimizer_count": baseline_sole,
        "q50_sole_empirical_optimizer_proportion": baseline_sole / N_SAMPLES,
        "q50_in_tied_optimizer_set_count": baseline_tied,
        "q50_in_tied_optimizer_set_proportion": baseline_tied / N_SAMPLES,
        "q50_absent_from_optimizer_set_count": baseline_absent,
        "q50_absent_from_optimizer_set_proportion": baseline_absent / N_SAMPLES,
        "tie_count_threshold": TIE_COUNT_THRESHOLD,
        "conditional_wide_gap_threshold": WIDE_PROP_THRESHOLD,
        "required_wide_gap_tie_count": required_wide_count,
        "tie_count_condition_pass": bool(n_tie >= TIE_COUNT_THRESHOLD),
        "wide_gap_condition_pass": bool(n_wide >= required_wide_count),
        "decision": decision,
    }
    for j, cutoff in enumerate(CUTOFFS):
        summary[f"population_accuracy_q{cutoff:.2f}"] = float(accuracies[j])
        summary[f"population_deficit_q{cutoff:.2f}"] = float(deficits[j])

    json_dump(ROOT / "summary_metrics.json", summary)

    # The mandatory results file is deliberately flat and scalar-valued.
    results = {
        "decision": decision,
        "population_checks_pass": population_checks_pass,
        "min_pairwise_population_accuracy_difference": min_pairwise_difference,
        "number_of_population_maximizers": int(len(maximizing_indices)),
        "population_optimum_cutoff": float(CUTOFFS[BASELINE_INDEX]),
        "population_optimum_accuracy": optimum_accuracy,
        "exact_tie_count": n_tie,
        "exact_tie_rate": tie_rate,
        "exact_tie_wilson_95_lower": tie_interval[0],
        "exact_tie_wilson_95_upper": tie_interval[1],
        "wide_gap_tie_count": n_wide,
        "conditional_wide_gap_proportion": conditional_wide,
        "conditional_wide_gap_wilson_95_lower": conditional_interval[0] if n_tie else -1.0,
        "conditional_wide_gap_wilson_95_upper": conditional_interval[1] if n_tie else -1.0,
        "required_wide_gap_tie_count": required_wide_count,
        "tie_count_condition_pass": bool(n_tie >= TIE_COUNT_THRESHOLD),
        "wide_gap_condition_pass": bool(n_wide >= required_wide_count),
        "q50_sole_empirical_optimizer_count": baseline_sole,
        "q50_in_tied_optimizer_set_count": baseline_tied,
        "q50_absent_from_optimizer_set_count": baseline_absent,
        "seed": SEED,
        "n": SAMPLE_SIZE,
        "number_of_samples": N_SAMPLES,
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "pandas_version": pd.__version__,
        "matplotlib_version": matplotlib.__version__,
    }
    json_dump(ROOT / "results.json", results)

    tied_ranges = sample_frame.loc[sample_frame["T_s"] == 1, "D_s"].to_numpy(dtype=float)
    save_figure(tie_rate, tie_interval, conditional_wide, conditional_interval, tied_ranges, n_tie, n_wide)

    direction = "supporting" if decision == "SUPPORTED" else "refuting"
    print(
        f"Ran {N_SAMPLES} fixed validation samples of n={SAMPLE_SIZE} over 11 prespecified cutoffs.\n"
        f"Population checks: PASS; unique optimum q=0.50, accuracy={optimum_accuracy:.12f}, "
        f"minimum pairwise gap={min_pairwise_difference:.12g}.\n"
        f"Exact ties: {n_tie}/{N_SAMPLES} ({tie_rate:.3f}, Wilson 95% CI "
        f"[{tie_interval[0]:.3f}, {tie_interval[1]:.3f}]).\n"
        f"Wide-gap ties: {n_wide}/{n_tie} ({conditional_wide:.3f}, Wilson 95% CI "
        f"[{conditional_interval[0]:.3f}, {conditional_interval[1]:.3f}]).\n"
        f"Decision: {decision}; results point toward {direction} the prespecified hypothesis."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
