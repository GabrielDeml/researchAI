#!/usr/bin/env python3
"""Run the deterministic GA order-reversal experiment and write its artifacts."""

from __future__ import annotations

import os

# Keep numerical libraries single-threaded before importing NumPy/Matplotlib.
for _variable in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ[_variable] = "1"
_workspace_cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".runtime_cache")
os.environ["MPLCONFIGDIR"] = os.path.join(_workspace_cache, "matplotlib")
os.environ["XDG_CACHE_HOME"] = os.path.join(_workspace_cache, "xdg")

import csv
import hashlib
import json
import sys
import warnings
from pathlib import Path
from typing import Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np


MASTER_SEED = 20250308
MASK64 = (1 << 64) - 1
POPULATION_SIZE = 64
INITIALIZATION_TARGET = 64
INITIALIZATION_ATTEMPT_CAP = 10_000
OFFSPRING_TARGET = 2_048
OFFSPRING_ATTEMPT_CAP = 100_000
SEEDS = tuple(range(30))

ALGORITHM_IDS = {"generational": 0, "steady_state": 1}
FORWARD_ORDER = ("generational", "steady_state")
REVERSE_ORDER = ("steady_state", "generational")

METRIC_FIELDS = (
    "initialization_target",
    "initialization_accepted",
    "initialization_attempts",
    "initialization_misses",
    "initialization_failed",
    "offspring_target",
    "offspring_accepted",
    "offspring_attempts",
    "offspring_misses",
    "offspring_failed",
    "best_score",
    "duplicate_ratio",
)

AUDIT_COLUMNS = (
    "generational_initialization_attempts",
    "steady_state_initialization_attempts",
    "generational_offspring_attempts",
    "steady_state_offspring_attempts",
    "generational_duplicate_ratio",
    "steady_state_duplicate_ratio",
    "generational_best_score",
    "steady_state_best_score",
)

HEADER = (
    "seed",
    *(f"generational_{field}" for field in METRIC_FIELDS),
    *(f"steady_state_{field}" for field in METRIC_FIELDS),
)

RunMetrics = dict[str, int | float]
Row = dict[str, int | str]


def fitness(genome: int) -> int:
    """Return the 64-bit OneMax fitness."""
    return int(genome).bit_count()


def random_genome(rng: np.random.Generator) -> int:
    return int(rng.bit_generator.random_raw()) & MASK64


def initialize_population(
    rng: np.random.Generator,
) -> tuple[list[int], int, int]:
    population: list[int] = []
    accepted: set[int] = set()
    attempts = 0
    misses = 0

    while len(population) < INITIALIZATION_TARGET and attempts < INITIALIZATION_ATTEMPT_CAP:
        genome = random_genome(rng)
        attempts += 1
        if genome in accepted:
            misses += 1
            continue
        population.append(genome)
        accepted.add(genome)

    return population, attempts, misses


def tournament(population: list[int], rng: np.random.Generator) -> int:
    first_index = int(rng.integers(0, len(population)))
    second_index = int(rng.integers(0, len(population)))
    first = population[first_index]
    second = population[second_index]
    return first if fitness(first) >= fitness(second) else second


def make_child(population: list[int], rng: np.random.Generator) -> int:
    parent1 = tournament(population, rng)
    parent2 = tournament(population, rng)
    crossover_mask = int(rng.bit_generator.random_raw()) & MASK64
    child = (parent1 & crossover_mask) | (parent2 & ((~crossover_mask) & MASK64))

    mutation_count = int(rng.binomial(64, 1 / 64))
    if mutation_count > 0:
        bit_positions = rng.choice(64, size=mutation_count, replace=False)
        for position in bit_positions:
            child ^= 1 << int(position)

    return child & MASK64


def base_metrics(
    population: list[int], initialization_attempts: int, initialization_misses: int
) -> RunMetrics:
    initialization_accepted = len(population)
    return {
        "initialization_target": INITIALIZATION_TARGET,
        "initialization_accepted": initialization_accepted,
        "initialization_attempts": initialization_attempts,
        "initialization_misses": initialization_misses,
        "initialization_failed": int(initialization_accepted < INITIALIZATION_TARGET),
        "offspring_target": OFFSPRING_TARGET,
        "offspring_accepted": 0,
        "offspring_attempts": 0,
        "offspring_misses": 0,
        "offspring_failed": 1,
        "best_score": max((fitness(genome) for genome in population), default=0),
        "duplicate_ratio": 0.0,
    }


def finalize_metrics(metrics: RunMetrics) -> RunMetrics:
    denominator = int(metrics["initialization_attempts"]) + int(metrics["offspring_attempts"])
    misses = int(metrics["initialization_misses"]) + int(metrics["offspring_misses"])
    metrics["duplicate_ratio"] = misses / denominator if denominator else 0.0
    return metrics


def run_generational(rng: np.random.Generator) -> RunMetrics:
    population, initialization_attempts, initialization_misses = initialize_population(rng)
    metrics = base_metrics(population, initialization_attempts, initialization_misses)
    if metrics["initialization_failed"]:
        return finalize_metrics(metrics)

    best_score = int(metrics["best_score"])
    offspring_attempts = 0
    offspring_misses = 0
    offspring_accepted = 0

    while offspring_accepted < OFFSPRING_TARGET and offspring_attempts < OFFSPRING_ATTEMPT_CAP:
        current_population = set(population)
        next_generation: list[int] = []
        accepted_children: set[int] = set()

        while (
            len(next_generation) < POPULATION_SIZE
            and offspring_accepted < OFFSPRING_TARGET
            and offspring_attempts < OFFSPRING_ATTEMPT_CAP
        ):
            child = make_child(population, rng)
            offspring_attempts += 1
            if child in current_population or child in accepted_children:
                offspring_misses += 1
                continue

            next_generation.append(child)
            accepted_children.add(child)
            offspring_accepted += 1
            best_score = max(best_score, fitness(child))

        if len(next_generation) == POPULATION_SIZE:
            population = next_generation

    metrics.update(
        {
            "offspring_accepted": offspring_accepted,
            "offspring_attempts": offspring_attempts,
            "offspring_misses": offspring_misses,
            "offspring_failed": int(offspring_accepted < OFFSPRING_TARGET),
            "best_score": best_score,
        }
    )
    return finalize_metrics(metrics)


def run_steady_state(rng: np.random.Generator) -> RunMetrics:
    population, initialization_attempts, initialization_misses = initialize_population(rng)
    metrics = base_metrics(population, initialization_attempts, initialization_misses)
    if metrics["initialization_failed"]:
        return finalize_metrics(metrics)

    best_score = int(metrics["best_score"])
    offspring_attempts = 0
    offspring_misses = 0
    offspring_accepted = 0

    while offspring_accepted < OFFSPRING_TARGET and offspring_attempts < OFFSPRING_ATTEMPT_CAP:
        child = make_child(population, rng)
        offspring_attempts += 1
        if child in population:
            offspring_misses += 1
            continue

        population.append(child)
        offspring_accepted += 1
        best_score = max(best_score, fitness(child))

        minimum_fitness = min(fitness(genome) for genome in population)
        minimum_indices = [
            index for index, genome in enumerate(population) if fitness(genome) == minimum_fitness
        ]
        removal_rank = int(rng.integers(0, len(minimum_indices)))
        del population[minimum_indices[removal_rank]]

    metrics.update(
        {
            "offspring_accepted": offspring_accepted,
            "offspring_attempts": offspring_attempts,
            "offspring_misses": offspring_misses,
            "offspring_failed": int(offspring_accepted < OFFSPRING_TARGET),
            "best_score": best_score,
        }
    )
    return finalize_metrics(metrics)


ALGORITHMS: dict[str, Callable[[np.random.Generator], RunMetrics]] = {
    "generational": run_generational,
    "steady_state": run_steady_state,
}


def make_rng(entropy: list[int]) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(entropy)))


def run_condition(mode: str, order: tuple[str, str]) -> list[Row]:
    rows: list[Row] = []
    for seed in SEEDS:
        algorithm_metrics: dict[str, RunMetrics] = {}
        shared_rng = make_rng([MASTER_SEED, seed]) if mode == "shared" else None

        for algorithm in order:
            if mode == "independent":
                rng = make_rng([MASTER_SEED, seed, ALGORITHM_IDS[algorithm]])
            elif mode == "shared":
                assert shared_rng is not None
                rng = shared_rng
            else:
                raise ValueError(f"unknown RNG allocation mode: {mode}")
            algorithm_metrics[algorithm] = ALGORITHMS[algorithm](rng)

        row: Row = {"seed": seed}
        for algorithm in ("generational", "steady_state"):
            for field in METRIC_FIELDS:
                value = algorithm_metrics[algorithm][field]
                row[f"{algorithm}_{field}"] = (
                    format(float(value), ".12f") if field == "duplicate_ratio" else int(value)
                )
        rows.append(row)

    return sorted(rows, key=lambda row: int(row["seed"]))


def write_csv(path: Path, rows: list[Row]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_serialized_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def compare_conditions(
    forward_path: Path, reverse_path: Path
) -> tuple[dict[str, dict[str, int | float]], int, np.ndarray]:
    forward_rows = read_serialized_rows(forward_path)
    reverse_rows = read_serialized_rows(reverse_path)
    if len(forward_rows) != len(SEEDS) or len(reverse_rows) != len(SEEDS):
        raise RuntimeError("comparison inputs must each contain exactly 30 data rows")
    if [row["seed"] for row in forward_rows] != [row["seed"] for row in reverse_rows]:
        raise RuntimeError("forward and reverse CSV seed ordering differs")

    difference_matrix = np.zeros((len(SEEDS), len(AUDIT_COLUMNS)), dtype=np.uint8)
    column_changes: dict[str, dict[str, int | float]] = {}
    for column_index, column in enumerate(AUDIT_COLUMNS):
        for row_index, (forward, reverse) in enumerate(zip(forward_rows, reverse_rows)):
            difference_matrix[row_index, column_index] = int(forward[column] != reverse[column])
        count = int(difference_matrix[:, column_index].sum())
        column_changes[column] = {"count": count, "rate": count / len(SEEDS)}

    union_count = int(np.any(difference_matrix, axis=1).sum())
    return column_changes, union_count, difference_matrix


def identical_data_line_count(forward_path: Path, reverse_path: Path) -> int:
    forward_lines = forward_path.read_bytes().splitlines()
    reverse_lines = reverse_path.read_bytes().splitlines()
    if not forward_lines or not reverse_lines or forward_lines[0] != reverse_lines[0]:
        raise RuntimeError("CSV headers are not identical")
    if len(forward_lines) != len(SEEDS) + 1 or len(reverse_lines) != len(SEEDS) + 1:
        raise RuntimeError("CSV files do not each contain one header and 30 data rows")
    return sum(left == right for left, right in zip(forward_lines[1:], reverse_lines[1:]))


def failure_counts(rows: list[Row]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for algorithm in ("generational", "steady_state"):
        for failure_field in ("initialization_failed", "offspring_failed"):
            column = f"{algorithm}_{failure_field}"
            counts[column] = sum(int(row[column]) for row in rows)
    return counts


def make_heatmap(
    independent_matrix: np.ndarray, shared_matrix: np.ndarray, output_path: Path
) -> None:
    color_map = LinearSegmentedColormap.from_list(
        "white_to_dark_red", ("#ffffff", "#7f0000")
    )
    figure = plt.figure(figsize=(18, 14))
    grid = figure.add_gridspec(
        2,
        2,
        width_ratios=(32, 1),
        height_ratios=(1, 1),
        wspace=0.06,
        hspace=0.08,
    )
    axes = (
        figure.add_subplot(grid[0, 0]),
        figure.add_subplot(grid[1, 0]),
    )
    axes[1].sharex(axes[0])
    colorbar_axis = figure.add_subplot(grid[:, 1])

    last_image = None
    for axis, matrix, title in zip(
        axes,
        (independent_matrix, shared_matrix),
        ("Independent RNG streams", "Shared mutable RNG stream"),
    ):
        last_image = axis.imshow(
            matrix,
            cmap=color_map,
            vmin=0,
            vmax=1,
            aspect="auto",
            interpolation="nearest",
        )
        axis.set_title(title)
        axis.set_ylabel("seed")
        axis.set_yticks(range(len(SEEDS)), labels=[str(seed) for seed in SEEDS])
        axis.set_xticks(range(len(AUDIT_COLUMNS)), labels=AUDIT_COLUMNS)
        axis.tick_params(axis="x", labelrotation=35)

    axes[0].tick_params(axis="x", labelbottom=False)

    axes[-1].set_xlabel("audit column")
    assert last_image is not None
    colorbar = figure.colorbar(last_image, cax=colorbar_axis, ticks=(0, 1))
    colorbar.set_label("order-induced change")
    # The explicit call is part of the experiment protocol. Matplotlib warns for
    # figures with a dedicated colorbar GridSpec even though the subsequent
    # margins make every label fit, so suppress only that known layout warning.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="This figure includes Axes that are not compatible with tight_layout",
            category=UserWarning,
        )
        figure.tight_layout()
    figure.subplots_adjust(
        left=0.08,
        right=0.94,
        bottom=0.22,
        top=0.96,
        hspace=0.12,
        wspace=0.06,
    )
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def validate_runtime() -> None:
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError(f"Python 3.11 required, found {sys.version.split()[0]}")
    if np.__version__ != "1.26.4":
        raise RuntimeError(f"numpy 1.26.4 required, found {np.__version__}")
    if matplotlib.__version__ != "3.8.4":
        raise RuntimeError(f"matplotlib 3.8.4 required, found {matplotlib.__version__}")


def main() -> None:
    validate_runtime()
    workspace = Path(__file__).resolve().parent
    figures_directory = workspace / "figures"
    figures_directory.mkdir(exist_ok=True)

    conditions = {
        "independent_forward": ("independent", FORWARD_ORDER),
        "independent_reverse": ("independent", REVERSE_ORDER),
        "shared_forward": ("shared", FORWARD_ORDER),
        "shared_reverse": ("shared", REVERSE_ORDER),
    }
    rows_by_condition: dict[str, list[Row]] = {}
    paths: dict[str, Path] = {}
    for name, (mode, order) in conditions.items():
        rows = run_condition(mode, order)
        path = workspace / f"{name}.csv"
        write_csv(path, rows)
        rows_by_condition[name] = rows
        paths[name] = path

    independent_hashes = {
        "forward_sha256": sha256(paths["independent_forward"]),
        "reverse_sha256": sha256(paths["independent_reverse"]),
    }
    shared_hashes = {
        "forward_sha256": sha256(paths["shared_forward"]),
        "reverse_sha256": sha256(paths["shared_reverse"]),
    }
    independent_hash_equal = (
        independent_hashes["forward_sha256"] == independent_hashes["reverse_sha256"]
    )
    shared_hash_equal = shared_hashes["forward_sha256"] == shared_hashes["reverse_sha256"]
    independent_identical_lines = identical_data_line_count(
        paths["independent_forward"], paths["independent_reverse"]
    )

    independent_changes, independent_union_count, independent_matrix = compare_conditions(
        paths["independent_forward"], paths["independent_reverse"]
    )
    shared_changes, shared_union_count, shared_matrix = compare_conditions(
        paths["shared_forward"], paths["shared_reverse"]
    )
    shared_max_column = max(
        AUDIT_COLUMNS, key=lambda column: int(shared_changes[column]["count"])
    )
    shared_max_count = int(shared_changes[shared_max_column]["count"])
    shared_max_rate = float(shared_changes[shared_max_column]["rate"])

    supported = (
        independent_identical_lines == len(SEEDS)
        and independent_hash_equal
        and shared_max_rate >= 0.80
    )

    failure_counts_by_condition = {
        condition: failure_counts(rows) for condition, rows in rows_by_condition.items()
    }
    audit_metrics = {
        "comparison_hashes": {
            "independent": {**independent_hashes, "equal": independent_hash_equal},
            "shared": {**shared_hashes, "equal": shared_hash_equal},
        },
        "independent_identical_line_count": independent_identical_lines,
        "independent_total_line_count": len(SEEDS),
        "column_changes": {
            "independent": independent_changes,
            "shared": shared_changes,
        },
        "union_changes": {
            "independent": {
                "count": independent_union_count,
                "rate": independent_union_count / len(SEEDS),
            },
            "shared": {
                "count": shared_union_count,
                "rate": shared_union_count / len(SEEDS),
            },
        },
        "shared_max_column": shared_max_column,
        "shared_max_column_change_count": shared_max_count,
        "shared_max_column_change_rate": shared_max_rate,
        "failure_counts": failure_counts_by_condition,
        "supported": supported,
        "decision": "supported" if supported else "refuted",
    }
    (workspace / "audit_metrics.json").write_text(
        json.dumps(audit_metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    make_heatmap(
        independent_matrix,
        shared_matrix,
        figures_directory / "order_reversal_heatmap.png",
    )

    results: dict[str, bool | float | int | str] = {
        "python_version": sys.version.split()[0],
        "numpy_version": np.__version__,
        "matplotlib_version": matplotlib.__version__,
        "master_seed": MASTER_SEED,
        "seed_count": len(SEEDS),
        "independent_forward_sha256": independent_hashes["forward_sha256"],
        "independent_reverse_sha256": independent_hashes["reverse_sha256"],
        "independent_whole_file_equal": independent_hash_equal,
        "independent_identical_line_count": independent_identical_lines,
        "independent_total_line_count": len(SEEDS),
        "shared_forward_sha256": shared_hashes["forward_sha256"],
        "shared_reverse_sha256": shared_hashes["reverse_sha256"],
        "shared_whole_file_equal": shared_hash_equal,
        "independent_union_change_count": independent_union_count,
        "independent_union_change_rate": independent_union_count / len(SEEDS),
        "shared_union_change_count": shared_union_count,
        "shared_union_change_rate": shared_union_count / len(SEEDS),
        "shared_max_column": shared_max_column,
        "shared_max_column_change_count": shared_max_count,
        "shared_max_column_change_rate": shared_max_rate,
        "hypothesis_supported": supported,
        "decision": "supported" if supported else "refuted",
    }
    for mode, changes in (("independent", independent_changes), ("shared", shared_changes)):
        for column, values in changes.items():
            results[f"{mode}_{column}_change_count"] = int(values["count"])
            results[f"{mode}_{column}_change_rate"] = float(values["rate"])
    for condition, counts in failure_counts_by_condition.items():
        for column, count in counts.items():
            results[f"{condition}_{column}_count"] = count

    if not all(isinstance(value, (bool, float, int, str)) for value in results.values()):
        raise RuntimeError("results.json must be a flat object containing only scalar values")
    (workspace / "results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    total_failures = sum(sum(counts.values()) for counts in failure_counts_by_condition.values())
    print("Ran generational and steady-state 64-bit OneMax for seeds 0-29 in four mode/order conditions.")
    print(
        "Independent: "
        f"{independent_identical_lines}/{len(SEEDS)} identical rows; "
        f"whole-file hash equality={str(independent_hash_equal).lower()}."
    )
    print(
        "Shared: maximum single-column change "
        f"{shared_max_count}/{len(SEEDS)} ({shared_max_rate:.3f}) in {shared_max_column}; "
        f"union={shared_union_count}/{len(SEEDS)} ({shared_union_count / len(SEEDS):.3f})."
    )
    print(f"Failure-indicator sum across all conditions={total_failures}.")
    print(f"Decision: {'SUPPORTED' if supported else 'REFUTED'}.")


if __name__ == "__main__":
    main()
