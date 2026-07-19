#!/usr/bin/env python3
"""Run the deterministic paired-calibration selection experiment.

The implementation follows the locked protocol in the experiment request:
80 null-DGP splits, sixteen separate n=50 calibration samples per split,
selection over the fixed 21-by-21 affine-logit grid, and independent n=10,000
evaluation samples.
"""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / ".cache"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


BASE_SEED = 20250308
N_SPLITS = 80
N_CALIBRATION_SAMPLES = 16
N_CALIBRATION = 50
N_EVALUATION = 10_000
N_BINS = 15
THRESHOLD = 0.08

CSV_PATH = ROOT / "split_results.csv"
SUMMARY_PATH = ROOT / "summary.json"
RESULTS_PATH = ROOT / "results.json"
FIGURE_DIR = ROOT / "figures"
FIGURE_PATH = FIGURE_DIR / "paired_calibration_effects.png"
ROOT_FIGURE_PATH = ROOT / "paired_calibration_effects.png"

CSV_COLUMNS = [
    "split",
    "selected_a",
    "selected_b",
    "selected_calibration_objective",
    "identity_reused_mean_ece",
    "selected_reused_mean_ece",
    "reused_paired_reduction",
    "identity_evaluation_ece",
    "selected_evaluation_ece",
    "evaluation_paired_reduction",
]


def sigmoid(x: np.ndarray) -> np.ndarray:
    """Compute the logistic sigmoid (the protocol's range cannot overflow)."""

    return 1.0 / (1.0 + np.exp(-x))


def affine_logit_predictions(
    q: np.ndarray, candidate_a: np.ndarray, candidate_b: np.ndarray
) -> np.ndarray:
    """Return predictions for every candidate, with shape (candidates, n)."""

    clipped = np.clip(q, 1e-12, 1.0 - 1e-12)
    logits = np.log(clipped) - np.log1p(-clipped)
    return sigmoid(candidate_a[:, None] * logits[None, :] + candidate_b[:, None])


def ece_many(predictions: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Compute fixed 15-bin ECE independently for each prediction row.

    For a bin k, (n_k/n)*abs(mean(y)-mean(p)) simplifies exactly to
    abs(sum(y)-sum(p))/n. Bincount offsets keep every candidate's bins
    separate without pooling samples or candidates.
    """

    if predictions.ndim != 2 or predictions.shape[1] != y.size:
        raise ValueError("predictions must have shape (candidates, len(y))")
    n_candidates, n = predictions.shape
    bins = np.minimum(np.floor(N_BINS * predictions).astype(np.int64), N_BINS - 1)
    offsets = np.arange(n_candidates, dtype=np.int64)[:, None] * N_BINS
    flat_bin_ids = (bins + offsets).ravel()
    minlength = n_candidates * N_BINS
    tiled_y = np.broadcast_to(y, predictions.shape).ravel()
    y_sums = np.bincount(flat_bin_ids, weights=tiled_y, minlength=minlength)
    p_sums = np.bincount(
        flat_bin_ids, weights=predictions.ravel(), minlength=minlength
    )
    return np.abs(y_sums - p_sums).reshape(n_candidates, N_BINS).sum(axis=1) / n


def ece(predictions: np.ndarray, y: np.ndarray) -> float:
    """Compute fixed equal-width 15-bin ECE for one prediction vector."""

    return float(ece_many(np.asarray(predictions)[None, :], np.asarray(y))[0])


def make_sample(seed_components: list[int], n: int) -> tuple[np.ndarray, np.ndarray]:
    """Draw q and Y from the null DGP using the prescribed PCG64 seed."""

    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed_components)))
    q = rng.random(n)
    y = (rng.random(n) < q).astype(int)
    return q, y


def mean_sd_interval(values: np.ndarray) -> dict[str, float]:
    """Return mean, sample SD, SE, and normal-approximation 95% interval."""

    mean = float(np.mean(values))
    sd = float(np.std(values, ddof=1))
    se = sd / math.sqrt(values.size)
    return {
        "mean": mean,
        "sample_sd": sd,
        "standard_error": se,
        "normal_95_ci_lower": mean - 1.96 * se,
        "normal_95_ci_upper": mean + 1.96 * se,
    }


def make_figure(reused: np.ndarray, evaluation: np.ndarray) -> None:
    """Create the specified two-panel paired-effect figure."""

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    splits = np.arange(N_SPLITS)
    fig, axes = plt.subplots(1, 2, figsize=(16, 7), dpi=120, sharey=False)

    axes[0].plot(splits, reused, marker="o", markersize=3.5, linewidth=0.9)
    axes[0].axhline(float(np.mean(reused)), color="black", linewidth=1.8,
                    label=f"Mean = {np.mean(reused):.4f}")
    axes[0].axhline(0.0, color="gray", linestyle="--", linewidth=1.2,
                    label="Zero")
    axes[0].axhline(THRESHOLD, color="red", linestyle="--", linewidth=1.5,
                    label="Threshold = 0.08")
    axes[0].set_title("Reused calibration samples (16 x n=50)")
    axes[0].set_xlabel("Split")
    axes[0].set_ylabel("Identity ECE minus selected ECE")
    axes[0].legend(loc="best")
    axes[0].grid(alpha=0.22)

    axes[1].plot(splits, evaluation, marker="o", markersize=3.5, linewidth=0.9,
                 color="#d97706")
    axes[1].axhline(float(np.mean(evaluation)), color="black", linewidth=1.8,
                    label=f"Mean = {np.mean(evaluation):.4f}")
    axes[1].axhline(0.0, color="gray", linestyle="--", linewidth=1.2,
                    label="Zero")
    axes[1].set_title("Independent evaluation samples (n=10,000)")
    axes[1].set_xlabel("Split")
    axes[1].set_ylabel("Identity ECE minus selected ECE")
    axes[1].legend(loc="best")
    axes[1].grid(alpha=0.22)

    fig.suptitle(
        "Paired ECE effects: positive favors selected calibrator; negative favors identity",
        fontsize=14,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(FIGURE_PATH, dpi=120)
    plt.close(fig)
    # Keep the convention-compliant figure under figures/ and also provide the
    # exact root-level filename requested by the experimental protocol.
    shutil.copyfile(FIGURE_PATH, ROOT_FIGURE_PATH)


def run_experiment() -> tuple[list[dict[str, int | float]], dict, dict]:
    """Run all splits and return row-level, detailed, and flat summaries."""

    # Lock the complete ordered grid before generating any data.
    grid_a = np.linspace(0.0, 2.0, 21)
    grid_b = np.linspace(-2.0, 2.0, 21)
    candidates = [(float(a), float(b)) for a in grid_a for b in grid_b]
    candidate_a = np.asarray([pair[0] for pair in candidates], dtype=np.float64)
    candidate_b = np.asarray([pair[1] for pair in candidates], dtype=np.float64)

    if len(candidates) != 441 or candidates[220] != (1.0, 0.0):
        raise AssertionError("locked grid or identity position is incorrect")

    rows: list[dict[str, int | float]] = []

    for split in range(N_SPLITS):
        candidate_objective_sum = np.zeros(len(candidates), dtype=np.float64)
        identity_reused_eces = np.empty(N_CALIBRATION_SAMPLES, dtype=np.float64)
        candidate_sample_eces = np.empty(
            (N_CALIBRATION_SAMPLES, len(candidates)), dtype=np.float64
        )

        for sample_index in range(N_CALIBRATION_SAMPLES):
            q, y = make_sample(
                [BASE_SEED, split, 0, sample_index], N_CALIBRATION
            )
            predictions = affine_logit_predictions(q, candidate_a, candidate_b)
            sample_eces = ece_many(predictions, y)
            candidate_sample_eces[sample_index] = sample_eces
            candidate_objective_sum += sample_eces
            # Identity is explicitly recomputed from q, not taken from the grid.
            identity_reused_eces[sample_index] = ece(q, y)

        candidate_objectives = candidate_objective_sum / N_CALIBRATION_SAMPLES
        selected_index = int(np.argmin(candidate_objectives))
        selected_a, selected_b = candidates[selected_index]
        selected_reused_eces = candidate_sample_eces[:, selected_index]
        identity_reused_mean = float(np.mean(identity_reused_eces))
        selected_reused_mean = float(np.mean(selected_reused_eces))
        reused_reduction = float(
            np.mean(identity_reused_eces - selected_reused_eces)
        )

        q_eval, y_eval = make_sample([BASE_SEED, split, 1, 0], N_EVALUATION)
        selected_eval_predictions = affine_logit_predictions(
            q_eval,
            np.asarray([selected_a], dtype=np.float64),
            np.asarray([selected_b], dtype=np.float64),
        )[0]
        identity_eval_ece = ece(q_eval, y_eval)
        selected_eval_ece = ece(selected_eval_predictions, y_eval)
        evaluation_reduction = identity_eval_ece - selected_eval_ece

        # The selected objective and reused selected mean are the same quantity,
        # calculated from the sixteen separate sample ECEs.
        if not np.isclose(
            candidate_objectives[selected_index], selected_reused_mean,
            rtol=0.0, atol=2e-16
        ):
            raise AssertionError("selected objective disagrees with reused mean ECE")

        rows.append(
            {
                "split": split,
                "selected_a": selected_a,
                "selected_b": selected_b,
                "selected_calibration_objective": float(
                    candidate_objectives[selected_index]
                ),
                "identity_reused_mean_ece": identity_reused_mean,
                "selected_reused_mean_ece": selected_reused_mean,
                "reused_paired_reduction": reused_reduction,
                "identity_evaluation_ece": identity_eval_ece,
                "selected_evaluation_ece": selected_eval_ece,
                "evaluation_paired_reduction": evaluation_reduction,
            }
        )

    reused = np.asarray([row["reused_paired_reduction"] for row in rows])
    evaluation = np.asarray([row["evaluation_paired_reduction"] for row in rows])
    identity_eval = np.asarray([row["identity_evaluation_ece"] for row in rows])
    selected_eval = np.asarray([row["selected_evaluation_ece"] for row in rows])
    reused_stats = mean_sd_interval(reused)
    evaluation_stats = mean_sd_interval(evaluation)

    mean_identity_eval = float(np.mean(identity_eval))
    mean_selected_eval = float(np.mean(selected_eval))
    identity_win_count = int(np.sum(identity_eval < selected_eval))
    identity_win_rate = identity_win_count / N_SPLITS
    condition_a = reused_stats["mean"] >= THRESHOLD
    condition_b = evaluation_stats["mean"] <= 0.0
    condition_identity_mean = mean_identity_eval < mean_selected_eval
    supported = bool(condition_a and condition_b and condition_identity_mean)
    decision = "SUPPORTED" if supported else "REFUTED"

    selected_pairs = [(float(row["selected_a"]), float(row["selected_b"])) for row in rows]
    pair_counts = Counter(selected_pairs)
    distribution = [
        {
            "a": pair[0],
            "b": pair[1],
            "count": count,
            "frequency": count / N_SPLITS,
        }
        for pair, count in sorted(
            pair_counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1])
        )
    ]
    most_common = distribution[0]
    identity_selected_count = pair_counts.get((1.0, 0.0), 0)

    summary = {
        "protocol": {
            "base_seed": BASE_SEED,
            "splits": N_SPLITS,
            "calibration_samples_per_split": N_CALIBRATION_SAMPLES,
            "calibration_sample_size": N_CALIBRATION,
            "evaluation_sample_size": N_EVALUATION,
            "ece_bins": N_BINS,
            "grid_a_points": 21,
            "grid_b_points": 21,
            "candidate_count": len(candidates),
            "apparent_effect_threshold": THRESHOLD,
        },
        "reused_paired_reduction": reused_stats,
        "evaluation_paired_reduction": evaluation_stats,
        "mean_identity_evaluation_ece": mean_identity_eval,
        "mean_selected_evaluation_ece": mean_selected_eval,
        "identity_evaluation_win_count": identity_win_count,
        "identity_evaluation_win_rate": identity_win_rate,
        "selected_parameter_distribution": distribution,
        "decision_conditions": {
            "mean_reused_reduction_at_least_0.08": bool(condition_a),
            "mean_evaluation_reduction_nonpositive": bool(condition_b),
            "identity_mean_evaluation_ece_lower": bool(condition_identity_mean),
        },
        "hypothesis_supported": supported,
        "decision": decision,
    }

    # results.json is deliberately flat, with only scalar JSON values.
    flat_results = {
        "mean_reused_paired_ece_reduction_A": reused_stats["mean"],
        "reused_paired_reduction_sample_sd": reused_stats["sample_sd"],
        "reused_paired_reduction_normal_95_ci_lower": reused_stats[
            "normal_95_ci_lower"
        ],
        "reused_paired_reduction_normal_95_ci_upper": reused_stats[
            "normal_95_ci_upper"
        ],
        "mean_independent_paired_ece_reduction_B": evaluation_stats["mean"],
        "evaluation_paired_reduction_sample_sd": evaluation_stats["sample_sd"],
        "evaluation_paired_reduction_normal_95_ci_lower": evaluation_stats[
            "normal_95_ci_lower"
        ],
        "evaluation_paired_reduction_normal_95_ci_upper": evaluation_stats[
            "normal_95_ci_upper"
        ],
        "mean_identity_evaluation_ece": mean_identity_eval,
        "mean_selected_evaluation_ece": mean_selected_eval,
        "identity_evaluation_win_count": identity_win_count,
        "identity_evaluation_win_rate": identity_win_rate,
        "unique_selected_parameter_pairs": len(pair_counts),
        "identity_selected_count": identity_selected_count,
        "identity_selected_frequency": identity_selected_count / N_SPLITS,
        "most_common_selected_a": most_common["a"],
        "most_common_selected_b": most_common["b"],
        "most_common_selected_count": most_common["count"],
        "most_common_selected_frequency": most_common["frequency"],
        "selected_parameter_distribution_json": json.dumps(
            distribution, separators=(",", ":")
        ),
        "condition_A_at_least_0.08": bool(condition_a),
        "condition_B_nonpositive": bool(condition_b),
        "condition_identity_mean_ece_lower": bool(condition_identity_mean),
        "hypothesis_supported": supported,
        "decision": decision,
        "n_splits": N_SPLITS,
        "calibration_samples_per_split": N_CALIBRATION_SAMPLES,
        "calibration_sample_size": N_CALIBRATION,
        "evaluation_sample_size": N_EVALUATION,
        "candidate_count": len(candidates),
        "ece_bin_count": N_BINS,
        "base_seed": BASE_SEED,
    }

    return rows, summary, flat_results


def write_outputs(rows: list[dict], summary: dict, flat_results: dict) -> None:
    """Write all requested tabular, JSON, and visual outputs."""

    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    with SUMMARY_PATH.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")

    with RESULTS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(flat_results, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")

    reused = np.asarray([row["reused_paired_reduction"] for row in rows])
    evaluation = np.asarray([row["evaluation_paired_reduction"] for row in rows])
    make_figure(reused, evaluation)


def main() -> None:
    rows, summary, flat_results = run_experiment()
    write_outputs(rows, summary, flat_results)
    print(
        "Ran 80 deterministic null-DGP splits with 16 separate n=50 calibration "
        "samples, the locked 441-candidate grid, and independent n=10000 evaluation."
    )
    print(
        f"A (mean reused paired ECE reduction) = "
        f"{flat_results['mean_reused_paired_ece_reduction_A']:.9f}; "
        f"B (mean independent paired ECE reduction) = "
        f"{flat_results['mean_independent_paired_ece_reduction_B']:.9f}."
    )
    print(
        f"Mean evaluation ECE: identity = "
        f"{flat_results['mean_identity_evaluation_ece']:.9f}, selected = "
        f"{flat_results['mean_selected_evaluation_ece']:.9f}; identity win rate = "
        f"{flat_results['identity_evaluation_win_rate']:.3f}."
    )
    print(f"Decision: {summary['decision']}.")


if __name__ == "__main__":
    main()
