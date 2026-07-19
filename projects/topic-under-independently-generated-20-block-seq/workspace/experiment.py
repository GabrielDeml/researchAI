#!/usr/bin/env python3
"""Simulate the null distribution of lag-1 correlations after candidate selection."""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy
import scipy
from scipy import stats


SEED = 20250308
N_EXPERIMENTS = 200_000
N_CANDIDATES = 32
SEQUENCE_LENGTH = 20
BATCH_SIZE = 5_000
N_BATCHES = N_EXPERIMENTS // BATCH_SIZE
QUANTILE_LEVELS = numpy.array([0.05, 0.25, 0.50, 0.75, 0.95])
KS_THRESHOLD = 0.01
R_THRESHOLD = 0.40
EXCEEDANCE_THRESHOLD = 0.50

WORKSPACE = Path(__file__).resolve().parent
FIGURES_DIR = WORKSPACE / "figures"
FIGURE_PATH = FIGURES_DIR / "lag1_selection_null.png"
ROOT_FIGURE_PATH = WORKSPACE / "lag1_selection_null.png"
METRICS_PATH = WORKSPACE / "metrics.json"
RESULTS_PATH = WORKSPACE / "results.json"


def validate_environment() -> None:
    """Fail early if the protocol's exact package versions are not active."""
    required = {
        "numpy": "1.26.4",
        "scipy": "1.12.0",
        "matplotlib": "3.8.3",
    }
    actual = {
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "matplotlib": matplotlib.__version__,
    }
    if actual != required:
        raise RuntimeError(f"Package version mismatch: required={required}, actual={actual}")
    python_major_minor = tuple(map(int, platform.python_version_tuple()[:2]))
    if python_major_minor < (3, 11):
        raise RuntimeError(f"Python 3.11+ is required, found {platform.python_version()}")


def simulate() -> tuple[numpy.ndarray, numpy.ndarray, numpy.ndarray, float]:
    """Run all batches in protocol order and return the three result arrays."""
    if N_EXPERIMENTS % BATCH_SIZE != 0 or N_BATCHES != 40:
        raise RuntimeError("The protocol requires exactly 40 complete batches")

    # The protocol requires exactly one Generator, initialized this way.
    rng = numpy.random.Generator(numpy.random.PCG64(20250308))

    r_fixed = numpy.empty(N_EXPERIMENTS, dtype=numpy.float64)
    r_max_mean = numpy.empty(N_EXPERIMENTS, dtype=numpy.float64)
    r_max_r = numpy.empty(N_EXPERIMENTS, dtype=numpy.float64)
    verification_max_abs_diff = numpy.nan
    batch_rows = numpy.arange(BATCH_SIZE)

    for batch_index in range(N_BATCHES):
        start = batch_index * BATCH_SIZE
        stop = start + BATCH_SIZE

        z = rng.standard_normal(
            (BATCH_SIZE, N_CANDIDATES, SEQUENCE_LENGTH),
            dtype=numpy.float64,
        )
        candidate_mean = z.mean(axis=2)
        idx_mean = numpy.argmax(candidate_mean, axis=1)

        x = z[:, :, :-1]
        y = z[:, :, 1:]
        xc = x - x.mean(axis=2, keepdims=True)
        yc = y - y.mean(axis=2, keepdims=True)
        r = numpy.sum(xc * yc, axis=2) / numpy.sqrt(
            numpy.sum(xc * xc, axis=2) * numpy.sum(yc * yc, axis=2)
        )

        if batch_index == 0:
            first_sequences = z.reshape(-1, SEQUENCE_LENGTH)[:256]
            corrcoef_values = numpy.array(
                [
                    numpy.corrcoef(sequence[:-1], sequence[1:])[0, 1]
                    for sequence in first_sequences
                ],
                dtype=numpy.float64,
            )
            vectorized_values = r.reshape(-1)[:256]
            if not numpy.all(numpy.isfinite(corrcoef_values)):
                raise RuntimeError("Non-finite value in corrcoef verification")
            verification_max_abs_diff = float(
                numpy.max(numpy.abs(corrcoef_values - vectorized_values))
            )
            if verification_max_abs_diff > 1e-12:
                raise RuntimeError(
                    "Vectorized correlation verification failed: "
                    f"max abs diff={verification_max_abs_diff:.17g}"
                )

        r_fixed[start:stop] = r[:, 0]
        r_max_mean[start:stop] = r[batch_rows, idx_mean]
        idx_r = numpy.argmax(r, axis=1)
        r_max_r[start:stop] = r[batch_rows, idx_r]

        if (batch_index + 1) % 10 == 0:
            print(f"Completed batch {batch_index + 1}/{N_BATCHES}", flush=True)

    for name, values in (
        ("r_fixed", r_fixed),
        ("r_max_mean", r_max_mean),
        ("r_max_r", r_max_r),
    ):
        if values.shape != (N_EXPERIMENTS,):
            raise RuntimeError(f"{name} has incorrect shape {values.shape}")
        if numpy.count_nonzero(numpy.isfinite(values)) != N_EXPERIMENTS:
            raise RuntimeError(f"{name} does not contain exactly 200,000 finite values")
        if not numpy.all((values >= -1.0) & (values <= 1.0)):
            raise RuntimeError(f"{name} contains a value outside [-1, 1]")

    return r_fixed, r_max_mean, r_max_r, verification_max_abs_diff


def build_metrics(
    r_fixed: numpy.ndarray,
    r_max_mean: numpy.ndarray,
    r_max_r: numpy.ndarray,
    verification_max_abs_diff: float,
) -> dict[str, bool | float | int | str]:
    """Compute all pre-specified statistics and the fixed-threshold decision."""
    ks_distance = float(
        stats.ks_2samp(
            r_fixed,
            r_max_mean,
            alternative="two-sided",
            method="asymp",
        ).statistic
    )
    p_max_r_gt_040 = float(numpy.mean(r_max_r > 0.40))
    p_fixed_gt_040 = float(numpy.mean(r_fixed > 0.40))
    p_max_mean_gt_040 = float(numpy.mean(r_max_mean > 0.40))
    mcse_max_r_gt_040 = float(
        numpy.sqrt(p_max_r_gt_040 * (1.0 - p_max_r_gt_040) / 200000)
    )
    ks_condition = ks_distance <= KS_THRESHOLD
    exceedance_condition = p_max_r_gt_040 > EXCEEDANCE_THRESHOLD
    supported = bool(ks_condition and exceedance_condition)

    metrics: dict[str, bool | float | int | str] = {
        "decision": "SUPPORTED" if supported else "REFUTED",
        "hypothesis_supported": supported,
        "ks_condition_passed": bool(ks_condition),
        "exceedance_condition_passed": bool(exceedance_condition),
        "ks_r_fixed_vs_r_max_mean": ks_distance,
        "ks_decision_threshold": KS_THRESHOLD,
        "p_max_r_gt_0_40": p_max_r_gt_040,
        "p_fixed_gt_0_40": p_fixed_gt_040,
        "p_max_mean_gt_0_40": p_max_mean_gt_040,
        "max_r_exceedance_decision_threshold": EXCEEDANCE_THRESHOLD,
        "max_r_exceedance_is_strict": True,
        "mcse_p_max_r_gt_0_40": mcse_max_r_gt_040,
        "seed": SEED,
        "n_experiments": N_EXPERIMENTS,
        "n_candidates": N_CANDIDATES,
        "sequence_length": SEQUENCE_LENGTH,
        "batch_size": BATCH_SIZE,
        "n_batches": N_BATCHES,
        "correlation_validation_sequences": 256,
        "correlation_validation_max_abs_diff": verification_max_abs_diff,
        "numpy_version": numpy.__version__,
        "scipy_version": scipy.__version__,
        "matplotlib_version": matplotlib.__version__,
        "python_version": platform.python_version(),
        "bit_generator": "PCG64",
        "figure_path": "figures/lag1_selection_null.png",
    }

    for prefix, values in (
        ("r_fixed", r_fixed),
        ("r_max_mean", r_max_mean),
        ("r_max_r", r_max_r),
    ):
        quantiles = numpy.quantile(values, QUANTILE_LEVELS, method="linear")
        for percentile, value in zip((5, 25, 50, 75, 95), quantiles, strict=True):
            metrics[f"{prefix}_q{percentile:02d}"] = float(value)

    return metrics


def create_figure(
    r_fixed: numpy.ndarray,
    r_max_mean: numpy.ndarray,
    r_max_r: numpy.ndarray,
    metrics: dict[str, bool | float | int | str],
) -> None:
    """Create the required ECDF and density-histogram figure."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), dpi=150)

    ecdf_y = numpy.arange(1, N_EXPERIMENTS + 1, dtype=numpy.float64) / N_EXPERIMENTS
    for values, label, color in (
        (r_fixed, "Fixed candidate", "#1f77b4"),
        (r_max_mean, "Maximum-mean candidate", "#ff7f0e"),
    ):
        sorted_values = numpy.sort(values)
        axes[0].step(
            numpy.concatenate(([-1.0], sorted_values)),
            numpy.concatenate(([0.0], ecdf_y)),
            where="post",
            label=label,
            color=color,
            linewidth=1.5,
        )
    axes[0].set_xlabel("Lag-1 sample autocorrelation r")
    axes[0].set_ylabel("Empirical CDF")
    axes[0].set_xlim(-1.0, 1.0)
    axes[0].set_ylim(0.0, 1.0)
    axes[0].grid(alpha=0.2)
    axes[0].legend(loc="lower right")
    axes[0].set_title("Fixed vs. maximum-mean selection")
    axes[0].text(
        0.03,
        0.96,
        f"KS = {float(metrics['ks_r_fixed_vs_r_max_mean']):.5f}\n"
        f"decision threshold = {KS_THRESHOLD:.2f}",
        transform=axes[0].transAxes,
        ha="left",
        va="top",
        bbox={"facecolor": "white", "edgecolor": "0.7", "alpha": 0.9},
    )

    bins = numpy.linspace(-1, 1, 101)
    axes[1].hist(
        r_fixed,
        bins=bins,
        density=True,
        alpha=0.55,
        label="Fixed candidate",
        color="#1f77b4",
    )
    axes[1].hist(
        r_max_r,
        bins=bins,
        density=True,
        alpha=0.55,
        label="Maximum-r candidate",
        color="#2ca02c",
    )
    axes[1].axvline(
        R_THRESHOLD,
        color="black",
        linestyle="--",
        linewidth=1.5,
        label="r = 0.40",
    )
    axes[1].set_xlabel("Lag-1 sample autocorrelation r")
    axes[1].set_ylabel("Density")
    axes[1].set_xlim(-1.0, 1.0)
    axes[1].grid(alpha=0.2)
    axes[1].legend(loc="upper left")
    axes[1].set_title("Fixed vs. maximum-autocorrelation selection")
    axes[1].text(
        0.97,
        0.96,
        f"P(max r > 0.40) = {float(metrics['p_max_r_gt_0_40']):.5f}\n"
        f"decision threshold = {EXCEEDANCE_THRESHOLD:.2f}",
        transform=axes[1].transAxes,
        ha="right",
        va="top",
        bbox={"facecolor": "white", "edgecolor": "0.7", "alpha": 0.9},
    )

    fig.suptitle(
        "Lag-1 autocorrelation selection null: "
        "N=200,000, 32 candidates, length 20",
        fontsize=13,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(FIGURE_PATH, dpi=150)
    plt.close(fig)

    # Keep the canonical artifact under figures/ while also providing the exact
    # root-level filename requested by the protocol.
    if ROOT_FIGURE_PATH.is_symlink() or ROOT_FIGURE_PATH.exists():
        ROOT_FIGURE_PATH.unlink()
    os.symlink(FIGURE_PATH.relative_to(WORKSPACE), ROOT_FIGURE_PATH)


def write_json(path: Path, metrics: dict[str, bool | float | int | str]) -> None:
    """Write a stable, flat JSON object containing scalar values only."""
    if not all(isinstance(value, (bool, float, int, str)) for value in metrics.values()):
        raise TypeError("All result values must be JSON scalar values")
    path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    validate_environment()
    r_fixed, r_max_mean, r_max_r, verification_max_abs_diff = simulate()
    metrics = build_metrics(
        r_fixed,
        r_max_mean,
        r_max_r,
        verification_max_abs_diff,
    )
    create_figure(r_fixed, r_max_mean, r_max_r, metrics)
    write_json(METRICS_PATH, metrics)
    write_json(RESULTS_PATH, metrics)

    print(
        "Ran 200,000 independent pools of 32 length-20 Gaussian sequences "
        "in 40 batches."
    )
    print(
        f"KS(fixed, max-mean) = {float(metrics['ks_r_fixed_vs_r_max_mean']):.6f} "
        f"(required <= {KS_THRESHOLD:.2f})."
    )
    print(
        f"P(max-r > 0.40) = {float(metrics['p_max_r_gt_0_40']):.6f} "
        f"(required > {EXCEEDANCE_THRESHOLD:.2f}); "
        f"MCSE = {float(metrics['mcse_p_max_r_gt_0_40']):.6f}."
    )
    print(
        f"P(fixed > 0.40) = {float(metrics['p_fixed_gt_0_40']):.6f}; "
        f"P(max-mean > 0.40) = {float(metrics['p_max_mean_gt_0_40']):.6f}."
    )
    print(f"Decision: {metrics['decision']}.")


if __name__ == "__main__":
    main()
