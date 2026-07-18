#!/usr/bin/env python3
"""Paired serial-vs-batched steady-state GA experiment on trap-5."""

from __future__ import annotations

import os

# These must be set before NumPy is imported so its numerical backends stay
# single-threaded. Assignment (rather than setdefault) also overrides any
# inherited setting from the launching shell.
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["MPLCONFIGDIR"] = os.path.join(os.path.dirname(__file__), ".matplotlib-cache")
os.environ["XDG_CACHE_HOME"] = os.path.join(os.path.dirname(__file__), ".cache")

import csv
import gc
import json
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


POPULATION_SIZE = 100
GENOME_LENGTH = 100
BLOCK_SIZE = 5
N_BLOCKS = GENOME_LENGTH // BLOCK_SIZE
FULL_BUDGET = 50_000
WARMUP_BUDGET = 1_100
BATCH_SIZE = 16
SEEDS = tuple(range(30))
NO_HIT = FULL_BUDGET + 1


@dataclass(frozen=True)
class OperatorSchedule:
    tournaments: np.ndarray
    block_choices: np.ndarray
    mutations: np.ndarray

    def __len__(self) -> int:
        return int(self.tournaments.shape[0])


@dataclass(frozen=True)
class RunOutcome:
    success: bool
    first_hit: int
    final_best: int


def trap5_fitness(population: np.ndarray) -> np.ndarray:
    """Evaluate a two-dimensional uint8/bool population with one formula."""
    if population.ndim != 2 or population.shape[1] != GENOME_LENGTH:
        raise ValueError(f"expected shape (n, {GENOME_LENGTH}), got {population.shape}")
    unitation = population.reshape(-1, N_BLOCKS, BLOCK_SIZE).sum(
        axis=2, dtype=np.int16
    )
    block_scores = np.where(unitation == BLOCK_SIZE, BLOCK_SIZE, 4 - unitation)
    return block_scores.sum(axis=1, dtype=np.int16)


def make_inputs(seed: int, budget: int) -> tuple[np.ndarray, OperatorSchedule]:
    """Create paired initial conditions and the shared variation schedule."""
    if budget < POPULATION_SIZE:
        raise ValueError("budget must include at least the initial population")
    root = np.random.SeedSequence(seed)
    initial_sequence, variation_sequence = root.spawn(2)
    initial_rng = np.random.Generator(np.random.PCG64(initial_sequence))
    variation_rng = np.random.Generator(np.random.PCG64(variation_sequence))

    initial_population = initial_rng.integers(
        0,
        2,
        size=(POPULATION_SIZE, GENOME_LENGTH),
        dtype=np.uint8,
    )
    n_offspring = budget - POPULATION_SIZE
    schedule = OperatorSchedule(
        tournaments=variation_rng.integers(
            0,
            POPULATION_SIZE,
            size=(n_offspring, 4),
            dtype=np.int16,
        ),
        block_choices=variation_rng.random((n_offspring, N_BLOCKS)) < 0.5,
        mutations=variation_rng.random((n_offspring, GENOME_LENGTH)) < 0.01,
    )
    return initial_population, schedule


def environmental_select(
    population: np.ndarray,
    fitness: np.ndarray,
    offspring: np.ndarray,
    offspring_fitness: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Stable (mu + lambda) selection with incumbent-first tie breaking."""
    candidates = np.concatenate((population, offspring), axis=0)
    candidate_fitness = np.concatenate((fitness, offspring_fitness), axis=0)
    # Stable sorting preserves concatenated index on a tie. Incumbents occur
    # first, so an equal-fitness child cannot displace an incumbent.
    order = np.argsort(-candidate_fitness, kind="stable")[:POPULATION_SIZE]
    return candidates[order].copy(), candidate_fitness[order].copy()


def choose_parent_pair(tournament: np.ndarray, fitness: np.ndarray) -> tuple[int, int]:
    a, b, c, d = (int(value) for value in tournament)
    parent1 = a if fitness[a] >= fitness[b] else b
    parent2 = c if fitness[c] >= fitness[d] else d
    return parent1, parent2


def make_serial_child(
    population: np.ndarray,
    fitness: np.ndarray,
    tournament: np.ndarray,
    block_choices: np.ndarray,
    mutation: np.ndarray,
) -> np.ndarray:
    parent1, parent2 = choose_parent_pair(tournament, fitness)
    p1_blocks = population[parent1].reshape(N_BLOCKS, BLOCK_SIZE)
    p2_blocks = population[parent2].reshape(N_BLOCKS, BLOCK_SIZE)
    child = np.where(block_choices[:, None], p1_blocks, p2_blocks).reshape(
        GENOME_LENGTH
    )
    return np.bitwise_xor(child, mutation).astype(np.uint8, copy=False)


def make_batched_children(
    snapshot: np.ndarray,
    snapshot_fitness: np.ndarray,
    tournaments: np.ndarray,
    block_choices: np.ndarray,
    mutations: np.ndarray,
) -> np.ndarray:
    """Vectorize parent choice, block crossover, and mutation across a batch."""
    first = np.where(
        snapshot_fitness[tournaments[:, 0]] >= snapshot_fitness[tournaments[:, 1]],
        tournaments[:, 0],
        tournaments[:, 1],
    )
    second = np.where(
        snapshot_fitness[tournaments[:, 2]] >= snapshot_fitness[tournaments[:, 3]],
        tournaments[:, 2],
        tournaments[:, 3],
    )
    p1_blocks = snapshot[first].reshape(-1, N_BLOCKS, BLOCK_SIZE)
    p2_blocks = snapshot[second].reshape(-1, N_BLOCKS, BLOCK_SIZE)
    children = np.where(block_choices[:, :, None], p1_blocks, p2_blocks).reshape(
        -1, GENOME_LENGTH
    )
    return np.bitwise_xor(children, mutations).astype(np.uint8, copy=False)


def initial_hit(fitness: np.ndarray, no_hit: int) -> int:
    hits = np.flatnonzero(fitness == 100)
    return int(hits[0] + 1) if hits.size else no_hit


def run_serial(
    initial_population: np.ndarray,
    schedule: OperatorSchedule,
    budget: int,
) -> RunOutcome:
    """Run one-child-at-a-time steady-state replacement."""
    no_hit = budget + 1
    population = initial_population.copy()
    fitness = trap5_fitness(population)
    first_hit = initial_hit(fitness, no_hit)

    for index in range(len(schedule)):
        child = make_serial_child(
            population,
            fitness,
            schedule.tournaments[index],
            schedule.block_choices[index],
            schedule.mutations[index],
        )
        child_batch = child.reshape(1, GENOME_LENGTH)
        child_fitness = trap5_fitness(child_batch)
        if first_hit == no_hit and child_fitness[0] == 100:
            first_hit = POPULATION_SIZE + index + 1
        population, fitness = environmental_select(
            population, fitness, child_batch, child_fitness
        )

    return RunOutcome(first_hit != no_hit, first_hit, int(fitness[0]))


def run_batch16(
    initial_population: np.ndarray,
    schedule: OperatorSchedule,
    budget: int,
) -> RunOutcome:
    """Run snapshot-based batches of 16, including the final partial batch."""
    no_hit = budget + 1
    population = initial_population.copy()
    fitness = trap5_fitness(population)
    first_hit = initial_hit(fitness, no_hit)

    for start in range(0, len(schedule), BATCH_SIZE):
        stop = min(start + BATCH_SIZE, len(schedule))
        snapshot = population.copy()
        snapshot_fitness = fitness.copy()
        children = make_batched_children(
            snapshot,
            snapshot_fitness,
            schedule.tournaments[start:stop],
            schedule.block_choices[start:stop],
            schedule.mutations[start:stop],
        )
        child_fitness = trap5_fitness(children)
        if first_hit == no_hit:
            hits = np.flatnonzero(child_fitness == 100)
            if hits.size:
                first_hit = POPULATION_SIZE + start + int(hits[0]) + 1
        population, fitness = environmental_select(
            population, fitness, children, child_fitness
        )

    return RunOutcome(first_hit != no_hit, first_hit, int(fitness[0]))


METHODS = {"serial": run_serial, "batch16": run_batch16}


def timed_run(
    method_name: str,
    initial_population: np.ndarray,
    schedule: OperatorSchedule,
    budget: int,
) -> tuple[RunOutcome, float]:
    """Collect immediately before and disable GC only within the timer."""
    gc.collect()
    gc.disable()
    try:
        start = time.perf_counter_ns()
        outcome = METHODS[method_name](initial_population, schedule, budget)
        elapsed_ns = time.perf_counter_ns() - start
    finally:
        gc.enable()
    return outcome, elapsed_ns / 1_000_000_000.0


def assert_protocol_invariants() -> None:
    zeros = np.zeros((1, GENOME_LENGTH), dtype=np.uint8)
    ones = np.ones((1, GENOME_LENGTH), dtype=np.uint8)
    almost = ones.copy()
    almost[0, 0] = 0
    assert trap5_fitness(zeros).tolist() == [80]
    assert trap5_fitness(ones).tolist() == [100]
    assert trap5_fitness(almost).tolist() == [95]

    initial, schedule = make_inputs(123, 116)
    fitness = trap5_fitness(initial)
    vectorized = make_batched_children(
        initial,
        fitness,
        schedule.tournaments,
        schedule.block_choices,
        schedule.mutations,
    )
    scalar = np.stack(
        [
            make_serial_child(
                initial,
                fitness,
                schedule.tournaments[i],
                schedule.block_choices[i],
                schedule.mutations[i],
            )
            for i in range(16)
        ]
    )
    np.testing.assert_array_equal(vectorized, scalar)

    incumbent = np.zeros((POPULATION_SIZE, GENOME_LENGTH), dtype=np.uint8)
    incumbent_fitness = np.full(POPULATION_SIZE, 50, dtype=np.int16)
    equal_child = np.ones((1, GENOME_LENGTH), dtype=np.uint8)
    selected, selected_fitness = environmental_select(
        incumbent, incumbent_fitness, equal_child, np.array([50], dtype=np.int16)
    )
    assert np.all(selected == 0) and np.all(selected_fitness == 50)

    assert len(make_inputs(0, FULL_BUDGET)[1]) == 49_900
    assert 49_900 % BATCH_SIZE == 12


def write_environment(path: Path) -> None:
    processor = platform.processor() or platform.machine() or "unknown"
    lines = [
        f"Python: {platform.python_version()}",
        f"Python implementation: {platform.python_implementation()}",
        f"NumPy: {np.__version__}",
        f"Operating system: {platform.platform()}",
        f"Processor: {processor}",
        f"Machine: {platform.machine() or 'unknown'}",
        "Thread limits: OMP_NUM_THREADS=1, OPENBLAS_NUM_THREADS=1, "
        "MKL_NUM_THREADS=1, VECLIB_MAXIMUM_THREADS=1",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    p = successes / n
    denominator = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denominator
    half_width = z * np.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denominator
    return float(center - half_width), float(center + half_width)


def save_figure(rows: list[dict[str, object]], results: dict[str, object], path: Path) -> None:
    serial_successes = int(results["serial_success_count"])
    batch_successes = int(results["batch16_success_count"])
    proportions = np.array(
        [results["serial_success_proportion"], results["batch16_success_proportion"]],
        dtype=float,
    )
    intervals = [wilson_interval(serial_successes, 30), wilson_interval(batch_successes, 30)]
    lower_errors = proportions - np.array([item[0] for item in intervals])
    upper_errors = np.array([item[1] for item in intervals]) - proportions

    serial_times = np.array([row["serial_runtime_seconds"] for row in rows], dtype=float)
    batch_times = np.array([row["batch16_runtime_seconds"] for row in rows], dtype=float)

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.8), constrained_layout=True)
    colors = ["#4063A3", "#D97732"]

    x = np.arange(2)
    bars = axes[0].bar(
        x,
        proportions,
        yerr=np.vstack((lower_errors, upper_errors)),
        capsize=5,
        color=colors,
        edgecolor="black",
        linewidth=0.7,
    )
    axes[0].set_xticks(x, ["Serial", "Batch-16"])
    axes[0].set_ylim(0.0, 1.08)
    axes[0].set_ylabel("Optimum-reaching success proportion")
    axes[0].set_title("Success with Wilson 95% intervals")
    for bar, count in zip(bars, (serial_successes, batch_successes), strict=True):
        axes[0].text(
            bar.get_x() + bar.get_width() / 2,
            min(bar.get_height() + 0.035, 1.025),
            f"{count}/30",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )
    axes[0].grid(axis="y", alpha=0.22)

    for serial_time, batch_time in zip(serial_times, batch_times, strict=True):
        axes[1].plot([0, 1], [serial_time, batch_time], color="0.78", linewidth=0.8, zorder=1)
    axes[1].scatter(np.zeros(30), serial_times, color=colors[0], s=24, alpha=0.82, zorder=2)
    axes[1].scatter(np.ones(30), batch_times, color=colors[1], s=24, alpha=0.82, zorder=2)
    medians = np.array(
        [results["serial_median_runtime_seconds"], results["batch16_median_runtime_seconds"]],
        dtype=float,
    )
    axes[1].scatter(
        [0, 1],
        medians,
        marker="_",
        s=650,
        linewidths=4,
        color="black",
        label="Median",
        zorder=3,
    )
    axes[1].set_xticks([0, 1], ["Serial", "Batch-16"])
    axes[1].set_xlim(-0.35, 1.35)
    axes[1].set_ylabel("Runtime per run (seconds)")
    axes[1].set_title("Paired per-seed wall-clock runtime")
    axes[1].grid(axis="y", alpha=0.22)
    axes[1].legend(frameon=False, loc="upper right")
    axes[1].text(
        0.5,
        0.04,
        f"Relative median reduction: {results['relative_median_time_reduction_percent']:.1f}%",
        transform=axes[1].transAxes,
        ha="center",
        va="bottom",
        fontsize=10,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.85, "edgecolor": "0.75"},
    )

    fig.savefig(path, dpi=180)
    plt.close(fig)


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    n = len(rows)
    serial_success_count = sum(bool(row["serial_success"]) for row in rows)
    batch_success_count = sum(bool(row["batch16_success"]) for row in rows)
    serial_success = serial_success_count / n
    batch_success = batch_success_count / n
    success_difference_count = serial_success_count - batch_success_count
    success_loss_points = 100.0 * (serial_success - batch_success)

    serial_only = sum(
        bool(row["serial_success"]) and not bool(row["batch16_success"]) for row in rows
    )
    batch_only = sum(
        bool(row["batch16_success"]) and not bool(row["serial_success"]) for row in rows
    )
    both = sum(
        bool(row["serial_success"]) and bool(row["batch16_success"]) for row in rows
    )
    neither = n - serial_only - batch_only - both

    serial_times = np.array([row["serial_runtime_seconds"] for row in rows], dtype=float)
    batch_times = np.array([row["batch16_runtime_seconds"] for row in rows], dtype=float)
    serial_median = float(np.median(serial_times))
    batch_median = float(np.median(batch_times))
    time_reduction = 1.0 - batch_median / serial_median
    ratios = batch_times / serial_times
    ratio_q1, ratio_median, ratio_q3 = np.percentile(ratios, [25, 50, 75])

    # With n=30, a difference >= 0.15 is operationally a raw difference of 5.
    success_threshold_met = success_difference_count >= 5
    runtime_threshold_met = time_reduction >= 0.40
    hypothesis_supported = success_threshold_met and runtime_threshold_met

    return {
        "n_seeds": n,
        "evaluations_per_run": FULL_BUDGET,
        "timed_repetitions_per_seed_method": 3,
        "serial_success_count": serial_success_count,
        "batch16_success_count": batch_success_count,
        "serial_success_proportion": serial_success,
        "batch16_success_proportion": batch_success,
        "success_difference_count": success_difference_count,
        "success_loss_percentage_points": success_loss_points,
        "serial_only_success_count": serial_only,
        "batch16_only_success_count": batch_only,
        "both_success_count": both,
        "neither_success_count": neither,
        "serial_median_runtime_seconds": serial_median,
        "batch16_median_runtime_seconds": batch_median,
        "relative_median_time_reduction": time_reduction,
        "relative_median_time_reduction_percent": 100.0 * time_reduction,
        "paired_runtime_ratio_median": float(ratio_median),
        "paired_runtime_ratio_q1": float(ratio_q1),
        "paired_runtime_ratio_q3": float(ratio_q3),
        "paired_runtime_ratio_iqr": float(ratio_q3 - ratio_q1),
        "serial_median_final_best": float(np.median([row["serial_final_best"] for row in rows])),
        "batch16_median_final_best": float(np.median([row["batch16_final_best"] for row in rows])),
        "success_threshold_met": success_threshold_met,
        "runtime_threshold_met": runtime_threshold_met,
        "hypothesis_supported": hypothesis_supported,
        "classification": "supported" if hypothesis_supported else "refuted",
    }


def write_csv(rows: list[dict[str, object]], path: Path) -> None:
    fieldnames = [
        "seed",
        "serial_success",
        "batch16_success",
        "serial_first_hit",
        "batch16_first_hit",
        "serial_final_best",
        "batch16_final_best",
        "serial_runtime_seconds",
        "batch16_runtime_seconds",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    root = Path(__file__).resolve().parent
    figures = root / "figures"
    figures.mkdir(exist_ok=True)
    write_environment(root / "environment.txt")
    assert_protocol_invariants()

    print("Protocol checks passed. Running untimed warm-ups (seed 10000, 1,100 evaluations).", flush=True)
    warm_initial, warm_schedule = make_inputs(10_000, WARMUP_BUDGET)
    for method_name in ("serial", "batch16"):
        outcome = METHODS[method_name](warm_initial, warm_schedule, WARMUP_BUDGET)
        print(f"Warm-up {method_name}: {outcome}", flush=True)

    rows: list[dict[str, object]] = []
    for seed in SEEDS:
        initial_population, schedule = make_inputs(seed, FULL_BUDGET)
        original_order = ("serial", "batch16") if seed % 2 == 0 else ("batch16", "serial")
        outcomes: dict[str, list[RunOutcome]] = {"serial": [], "batch16": []}
        timings: dict[str, list[float]] = {"serial": [], "batch16": []}

        for repetition in range(3):
            method_order = original_order if repetition != 1 else tuple(reversed(original_order))
            for method_name in method_order:
                outcome, elapsed = timed_run(
                    method_name, initial_population, schedule, FULL_BUDGET
                )
                outcomes[method_name].append(outcome)
                timings[method_name].append(elapsed)

        for method_name in METHODS:
            if len(set(outcomes[method_name])) != 1:
                raise RuntimeError(
                    f"non-deterministic outcomes for seed {seed}, {method_name}: "
                    f"{outcomes[method_name]}"
                )

        serial = outcomes["serial"][0]
        batch16 = outcomes["batch16"][0]
        serial_runtime = float(median(timings["serial"]))
        batch_runtime = float(median(timings["batch16"]))
        rows.append(
            {
                "seed": seed,
                "serial_success": serial.success,
                "batch16_success": batch16.success,
                "serial_first_hit": serial.first_hit,
                "batch16_first_hit": batch16.first_hit,
                "serial_final_best": serial.final_best,
                "batch16_final_best": batch16.final_best,
                "serial_runtime_seconds": serial_runtime,
                "batch16_runtime_seconds": batch_runtime,
            }
        )
        print(
            f"Seed {seed:02d}: success S/B={int(serial.success)}/{int(batch16.success)}, "
            f"first hit S/B={serial.first_hit}/{batch16.first_hit}, "
            f"final S/B={serial.final_best}/{batch16.final_best}, "
            f"median time S/B={serial_runtime:.3f}/{batch_runtime:.3f}s",
            flush=True,
        )

    results = summarize(rows)
    write_csv(rows, root / "run_results.csv")
    (root / "results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    save_figure(rows, results, figures / "key_results.png")

    print("\nFinal summary", flush=True)
    print(
        "Ran serial and snapshot-based batch-16 steady-state GAs on 100-bit trap-5 "
        "for 30 paired seeds, 50,000 evaluations, and three timings per method.",
        flush=True,
    )
    print(
        f"Success: serial {results['serial_success_count']}/30 "
        f"({results['serial_success_proportion']:.3f}), batch-16 "
        f"{results['batch16_success_count']}/30 "
        f"({results['batch16_success_proportion']:.3f}); loss "
        f"{results['success_loss_percentage_points']:.2f} percentage points.",
        flush=True,
    )
    print(
        f"Paired outcomes: serial-only {results['serial_only_success_count']}, "
        f"batch-only {results['batch16_only_success_count']}, both "
        f"{results['both_success_count']}, neither {results['neither_success_count']}.",
        flush=True,
    )
    print(
        f"Median runtime: serial {results['serial_median_runtime_seconds']:.3f}s, "
        f"batch-16 {results['batch16_median_runtime_seconds']:.3f}s; reduction "
        f"{results['relative_median_time_reduction_percent']:.2f}%.",
        flush=True,
    )
    print(
        f"Paired batch/serial runtime ratio: median "
        f"{results['paired_runtime_ratio_median']:.3f}, IQR "
        f"[{results['paired_runtime_ratio_q1']:.3f}, "
        f"{results['paired_runtime_ratio_q3']:.3f}].",
        flush=True,
    )
    print(f"Hypothesis: {str(results['classification']).upper()}.", flush=True)


if __name__ == "__main__":
    main()
