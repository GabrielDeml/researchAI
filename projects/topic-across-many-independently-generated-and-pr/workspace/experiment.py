#!/usr/bin/env python3
"""Run the preregistered overlapping-versus-disjoint block experiment."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".mplconfig"))
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / ".cache"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


MASTER_SEED = 20250308
BOOTSTRAP_SEED = 8675309
N_SEEDS = 1_000
N_OBS = 256
N_RULES = 6
BLOCK_SIZE = 48
N_WINDOWS = N_SEEDS - BLOCK_SIZE + 1
N_DISJOINT = 20
N_BOOTSTRAP = 2_000
MIN_TREATED = 500
MIN_CONTROL = 500
DECISION_THRESHOLD = 0.25

FIGURES_DIR = ROOT / "figures"

# Last dimension of the sufficient-statistic record.
ELIGIBLE_COUNT = 0
TREATED_COUNT = 1
TREATED_SUM = 2
CONTROL_COUNT = 3
CONTROL_SUM = 4


def simulate_seed_records() -> np.ndarray:
    """Return records[seed, split, rule, statistic].

    Split 0 is development and split 1 is held-out. Each spawned child stream
    generates the complete development split before the complete held-out split.
    """
    children = np.random.SeedSequence(MASTER_SEED).spawn(N_SEEDS)
    records = np.empty((N_SEEDS, 2, N_RULES, 5), dtype=np.float64)

    for seed_index, child in enumerate(children):
        rng = np.random.default_rng(child)
        for split_index in range(2):
            x = rng.binomial(1, 0.5, size=(N_OBS, N_RULES))
            treatment = rng.binomial(1, 0.5, size=N_OBS)
            epsilon = rng.normal(0.0, 1.0, size=N_OBS)
            tau = 0.15 + 0.10 * x[:, 0]
            outcome = treatment * tau + epsilon

            for rule_index in range(N_RULES):
                eligible = x[:, rule_index] == 1
                treated = eligible & (treatment == 1)
                control = eligible & (treatment == 0)
                records[seed_index, split_index, rule_index] = (
                    eligible.sum(),
                    treated.sum(),
                    outcome[treated].sum(),
                    control.sum(),
                    outcome[control].sum(),
                )
    return records


def contiguous_window_sums(records: np.ndarray) -> np.ndarray:
    """Pool sufficient statistics in every stride-1 BLOCK_SIZE window."""
    prefix = np.concatenate(
        [np.zeros((1,) + records.shape[1:], dtype=np.float64), np.cumsum(records, axis=0)],
        axis=0,
    )
    return prefix[BLOCK_SIZE:] - prefix[:-BLOCK_SIZE]


def disjoint_block_sums(records: np.ndarray) -> np.ndarray:
    """Pool the first 960 seed records into 20 prospective disjoint blocks."""
    used = records[: N_DISJOINT * BLOCK_SIZE]
    return used.reshape((N_DISJOINT, BLOCK_SIZE) + records.shape[1:]).sum(axis=1)


def uplift(split_stats: np.ndarray) -> np.ndarray:
    """Compute rule uplift from pooled stats ending in [rule, statistic]."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return (
            split_stats[..., TREATED_SUM] / split_stats[..., TREATED_COUNT]
            - split_stats[..., CONTROL_SUM] / split_stats[..., CONTROL_COUNT]
        )


def analyze_pooled_blocks(
    pooled: np.ndarray,
    analysis: str,
    starts: np.ndarray,
) -> pd.DataFrame:
    """Apply prospective development-only rule selection to pooled blocks."""
    dev = pooled[:, 0]
    hold = pooled[:, 1]
    eligible = (
        (dev[..., TREATED_COUNT] >= MIN_TREATED)
        & (dev[..., CONTROL_COUNT] >= MIN_CONTROL)
    )
    dev_uplifts = uplift(dev)
    selectable_uplifts = np.where(eligible, dev_uplifts, -np.inf)
    any_eligible = eligible.any(axis=1)

    # np.argmax returns the first maximum, implementing the lowest-rule tie-break.
    selected = np.argmax(selectable_uplifts, axis=1)
    row = np.arange(len(pooled))
    selected_dev = dev_uplifts[row, selected]
    selected_hold = uplift(hold)[row, selected]
    selected_n = dev[row, selected, ELIGIBLE_COUNT]
    retention = selected_hold / selected_dev
    decision = (selected_dev >= DECISION_THRESHOLD).astype(float)

    selected_dev = np.where(any_eligible, selected_dev, np.nan)
    selected_hold = np.where(any_eligible, selected_hold, np.nan)
    selected_n = np.where(any_eligible, selected_n, np.nan)
    retention = np.where(any_eligible, retention, np.nan)
    decision = np.where(any_eligible, decision, np.nan)
    selected_rule = np.where(any_eligible, selected + 1, np.nan)

    return pd.DataFrame(
        {
            "analysis": analysis,
            "block_id": np.arange(len(pooled), dtype=int),
            "start_seed": starts,
            "end_seed": starts + BLOCK_SIZE - 1,
            "selected_rule": selected_rule,
            "U_dev": selected_dev,
            "N_eligible": selected_n,
            "U_hold": selected_hold,
            "H": retention,
            "D": decision,
            "n_eligible_rules": eligible.sum(axis=1),
        }
    )


def distribution_summary(values: pd.Series) -> dict[str, int | float]:
    """Return exactly the requested descriptive statistics."""
    clean = values.dropna().to_numpy(dtype=float)
    if clean.size == 0:
        return {
            "count": 0,
            "mean": math.nan,
            "sample_std": math.nan,
            "minimum": math.nan,
            "p05": math.nan,
            "p25": math.nan,
            "p50": math.nan,
            "p75": math.nan,
            "p95": math.nan,
            "maximum": math.nan,
        }
    percentiles = np.percentile(clean, [5, 25, 50, 75, 95])
    return {
        "count": int(clean.size),
        "mean": float(np.mean(clean)),
        "sample_std": float(np.std(clean, ddof=1)),
        "minimum": float(np.min(clean)),
        "p05": float(percentiles[0]),
        "p25": float(percentiles[1]),
        "p50": float(percentiles[2]),
        "p75": float(percentiles[3]),
        "p95": float(percentiles[4]),
        "maximum": float(np.max(clean)),
    }


def rule_identity_summary(values: pd.Series) -> dict[str, dict[str, int | float]]:
    valid = values.dropna().astype(int)
    denominator = len(valid)
    result: dict[str, dict[str, int | float]] = {}
    for rule in range(1, N_RULES + 1):
        count = int((valid == rule).sum())
        result[f"R{rule}"] = {
            "count": count,
            "proportion": float(count / denominator) if denominator else math.nan,
        }
    return result


def lag1_autocorrelation(values: pd.Series | np.ndarray) -> float | None:
    z = np.asarray(values, dtype=float)
    if z.size < 2 or np.isnan(z).any():
        return None
    left, right = z[:-1], z[1:]
    if np.var(left) == 0.0 or np.var(right) == 0.0:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def bootstrap_decision_se(records: np.ndarray) -> tuple[float, np.ndarray]:
    """Bootstrap independent seed records and recompute all overlap decisions."""
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    rates = np.empty(N_BOOTSTRAP, dtype=float)
    for replicate in range(N_BOOTSTRAP):
        indices = rng.choice(N_SEEDS, size=N_SEEDS, replace=True)
        # This array preserves each sampled seed's complete dev and held-out record.
        sampled_records = records[indices]
        pooled = contiguous_window_sums(sampled_records)
        dev = pooled[:, 0]
        eligible = (
            (dev[..., TREATED_COUNT] >= MIN_TREATED)
            & (dev[..., CONTROL_COUNT] >= MIN_CONTROL)
        )
        selectable = np.where(eligible, uplift(dev), -np.inf)
        selected_dev = np.max(selectable, axis=1)
        decisions = selected_dev >= DECISION_THRESHOLD
        rates[replicate] = float(np.mean(decisions))
    return float(np.std(rates, ddof=1)), rates


def analysis_summary(frame: pd.DataFrame) -> dict[str, Any]:
    valid_decisions = frame["D"].dropna()
    return {
        "n_blocks": int(len(frame)),
        "selected_rule_uplift": distribution_summary(frame["U_dev"]),
        "held_out_retention": distribution_summary(frame["H"]),
        "eligible_sample_size": distribution_summary(frame["N_eligible"]),
        "selected_rule_identity": rule_identity_summary(frame["selected_rule"]),
        "threshold_decision_count": int(valid_decisions.sum()),
        "threshold_decision_rate": float(valid_decisions.mean()),
        "no_eligible_rule_count": int(frame["selected_rule"].isna().sum()),
    }


def sanitize_json(value: Any) -> Any:
    """Convert NumPy values and non-finite floats into strict JSON values."""
    if isinstance(value, dict):
        return {str(k): sanitize_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_json(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def flatten_scalars(value: Any, prefix: str = "") -> dict[str, int | float | str | bool]:
    """Flatten structured metrics into the mandatory scalar-only results object."""
    output: dict[str, int | float | str | bool] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}__{key}" if prefix else str(key)
            output.update(flatten_scalars(item, child))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            output.update(flatten_scalars(item, f"{prefix}__{index}"))
    else:
        output[prefix] = "undefined" if value is None else value
    return output


def make_figure(
    overlap: pd.DataFrame,
    correlations: dict[str, float | None],
    se_naive: float,
    se_bootstrap: float,
    factor: float | None,
) -> None:
    FIGURES_DIR.mkdir(exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)

    ax = axes[0, 0]
    ax.plot(overlap["start_seed"], overlap["U_dev"], linewidth=1.1, color="#1f77b4")
    ax.axhline(DECISION_THRESHOLD, color="#d62728", linestyle="--", linewidth=1.2)
    ax.set_title("A. Overlapping selected development uplift")
    ax.set_xlabel("Window start seed")
    ax.set_ylabel("Selected development uplift (U_dev)")

    ax = axes[0, 1]
    ax.step(overlap["start_seed"], overlap["D"], where="post", linewidth=1.1, color="#2ca02c")
    ax.set_ylim(-0.1, 1.1)
    ax.set_yticks([0, 1])
    ax.set_title("B. Overlapping threshold decisions")
    ax.set_xlabel("Window start seed")
    ax.set_ylabel("Decision (D)")

    ax = axes[1, 0]
    group_x = np.arange(2)
    width = 0.34
    uplift_keys = ["overlap_uplift", "disjoint_uplift"]
    decision_keys = ["overlap_decision", "disjoint_decision"]
    uplift_values = [correlations[key] if correlations[key] is not None else 0.0 for key in uplift_keys]
    decision_values = [correlations[key] if correlations[key] is not None else 0.0 for key in decision_keys]
    uplift_bars = ax.bar(group_x - width / 2, uplift_values, width, label="Uplift", color="#4c78a8")
    decision_bars = ax.bar(group_x + width / 2, decision_values, width, label="Decision", color="#e45756")
    for bar, key in zip([*uplift_bars, *decision_bars], [*uplift_keys, *decision_keys], strict=True):
        if correlations[key] is None:
            ax.text(bar.get_x() + bar.get_width() / 2, 0.02, "undefined", ha="center", va="bottom", rotation=90)
    for reference, style in [(0.90, "--"), (0.80, ":"), (0.10, "--"), (-0.10, "--")]:
        ax.axhline(reference, color="black", linestyle=style, linewidth=0.8, alpha=0.55)
    ax.set_title("C. Lag-1 autocorrelations")
    ax.set_xlabel("Block construction")
    ax.set_ylabel("Lag-1 autocorrelation")
    ax.set_xticks(group_x, ["Overlapping", "Disjoint"])
    ax.legend(loc="lower left")
    ax.set_ylim(-1.0, 1.05)

    ax = axes[1, 1]
    bars = ax.bar(["Naive", "Seed bootstrap"], [se_naive, se_bootstrap], color=["#9ecae9", "#3182bd"])
    ax.set_title("D. Monte Carlo standard errors")
    ax.set_xlabel("Estimator")
    ax.set_ylabel("Standard error of decision rate")
    ax.set_ylim(0.0, max(se_naive, se_bootstrap) * 1.18)
    factor_text = "undefined" if factor is None else ("infinity" if math.isinf(factor) else f"{factor:.3f}x")
    ax.text(0.5, 0.95, f"F = {factor_text}", transform=ax.transAxes, ha="center", va="top", fontsize=11)
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f"{height:.6f}", (bar.get_x() + bar.get_width() / 2, height), xytext=(0, 4), textcoords="offset points", ha="center", va="bottom")

    figure_path = FIGURES_DIR / "key_results.png"
    fig.savefig(figure_path, dpi=180)
    plt.close(fig)


def main() -> None:
    records = simulate_seed_records()
    overlap_pooled = contiguous_window_sums(records)
    disjoint_pooled = disjoint_block_sums(records)
    overlap = analyze_pooled_blocks(overlap_pooled, "overlapping", np.arange(N_WINDOWS))
    disjoint_starts = np.arange(N_DISJOINT) * BLOCK_SIZE
    disjoint = analyze_pooled_blocks(disjoint_pooled, "disjoint", disjoint_starts)
    block_results = pd.concat([overlap, disjoint], ignore_index=True)
    block_results.to_csv(ROOT / "block_results.csv", index=False, float_format="%.12g")

    overlap_summary = analysis_summary(overlap)
    disjoint_summary = analysis_summary(disjoint)
    correlations = {
        "overlap_uplift": lag1_autocorrelation(overlap["U_dev"]),
        "overlap_decision": lag1_autocorrelation(overlap["D"]),
        "disjoint_uplift": lag1_autocorrelation(disjoint["U_dev"]),
        "disjoint_decision": lag1_autocorrelation(disjoint["D"]),
    }

    p_overlap = overlap_summary["threshold_decision_rate"]
    se_naive = float(math.sqrt(p_overlap * (1.0 - p_overlap) / N_WINDOWS))
    se_bootstrap, bootstrap_rates = bootstrap_decision_se(records)
    if se_naive == 0.0:
        factor = math.inf if se_bootstrap > 0.0 else None
    else:
        factor = float(se_bootstrap / se_naive)

    criteria = {
        "overlap_uplift_autocorrelation_gt_0_90": (
            correlations["overlap_uplift"] is not None
            and correlations["overlap_uplift"] > 0.90
        ),
        "overlap_decision_autocorrelation_gt_0_80": (
            correlations["overlap_decision"] is not None
            and correlations["overlap_decision"] > 0.80
        ),
        "abs_disjoint_uplift_autocorrelation_lt_0_10": (
            correlations["disjoint_uplift"] is not None
            and abs(correlations["disjoint_uplift"]) < 0.10
        ),
        "abs_disjoint_decision_autocorrelation_lt_0_10": (
            correlations["disjoint_decision"] is not None
            and abs(correlations["disjoint_decision"]) < 0.10
        ),
        "se_underestimation_factor_ge_3_00": (
            factor is not None and factor >= 3.00
        ),
    }
    hypothesis_supported = bool(all(criteria.values()))

    metrics = {
        "experiment": "overlapping_stride1_vs_disjoint_48_seed_blocks",
        "master_seed": MASTER_SEED,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "n_seed_experiments": N_SEEDS,
        "observations_per_split_per_seed": N_OBS,
        "block_size": BLOCK_SIZE,
        "n_overlapping_windows": N_WINDOWS,
        "n_disjoint_blocks": N_DISJOINT,
        "n_bootstrap_replicates": N_BOOTSTRAP,
        "overlapping": overlap_summary,
        "disjoint": disjoint_summary,
        "lag1_autocorrelations": correlations,
        "overlapping_threshold_rate": p_overlap,
        "overlapping_threshold_se_naive": se_naive,
        "overlapping_threshold_se_bootstrap": se_bootstrap,
        "se_underestimation_factor": factor,
        "bootstrap_rate_mean": float(np.mean(bootstrap_rates)),
        "bootstrap_rate_minimum": float(np.min(bootstrap_rates)),
        "bootstrap_rate_maximum": float(np.max(bootstrap_rates)),
        "criteria": criteria,
        "hypothesis_supported": hypothesis_supported,
        "hypothesis_conclusion": "supported" if hypothesis_supported else "refuted",
    }
    clean_metrics = sanitize_json(metrics)
    with (ROOT / "metrics.json").open("w", encoding="utf-8") as handle:
        json.dump(clean_metrics, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")

    flat_results = flatten_scalars(clean_metrics)
    with (ROOT / "results.json").open("w", encoding="utf-8") as handle:
        json.dump(flat_results, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")

    make_figure(overlap, correlations, se_naive, se_bootstrap, factor)

    print("Completed 1,000 seed experiments, 953 overlapping windows, 20 disjoint blocks,")
    print("and 2,000 seed-record bootstrap replicates.")
    print(
        "Lag-1 correlations (overlap uplift/decision, disjoint uplift/decision): "
        + ", ".join("undefined" if value is None else f"{value:.6f}" for value in correlations.values())
    )
    print(
        f"Overlap decision rate={p_overlap:.6f}; SE naive={se_naive:.6f}; "
        f"SE bootstrap={se_bootstrap:.6f}; F={factor if factor is not None else 'undefined'}"
    )
    print(f"Hypothesis: {'SUPPORTED' if hypothesis_supported else 'REFUTED'} ({sum(criteria.values())}/5 criteria passed).")


if __name__ == "__main__":
    main()
