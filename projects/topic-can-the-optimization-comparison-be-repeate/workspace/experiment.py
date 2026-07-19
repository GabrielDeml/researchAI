#!/usr/bin/env python3
"""Run the preregistered OneMax calibration-optimism experiment.

The script writes the preregistration before calibration, persists calibration
selection before touching validation seeds, and then runs the held-out serial
and batch-size-16 comparison. Genomes are bit-packed unsigned integers and no
per-evaluation histories are retained.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


N_BITS = 20
OPTIMUM = np.uint32((1 << N_BITS) - 1)
POPULATION_GRID = (4, 12)
MUTATION_MULTIPLIERS = (0.5, 1.0, 2.0)
BUDGET_GRID = (80, 160, 320)
N_SPLITS = 120
N_CALIBRATION = 16
N_VALIDATION = 128
TARGET_RATE = 0.50
BATCH_SIZE = 16
OPTIMISM_THRESHOLD = 0.08
BOOTSTRAP_SEED = 20250308
N_BOOTSTRAP = 20_000
BASE_SEED_START = 10_000_000
BASE_SEED_STRIDE = 10_000
VALIDATION_SEED_OFFSET = 1_000
MUTATION_TIE_RANK = {1.0: 0, 0.5: 1, 2.0: 2}
BIT_WEIGHTS = np.left_shift(np.uint32(1), np.arange(N_BITS, dtype=np.uint32))

RESULT_COLUMNS = [
    "split",
    "selected_P",
    "selected_mutation_multiplier",
    "selected_p",
    "selected_B",
    "calibration_success_rate",
    "validation_serial_success_rate",
    "validation_batch_success_rate",
    "calibration_target_deviation",
    "validation_target_deviation",
    "delta",
    "batch_minus_serial",
]


@dataclass(frozen=True)
class Setting:
    population_size: int
    mutation_multiplier: float
    budget: int

    @property
    def mutation_probability(self) -> float:
        return self.mutation_multiplier / N_BITS


def versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "matplotlib": matplotlib.__version__,
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def preregistration() -> dict[str, Any]:
    return {
        "status": "locked before calibration and validation",
        "objective": "20-bit OneMax; success iff the all-ones genome is evaluated",
        "candidate_grid": {
            "population_size": list(POPULATION_GRID),
            "mutation_multiplier": list(MUTATION_MULTIPLIERS),
            "mutation_probability": [m / N_BITS for m in MUTATION_MULTIPLIERS],
            "total_evaluation_budget": list(BUDGET_GRID),
        },
        "calibration_target": TARGET_RATE,
        "selection_tie_break": [
            "smaller total evaluation budget",
            "smaller population size",
            "mutation multiplier order 1, 0.5, 2",
        ],
        "split_count": N_SPLITS,
        "calibration_seeds_per_split": N_CALIBRATION,
        "validation_seeds_per_split": N_VALIDATION,
        "base_seed_formula": "10000000 + 10000 * split",
        "calibration_seed_formula": "base + j, j=0,...,15",
        "validation_seed_formula": "base + 1000 + j, j=0,...,127",
        "primary_effect": "D = median_i(|v_i-0.50| - |c_i-0.50|)",
        "primary_threshold": OPTIMISM_THRESHOLD,
        "primary_confidence_interval": (
            "95% paired split-level percentile bootstrap; 20000 resamples of "
            "120 splits; numpy.quantile method=linear"
        ),
        "primary_decision": {
            "supported": "bootstrap lower bound >= 0.08",
            "refuted": "bootstrap upper bound < 0.08",
            "otherwise": "inconclusive",
        },
        "regime_check": (
            "at least 96 of 120 selected calibration rates must be in [0.25, 0.75]; "
            "failure overrides the primary decision"
        ),
        "secondary_effect": (
            "Q = mean over splits of mean over held-out paired seeds of "
            "batch_success - serial_success"
        ),
        "secondary_confidence_interval": (
            "95% cluster-bootstrap interval using the exact same split resamples as D"
        ),
        "secondary_decision": {
            "batch_size_16_superior": "bootstrap lower bound > 0",
            "serial_superior": "bootstrap upper bound < 0",
            "otherwise": "no decisive difference",
        },
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_resamples": N_BOOTSTRAP,
        "batch_size": BATCH_SIZE,
        "rng": "numpy.random.Generator(numpy.random.PCG64(seed)), separately per run",
        "package_versions_at_lock": versions(),
    }


def all_settings() -> tuple[Setting, ...]:
    return tuple(
        Setting(population_size, multiplier, budget)
        for population_size in POPULATION_GRID
        for multiplier in MUTATION_MULTIPLIERS
        for budget in BUDGET_GRID
    )


def mutation_mask(rng: np.random.Generator, probability: float) -> np.uint32:
    flips = rng.random(N_BITS) < probability
    return np.uint32(flips.astype(np.uint32) @ BIT_WEIGHTS)


def initialize(
    rng: np.random.Generator, population_size: int
) -> tuple[np.ndarray, np.ndarray, bool]:
    population = rng.integers(
        0, 1 << N_BITS, size=population_size, dtype=np.uint32
    )
    fitnesses = np.fromiter(
        (int(genome).bit_count() for genome in population),
        dtype=np.int8,
        count=population_size,
    )
    return population, fitnesses, bool(np.any(population == OPTIMUM))


def choose_parent(
    rng: np.random.Generator, population: np.ndarray, fitnesses: np.ndarray
) -> np.uint32:
    sampled = rng.integers(0, len(population), size=2)
    first = int(sampled[0])
    second = int(sampled[1])
    # >= is the specified first-index tie break.
    parent_index = first if fitnesses[first] >= fitnesses[second] else second
    return population[parent_index]


def replace_if_eligible(
    rng: np.random.Generator,
    population: np.ndarray,
    fitnesses: np.ndarray,
    child: np.uint32,
    child_fitness: int,
) -> None:
    minimum_fitness = int(fitnesses.min())
    if child_fitness < minimum_fitness:
        return
    minima = np.flatnonzero(fitnesses == minimum_fitness)
    replacement_index = int(minima[int(rng.integers(0, len(minima)))])
    population[replacement_index] = child
    fitnesses[replacement_index] = child_fitness


def run_serial(seed: int, setting: Setting) -> int:
    """Return the binary success outcome for one serial GA run."""
    rng = np.random.Generator(np.random.PCG64(seed))
    population, fitnesses, initial_success = initialize(rng, setting.population_size)
    if initial_success:
        return 1

    for _ in range(setting.population_size, setting.budget):
        parent = choose_parent(rng, population, fitnesses)
        child = np.uint32(parent ^ mutation_mask(rng, setting.mutation_probability))
        child_fitness = int(child).bit_count()
        if child == OPTIMUM:
            return 1
        replace_if_eligible(rng, population, fitnesses, child, child_fitness)
    return 0


def run_batch16(seed: int, setting: Setting) -> int:
    """Return the binary success outcome for one frozen-parent batch GA run."""
    rng = np.random.Generator(np.random.PCG64(seed))
    population, fitnesses, initial_success = initialize(rng, setting.population_size)
    if initial_success:
        return 1

    evaluations = setting.population_size
    while evaluations < setting.budget:
        frozen_population = population.copy()
        frozen_fitnesses = fitnesses.copy()
        batch_count = min(BATCH_SIZE, setting.budget - evaluations)
        children: list[tuple[np.uint32, int]] = []

        for _ in range(batch_count):
            parent = choose_parent(rng, frozen_population, frozen_fitnesses)
            child = np.uint32(parent ^ mutation_mask(rng, setting.mutation_probability))
            child_fitness = int(child).bit_count()
            evaluations += 1
            if child == OPTIMUM:
                return 1
            children.append((child, child_fitness))

        for child, child_fitness in children:
            replace_if_eligible(rng, population, fitnesses, child, child_fitness)

    assert evaluations == setting.budget
    return 0


def validate_seed_schedule() -> None:
    calibration_seeds: set[int] = set()
    validation_seeds: set[int] = set()
    for split in range(N_SPLITS):
        base = BASE_SEED_START + BASE_SEED_STRIDE * split
        calibration_seeds.update(base + j for j in range(N_CALIBRATION))
        validation_seeds.update(
            base + VALIDATION_SEED_OFFSET + j for j in range(N_VALIDATION)
        )
    assert len(calibration_seeds) == N_SPLITS * N_CALIBRATION
    assert len(validation_seeds) == N_SPLITS * N_VALIDATION
    assert calibration_seeds.isdisjoint(validation_seeds)


def calibrate() -> tuple[pd.DataFrame, pd.DataFrame]:
    candidate_rows: list[dict[str, int | float]] = []
    selected_rows: list[dict[str, int | float]] = []
    settings = all_settings()
    assert len(settings) == 18

    for split in range(N_SPLITS):
        base = BASE_SEED_START + BASE_SEED_STRIDE * split
        split_rows: list[dict[str, int | float]] = []
        for setting in settings:
            successes = sum(
                run_serial(base + j, setting) for j in range(N_CALIBRATION)
            )
            success_rate = successes / N_CALIBRATION
            row: dict[str, int | float] = {
                "split": split,
                "P": setting.population_size,
                "mutation_multiplier": setting.mutation_multiplier,
                "p": setting.mutation_probability,
                "B": setting.budget,
                "calibration_successes": successes,
                "calibration_success_rate": success_rate,
                "target_deviation": abs(success_rate - TARGET_RATE),
            }
            candidate_rows.append(row)
            split_rows.append(row)

        chosen = min(
            split_rows,
            key=lambda row: (
                float(row["target_deviation"]),
                int(row["B"]),
                int(row["P"]),
                MUTATION_TIE_RANK[float(row["mutation_multiplier"])],
            ),
        )
        selected_rows.append(dict(chosen))

        if (split + 1) % 10 == 0:
            print(f"Calibration: completed {split + 1}/{N_SPLITS} splits", flush=True)

    candidates = pd.DataFrame(candidate_rows)
    selected = pd.DataFrame(selected_rows)
    assert len(candidates) == N_SPLITS * 18
    assert len(selected) == N_SPLITS
    return candidates, selected


def validate(
    selected: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    result_rows: list[dict[str, int | float]] = []
    paired_rows: list[dict[str, int]] = []

    for selected_row in selected.itertuples(index=False):
        split = int(selected_row.split)
        setting = Setting(
            int(selected_row.P),
            float(selected_row.mutation_multiplier),
            int(selected_row.B),
        )
        base = BASE_SEED_START + BASE_SEED_STRIDE * split
        serial_outcomes = np.empty(N_VALIDATION, dtype=np.int8)
        batch_outcomes = np.empty(N_VALIDATION, dtype=np.int8)

        for j in range(N_VALIDATION):
            seed = base + VALIDATION_SEED_OFFSET + j
            serial_outcomes[j] = run_serial(seed, setting)
            batch_outcomes[j] = run_batch16(seed, setting)
            paired_rows.append(
                {
                    "split": split,
                    "validation_seed": seed,
                    "serial_success": int(serial_outcomes[j]),
                    "batch_success": int(batch_outcomes[j]),
                    "batch_minus_serial": int(batch_outcomes[j] - serial_outcomes[j]),
                }
            )

        calibration_rate = float(selected_row.calibration_success_rate)
        serial_rate = float(serial_outcomes.mean())
        batch_rate = float(batch_outcomes.mean())
        a_value = abs(calibration_rate - TARGET_RATE)
        b_value = abs(serial_rate - TARGET_RATE)
        result_rows.append(
            {
                "split": split,
                "selected_P": setting.population_size,
                "selected_mutation_multiplier": setting.mutation_multiplier,
                "selected_p": setting.mutation_probability,
                "selected_B": setting.budget,
                "calibration_success_rate": calibration_rate,
                "validation_serial_success_rate": serial_rate,
                "validation_batch_success_rate": batch_rate,
                "calibration_target_deviation": a_value,
                "validation_target_deviation": b_value,
                "delta": b_value - a_value,
                "batch_minus_serial": float(
                    np.mean(batch_outcomes.astype(float) - serial_outcomes)
                ),
            }
        )

        if (split + 1) % 10 == 0:
            print(f"Validation: completed {split + 1}/{N_SPLITS} splits", flush=True)

    results = pd.DataFrame(result_rows, columns=RESULT_COLUMNS)
    paired = pd.DataFrame(paired_rows)
    assert len(results) == N_SPLITS
    assert len(paired) == N_SPLITS * N_VALIDATION
    return results, paired


def bootstrap(
    results: pd.DataFrame,
) -> tuple[float, tuple[float, float], float, tuple[float, float]]:
    deltas = results["delta"].to_numpy(dtype=float)
    q_values = results["batch_minus_serial"].to_numpy(dtype=float)
    rng = np.random.Generator(np.random.PCG64(BOOTSTRAP_SEED))
    indices = rng.integers(0, N_SPLITS, size=(N_BOOTSTRAP, N_SPLITS))
    d_replicates = np.median(deltas[indices], axis=1)
    q_replicates = np.mean(q_values[indices], axis=1)
    d_ci = tuple(
        float(value)
        for value in np.quantile(
            d_replicates, [0.025, 0.975], method="linear"
        )
    )
    q_ci = tuple(
        float(value)
        for value in np.quantile(
            q_replicates, [0.025, 0.975], method="linear"
        )
    )
    return float(np.median(deltas)), d_ci, float(np.mean(q_values)), q_ci


def decide_primary(regime_count: int, d_ci: tuple[float, float]) -> str:
    if regime_count < 96:
        return "regime-check failure/inconclusive"
    if d_ci[0] >= OPTIMISM_THRESHOLD:
        return "supported"
    if d_ci[1] < OPTIMISM_THRESHOLD:
        return "refuted"
    return "inconclusive"


def decide_batch(q_ci: tuple[float, float]) -> str:
    if q_ci[0] > 0.0:
        return "batch-size-16 superior"
    if q_ci[1] < 0.0:
        return "serial superior"
    return "no decisive difference"


def summarize(
    results: pd.DataFrame,
    paired: pd.DataFrame,
    runtime_seconds: float,
) -> dict[str, Any]:
    d_value, d_ci, q_value, q_ci = bootstrap(results)
    deltas = results["delta"].to_numpy(dtype=float)
    regime_count = int(
        results["calibration_success_rate"].between(0.25, 0.75, inclusive="both").sum()
    )
    only_serial = int(
        ((paired["serial_success"] == 1) & (paired["batch_success"] == 0)).sum()
    )
    only_batch = int(
        ((paired["serial_success"] == 0) & (paired["batch_success"] == 1)).sum()
    )
    serial_successes = int(paired["serial_success"].sum())
    batch_successes = int(paired["batch_success"].sum())

    return {
        "experiment": "preregistered OneMax calibration optimism and batch-size-16 comparison",
        "primary_effect_D": d_value,
        "primary_D_ci_95": list(d_ci),
        "primary_threshold": OPTIMISM_THRESHOLD,
        "primary_decision": decide_primary(regime_count, d_ci),
        "median_calibration_target_deviation": float(
            results["calibration_target_deviation"].median()
        ),
        "median_validation_target_deviation": float(
            results["validation_target_deviation"].median()
        ),
        "delta_positive_splits": int(np.sum(deltas > 0.0)),
        "delta_zero_splits": int(np.sum(deltas == 0.0)),
        "delta_negative_splits": int(np.sum(deltas < 0.0)),
        "regime_check_count": regime_count,
        "regime_check_required": 96,
        "regime_check_passed": regime_count >= 96,
        "serial_validation_successes": serial_successes,
        "serial_validation_trials": len(paired),
        "serial_validation_success_rate": serial_successes / len(paired),
        "batch_validation_successes": batch_successes,
        "batch_validation_trials": len(paired),
        "batch_validation_success_rate": batch_successes / len(paired),
        "batch_effect_Q": q_value,
        "batch_Q_ci_95": list(q_ci),
        "batch_decision": decide_batch(q_ci),
        "only_serial_succeeds": only_serial,
        "only_batch_succeeds": only_batch,
        "paired_concordant_count": len(paired) - only_serial - only_batch,
        "split_count": N_SPLITS,
        "calibration_seeds_per_split": N_CALIBRATION,
        "validation_seeds_per_split": N_VALIDATION,
        "candidate_settings": 18,
        "calibration_run_count": N_SPLITS * N_CALIBRATION * 18,
        "validation_serial_run_count": N_SPLITS * N_VALIDATION,
        "validation_batch_run_count": N_SPLITS * N_VALIDATION,
        "bootstrap_resamples": N_BOOTSTRAP,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "base_seed_start": BASE_SEED_START,
        "base_seed_stride": BASE_SEED_STRIDE,
        "validation_seed_offset": VALIDATION_SEED_OFFSET,
        "package_versions": versions(),
        "runtime_seconds": runtime_seconds,
    }


def flat_results(summary: dict[str, Any]) -> dict[str, int | float | str | bool]:
    return {
        "primary_D": float(summary["primary_effect_D"]),
        "primary_ci_low": float(summary["primary_D_ci_95"][0]),
        "primary_ci_high": float(summary["primary_D_ci_95"][1]),
        "primary_threshold": float(summary["primary_threshold"]),
        "primary_decision": str(summary["primary_decision"]),
        "regime_check_count": int(summary["regime_check_count"]),
        "regime_check_required": int(summary["regime_check_required"]),
        "regime_check_passed": bool(summary["regime_check_passed"]),
        "median_calibration_target_deviation": float(
            summary["median_calibration_target_deviation"]
        ),
        "median_validation_target_deviation": float(
            summary["median_validation_target_deviation"]
        ),
        "delta_positive_splits": int(summary["delta_positive_splits"]),
        "delta_zero_splits": int(summary["delta_zero_splits"]),
        "delta_negative_splits": int(summary["delta_negative_splits"]),
        "serial_validation_success_rate": float(
            summary["serial_validation_success_rate"]
        ),
        "batch_validation_success_rate": float(
            summary["batch_validation_success_rate"]
        ),
        "batch_Q": float(summary["batch_effect_Q"]),
        "batch_ci_low": float(summary["batch_Q_ci_95"][0]),
        "batch_ci_high": float(summary["batch_Q_ci_95"][1]),
        "batch_decision": str(summary["batch_decision"]),
        "only_serial_succeeds": int(summary["only_serial_succeeds"]),
        "only_batch_succeeds": int(summary["only_batch_succeeds"]),
        "n_splits": int(summary["split_count"]),
        "n_calibration_runs": int(summary["calibration_run_count"]),
        "n_validation_serial_runs": int(summary["validation_serial_run_count"]),
        "n_validation_batch_runs": int(summary["validation_batch_run_count"]),
        "n_bootstrap_resamples": int(summary["bootstrap_resamples"]),
        "bootstrap_seed": int(summary["bootstrap_seed"]),
        "runtime_seconds": float(summary["runtime_seconds"]),
        "python_version": str(summary["package_versions"]["python"]),
        "numpy_version": str(summary["package_versions"]["numpy"]),
        "pandas_version": str(summary["package_versions"]["pandas"]),
        "matplotlib_version": str(summary["package_versions"]["matplotlib"]),
    }


def create_figure(results: pd.DataFrame, summary: dict[str, Any]) -> None:
    a_values = results["calibration_target_deviation"].to_numpy(dtype=float)
    b_values = results["validation_target_deviation"].to_numpy(dtype=float)
    deltas = np.sort(results["delta"].to_numpy(dtype=float))
    median_a = float(np.median(a_values))
    median_b = float(np.median(b_values))

    fig, (left, right) = plt.subplots(1, 2, figsize=(16, 7), dpi=100)

    left.scatter(a_values, b_values, s=42, alpha=0.78, color="#2B6CB0")
    upper = max(float(a_values.max()), float(b_values.max()), 0.5)
    left.plot([0.0, upper], [0.0, upper], "--", color="0.35", label="y = x")
    left.axvline(median_a, color="#2B6CB0", linewidth=2, label=f"median a = {median_a:.3f}")
    left.axhline(median_b, color="#C05621", linewidth=2, label=f"median b = {median_b:.3f}")
    left.set_xlim(-0.01, upper + 0.01)
    left.set_ylim(-0.01, upper + 0.01)
    left.set_xlabel("Calibration target deviation $a_i$")
    left.set_ylabel("Held-out target deviation $b_i$")
    left.set_title("Calibration vs. held-out deviation")
    left.legend(frameon=False, loc="lower right")

    right.plot(np.arange(1, N_SPLITS + 1), deltas, color="#2B6CB0", linewidth=2)
    right.axhline(0.0, color="0.25", linewidth=1.5)
    right.axhline(
        OPTIMISM_THRESHOLD,
        color="#C53030",
        linewidth=1.5,
        label="preregistered threshold = 0.08",
    )
    right.set_xlabel("Split rank (sorted by delta)")
    right.set_ylabel("$\u03b4_i = b_i - a_i$")
    right.set_title("Sorted split-level calibration optimism")
    right.legend(frameon=False, loc="lower right")
    right.text(
        0.03,
        0.97,
        (
            f"D = {summary['primary_effect_D']:.4f}\n"
            f"95% CI [{summary['primary_D_ci_95'][0]:.4f}, "
            f"{summary['primary_D_ci_95'][1]:.4f}]"
        ),
        transform=right.transAxes,
        ha="left",
        va="top",
        bbox={"facecolor": "white", "edgecolor": "0.75", "alpha": 0.9},
    )

    fig.tight_layout()
    root_path = ROOT / "calibration_optimism.png"
    figure_path = ROOT / "figures" / "calibration_optimism.png"
    fig.savefig(root_path, dpi=100)
    shutil.copyfile(root_path, figure_path)
    plt.close(fig)


def main() -> None:
    if tuple(map(int, platform.python_version_tuple()[:2])) < (3, 11):
        raise RuntimeError("Python 3.11 or later is required")

    start = time.perf_counter()
    (ROOT / "figures").mkdir(exist_ok=True)
    validate_seed_schedule()

    # This is the protocol lock. No experimental outcomes have been computed.
    write_json(ROOT / "preregistration.json", preregistration())

    candidates, selected = calibrate()
    candidates.to_csv(ROOT / "calibration_results.csv", index=False)
    selected.to_csv(ROOT / "selected_settings_prevalidation.csv", index=False)

    # Validation and the batch comparison begin only after selection is fixed on disk.
    results, paired = validate(selected)
    results.to_csv(ROOT / "results.csv", index=False)
    paired.to_csv(ROOT / "paired_validation_outcomes.csv", index=False)

    summary = summarize(results, paired, 0.0)
    create_figure(results, summary)
    summary["runtime_seconds"] = time.perf_counter() - start
    write_json(ROOT / "run_summary.json", summary)
    write_json(ROOT / "results.json", flat_results(summary))

    print(
        f"Ran {summary['calibration_run_count']} fixed calibration runs and "
        f"{summary['validation_serial_run_count']} paired held-out serial/batch-16 runs "
        f"across {N_SPLITS} splits."
    )
    print(
        f"D={summary['primary_effect_D']:.6f}, 95% CI "
        f"[{summary['primary_D_ci_95'][0]:.6f}, {summary['primary_D_ci_95'][1]:.6f}], "
        f"regime={summary['regime_check_count']}/120: {summary['primary_decision']}."
    )
    print(
        f"Q={summary['batch_effect_Q']:.6f}, 95% CI "
        f"[{summary['batch_Q_ci_95'][0]:.6f}, {summary['batch_Q_ci_95'][1]:.6f}]: "
        f"{summary['batch_decision']}. Runtime {summary['runtime_seconds']:.1f}s."
    )


if __name__ == "__main__":
    main()
