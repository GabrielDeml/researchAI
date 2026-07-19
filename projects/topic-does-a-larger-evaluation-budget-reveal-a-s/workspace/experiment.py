#!/usr/bin/env python3
"""Prospective paired trap-5 evaluation-budget experiment.

This script is intentionally self-contained: it synthesizes every population and
operator schedule from fixed PCG64 seeds and writes all outputs locally.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import time
from pathlib import Path

# Keep Matplotlib/font caches inside the self-contained workspace.
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))
os.environ.setdefault("XDG_CACHE_HOME", str(Path(__file__).resolve().parent / ".cache"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numba
import numpy as np
import pandas as pd
import scipy
from numba import njit
from scipy.stats import binom


N_REPLICATES = 64
POPULATION_SIZE = 256
N_BLOCKS = 20
BITS_PER_BLOCK = 5
GENOME_LENGTH = N_BLOCKS * BITS_PER_BLOCK
BATCH_SIZE = 16
CHECKPOINTS = np.array([100_000, 250_000, 500_000], dtype=np.int64)
CHECKPOINT_EVENTS = CHECKPOINTS - POPULATION_SIZE
N_EVENTS = int(CHECKPOINT_EVENTS[-1])
INITIALIZATION_SEED_BASE = 10_000
SCHEDULE_SEED_BASE = 20_000
BOOTSTRAP_SEED = 900_001
N_BOOTSTRAP = 20_000
RUNTIME_LIMIT_SECONDS = 30.0 * 60.0
ALGORITHM_NAMES = ("serial", "batch16")

ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "results"
FIGURES_DIR = ROOT / "figures"
ROOT_RESULTS_PATH = ROOT / "results.json"
CSV_PATH = RESULTS_DIR / "checkpoint_results.csv"
SUMMARY_COPY_PATH = RESULTS_DIR / "summary.json"
FIGURE_PATH = FIGURES_DIR / "key_result.png"

TRAP_SCORE = np.array(
    [5 if value == 31 else 4 - int(value).bit_count() for value in range(32)],
    dtype=np.int16,
)


@njit(cache=True)
def population_fitness(population: np.ndarray, trap_score: np.ndarray) -> np.ndarray:
    """Evaluate a block-encoded population."""
    fitness = np.empty(population.shape[0], dtype=np.int16)
    for i in range(population.shape[0]):
        total = 0
        for block in range(population.shape[1]):
            total += trap_score[population[i, block]]
        fitness[i] = total
    return fitness


@njit(cache=True, inline="always")
def tournament_winner(
    a: int, b: int, fitness: np.ndarray, tie_priority: np.ndarray
) -> int:
    """Return the fitter tournament member, resolving ties by larger priority."""
    if fitness[a] > fitness[b]:
        return a
    if fitness[b] > fitness[a]:
        return b
    if tie_priority[a] >= tie_priority[b]:
        return a
    return b


@njit(cache=True, inline="always")
def best_summary(
    population: np.ndarray, fitness: np.ndarray, tie_priority: np.ndarray
) -> tuple:
    """Return best fitness, solved-block count, and optimum-presence flag."""
    best = 0
    for i in range(1, population.shape[0]):
        if fitness[i] > fitness[best] or (
            fitness[i] == fitness[best] and tie_priority[i] > tie_priority[best]
        ):
            best = i
    solved = 0
    for block in range(population.shape[1]):
        if population[best, block] == 31:
            solved += 1
    return fitness[best], solved, fitness[best] == 100


@njit(cache=True)
def run_serial(
    initial_population: np.ndarray,
    initial_fitness: np.ndarray,
    initial_ties: np.ndarray,
    tournament_indices: np.ndarray,
    boundaries: np.ndarray,
    mutation_blocks: np.ndarray,
    mutation_bits: np.ndarray,
    targets: np.ndarray,
    offspring_ties: np.ndarray,
    checkpoint_events: np.ndarray,
    trap_score: np.ndarray,
) -> tuple:
    """Run immediate target-slot replacement for every offspring event."""
    population = initial_population.copy()
    fitness = initial_fitness.copy()
    ties = initial_ties.copy()
    child = np.empty(N_BLOCKS, dtype=np.uint8)
    out_fitness = np.empty(checkpoint_events.shape[0], dtype=np.int16)
    out_solved = np.empty(checkpoint_events.shape[0], dtype=np.int16)
    out_optimum = np.empty(checkpoint_events.shape[0], dtype=np.bool_)
    checkpoint_index = 0

    for event in range(tournament_indices.shape[0]):
        parent1 = tournament_winner(
            tournament_indices[event, 0],
            tournament_indices[event, 1],
            fitness,
            ties,
        )
        parent2 = tournament_winner(
            tournament_indices[event, 2],
            tournament_indices[event, 3],
            fitness,
            ties,
        )
        boundary = boundaries[event]
        mutation_block = mutation_blocks[event]
        mutation_mask = np.uint8(1 << mutation_bits[event])
        child_fitness = 0
        for block in range(N_BLOCKS):
            if block < boundary:
                value = population[parent1, block]
            else:
                value = population[parent2, block]
            if block == mutation_block:
                value ^= mutation_mask
            child[block] = value
            child_fitness += trap_score[value]

        target = targets[event]
        child_tie = offspring_ties[event]
        if child_fitness > fitness[target] or (
            child_fitness == fitness[target] and child_tie > ties[target]
        ):
            for block in range(N_BLOCKS):
                population[target, block] = child[block]
            fitness[target] = child_fitness
            ties[target] = child_tie

        completed_events = event + 1
        if (
            checkpoint_index < checkpoint_events.shape[0]
            and completed_events == checkpoint_events[checkpoint_index]
        ):
            best_fit, solved, optimum = best_summary(population, fitness, ties)
            out_fitness[checkpoint_index] = best_fit
            out_solved[checkpoint_index] = solved
            out_optimum[checkpoint_index] = optimum
            checkpoint_index += 1

    return out_fitness, out_solved, out_optimum


@njit(cache=True)
def run_batch16(
    initial_population: np.ndarray,
    initial_fitness: np.ndarray,
    initial_ties: np.ndarray,
    tournament_indices: np.ndarray,
    boundaries: np.ndarray,
    mutation_blocks: np.ndarray,
    mutation_bits: np.ndarray,
    targets: np.ndarray,
    offspring_ties: np.ndarray,
    checkpoint_events: np.ndarray,
    trap_score: np.ndarray,
) -> tuple:
    """Run 16-offspring frozen-parent batches with ordered live replacement."""
    population = initial_population.copy()
    fitness = initial_fitness.copy()
    ties = initial_ties.copy()
    snapshot_population = np.empty_like(population)
    snapshot_fitness = np.empty_like(fitness)
    snapshot_ties = np.empty_like(ties)
    children = np.empty((BATCH_SIZE, N_BLOCKS), dtype=np.uint8)
    child_fitnesses = np.empty(BATCH_SIZE, dtype=np.int16)
    out_fitness = np.empty(checkpoint_events.shape[0], dtype=np.int16)
    out_solved = np.empty(checkpoint_events.shape[0], dtype=np.int16)
    out_optimum = np.empty(checkpoint_events.shape[0], dtype=np.bool_)
    checkpoint_index = 0

    for batch_start in range(0, tournament_indices.shape[0], BATCH_SIZE):
        snapshot_population[:, :] = population
        snapshot_fitness[:] = fitness
        snapshot_ties[:] = ties

        for offset in range(BATCH_SIZE):
            event = batch_start + offset
            parent1 = tournament_winner(
                tournament_indices[event, 0],
                tournament_indices[event, 1],
                snapshot_fitness,
                snapshot_ties,
            )
            parent2 = tournament_winner(
                tournament_indices[event, 2],
                tournament_indices[event, 3],
                snapshot_fitness,
                snapshot_ties,
            )
            boundary = boundaries[event]
            mutation_block = mutation_blocks[event]
            mutation_mask = np.uint8(1 << mutation_bits[event])
            child_fitness = 0
            for block in range(N_BLOCKS):
                if block < boundary:
                    value = snapshot_population[parent1, block]
                else:
                    value = snapshot_population[parent2, block]
                if block == mutation_block:
                    value ^= mutation_mask
                children[offset, block] = value
                child_fitness += trap_score[value]
            child_fitnesses[offset] = child_fitness

        for offset in range(BATCH_SIZE):
            event = batch_start + offset
            target = targets[event]
            child_fitness = child_fitnesses[offset]
            child_tie = offspring_ties[event]
            if child_fitness > fitness[target] or (
                child_fitness == fitness[target] and child_tie > ties[target]
            ):
                for block in range(N_BLOCKS):
                    population[target, block] = children[offset, block]
                fitness[target] = child_fitness
                ties[target] = child_tie

        completed_events = batch_start + BATCH_SIZE
        if (
            checkpoint_index < checkpoint_events.shape[0]
            and completed_events == checkpoint_events[checkpoint_index]
        ):
            best_fit, solved, optimum = best_summary(population, fitness, ties)
            out_fitness[checkpoint_index] = best_fit
            out_solved[checkpoint_index] = solved
            out_optimum[checkpoint_index] = optimum
            checkpoint_index += 1

    return out_fitness, out_solved, out_optimum


def make_initial_population(replicate: int) -> tuple[np.ndarray, np.ndarray]:
    """Draw the paired population and priorities from PCG64(10000 + r)."""
    rng = np.random.Generator(np.random.PCG64(INITIALIZATION_SEED_BASE + replicate))
    bits = rng.integers(
        0,
        2,
        size=(POPULATION_SIZE, N_BLOCKS, BITS_PER_BLOCK),
        dtype=np.uint8,
    )
    weights = (np.uint8(1) << np.arange(BITS_PER_BLOCK, dtype=np.uint8))
    population = np.sum(bits * weights, axis=2, dtype=np.uint16).astype(np.uint8)
    tie_priorities = rng.bit_generator.random_raw(POPULATION_SIZE).astype(
        np.uint64, copy=False
    )
    return population, tie_priorities


def bounded_uint64(
    raw: np.ndarray, bound: int, rng: np.random.Generator
) -> tuple[np.ndarray, int]:
    """Map uint64 draws exactly uniformly to [0, bound) by rejection."""
    threshold = (1 << 64) % bound
    accepted = raw >= np.uint64(threshold)
    rejection_count = int(np.count_nonzero(~accepted))
    while not np.all(accepted):
        replacement = rng.bit_generator.random_raw(int(np.count_nonzero(~accepted)))
        raw[~accepted] = replacement
        accepted = raw >= np.uint64(threshold)
        rejection_count += int(np.count_nonzero(~accepted))
    return (raw % np.uint64(bound)), rejection_count


def make_schedule(replicate: int) -> tuple[tuple[np.ndarray, ...], int]:
    """Generate one event-major shared schedule from PCG64(20000 + r)."""
    rng = np.random.Generator(np.random.PCG64(SCHEDULE_SEED_BASE + replicate))
    # Columns are generated in the exact per-event protocol order:
    # four tournament slots, boundary, mutation block, mutation bit, target, tie.
    raw = rng.bit_generator.random_raw((N_EVENTS, 9))
    rejection_count = 0

    tournament_raw, count = bounded_uint64(raw[:, :4], POPULATION_SIZE, rng)
    rejection_count += count
    boundary_raw, count = bounded_uint64(raw[:, 4], N_BLOCKS - 1, rng)
    rejection_count += count
    mutation_block_raw, count = bounded_uint64(raw[:, 5], N_BLOCKS, rng)
    rejection_count += count
    mutation_bit_raw, count = bounded_uint64(raw[:, 6], BITS_PER_BLOCK, rng)
    rejection_count += count
    target_raw, count = bounded_uint64(raw[:, 7], POPULATION_SIZE, rng)
    rejection_count += count

    tournament_indices = tournament_raw.astype(np.uint16)
    boundaries = (boundary_raw + 1).astype(np.uint8)
    mutation_blocks = mutation_block_raw.astype(np.uint8)
    mutation_bits = mutation_bit_raw.astype(np.uint8)
    targets = target_raw.astype(np.uint16)
    offspring_ties = raw[:, 8].copy()
    return (
        tournament_indices,
        boundaries,
        mutation_blocks,
        mutation_bits,
        targets,
        offspring_ties,
    ), rejection_count


def warm_up_numba() -> None:
    """Compile all Numba kernels before the timed experiment."""
    population, ties = make_initial_population(0)
    fitness = population_fitness(population, TRAP_SCORE)
    rng = np.random.Generator(np.random.PCG64(123456789))
    events = BATCH_SIZE
    tournament_indices = rng.integers(
        0, POPULATION_SIZE, size=(events, 4), dtype=np.uint16
    )
    boundaries = rng.integers(1, N_BLOCKS, size=events, dtype=np.uint8)
    mutation_blocks = rng.integers(0, N_BLOCKS, size=events, dtype=np.uint8)
    mutation_bits = rng.integers(0, BITS_PER_BLOCK, size=events, dtype=np.uint8)
    targets = rng.integers(0, POPULATION_SIZE, size=events, dtype=np.uint16)
    offspring_ties = rng.bit_generator.random_raw(events)
    checkpoints = np.array([events], dtype=np.int64)
    args = (
        population,
        fitness,
        ties,
        tournament_indices,
        boundaries,
        mutation_blocks,
        mutation_bits,
        targets,
        offspring_ties,
        checkpoints,
        TRAP_SCORE,
    )
    run_serial(*args)
    run_batch16(*args)


def holm_adjust(p_values: np.ndarray) -> np.ndarray:
    """Holm step-down family-wise adjustment."""
    order = np.argsort(p_values)
    adjusted_sorted = np.empty_like(p_values, dtype=np.float64)
    running_max = 0.0
    m = len(p_values)
    for rank, original_index in enumerate(order):
        candidate = min(1.0, float((m - rank) * p_values[original_index]))
        running_max = max(running_max, candidate)
        adjusted_sorted[rank] = running_max
    adjusted = np.empty_like(adjusted_sorted)
    for rank, original_index in enumerate(order):
        adjusted[original_index] = adjusted_sorted[rank]
    return adjusted


def write_figure(
    means: np.ndarray,
    ci_low: np.ndarray,
    ci_high: np.ndarray,
    eligible_n: int,
    serial_success: np.ndarray,
    batch_success: np.ndarray,
) -> None:
    """Create the prespecified two-panel 1600x900 result figure."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    x = CHECKPOINTS / 1000
    fig, axes = plt.subplots(1, 2, figsize=(16, 9), dpi=100)

    if eligible_n > 0:
        errors = np.vstack((means - ci_low, ci_high - means))
        axes[0].errorbar(
            x,
            means,
            yerr=errors,
            marker="o",
            linewidth=2.2,
            capsize=6,
            color="#1768AC",
            label="Serial − batch16",
        )
    else:
        axes[0].text(
            0.5,
            0.5,
            "No eligible pairs",
            transform=axes[0].transAxes,
            ha="center",
            va="center",
            fontsize=16,
        )
    axes[0].axhline(1.0, color="#C33C54", linestyle="--", linewidth=2, label="Threshold = 1")
    axes[0].set_title(f"Eligible-cohort paired progress (n={eligible_n})")
    axes[0].set_xlabel("Total fitness evaluations (thousands)")
    axes[0].set_ylabel("Mean solved-block difference")
    axes[0].set_xticks(x)
    axes[0].grid(alpha=0.25)
    axes[0].legend()

    axes[1].plot(x, serial_success, marker="o", linewidth=2.2, label="Serial")
    axes[1].plot(x, batch_success, marker="s", linewidth=2.2, label="Frozen-parent batch16")
    axes[1].set_title("Optimum success across all 64 pairs")
    axes[1].set_xlabel("Total fitness evaluations (thousands)")
    axes[1].set_ylabel("Optimum-success proportion")
    axes[1].set_xticks(x)
    axes[1].set_ylim(-0.03, 1.03)
    axes[1].grid(alpha=0.25)
    axes[1].legend()

    fig.suptitle("Trap-5: serial replacement vs frozen-parent batches of 16", fontsize=17)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(FIGURE_PATH, dpi=100)
    plt.close(fig)


def main() -> None:
    assert sys.version_info[:2] == (3, 11), "Protocol requires Python 3.11"
    assert N_EVENTS == 499_744
    assert np.all(CHECKPOINT_EVENTS % BATCH_SIZE == 0)
    assert TRAP_SCORE[31] == 5
    assert np.array_equal(TRAP_SCORE[:5], np.array([4, 3, 3, 2, 3], dtype=np.int16))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    print("Compiling Numba kernels (untimed warm-up)...", flush=True)
    warm_up_numba()

    best_fitness = np.empty((N_REPLICATES, 2, len(CHECKPOINTS)), dtype=np.int16)
    solved_blocks = np.empty_like(best_fitness)
    optimum_reached = np.empty((N_REPLICATES, 2, len(CHECKPOINTS)), dtype=np.bool_)
    schedule_rejections = 0

    print(
        f"Running {N_REPLICATES} deterministic paired replicates to "
        f"{CHECKPOINTS[-1]:,} evaluations...",
        flush=True,
    )
    start = time.perf_counter()
    for replicate in range(N_REPLICATES):
        initial_population, initial_ties = make_initial_population(replicate)
        initial_fitness = population_fitness(initial_population, TRAP_SCORE)
        schedule, rejection_count = make_schedule(replicate)
        schedule_rejections += rejection_count
        args = (
            initial_population,
            initial_fitness,
            initial_ties,
            *schedule,
            CHECKPOINT_EVENTS,
            TRAP_SCORE,
        )
        serial_result = run_serial(*args)
        batch_result = run_batch16(*args)
        best_fitness[replicate, 0, :] = serial_result[0]
        solved_blocks[replicate, 0, :] = serial_result[1]
        optimum_reached[replicate, 0, :] = serial_result[2]
        best_fitness[replicate, 1, :] = batch_result[0]
        solved_blocks[replicate, 1, :] = batch_result[1]
        optimum_reached[replicate, 1, :] = batch_result[2]
        if (replicate + 1) % 8 == 0:
            print(f"  completed {replicate + 1:2d}/{N_REPLICATES} pairs", flush=True)
        # Release this replicate's schedule before constructing the next one.
        del args, schedule, serial_result, batch_result
    elapsed_seconds = time.perf_counter() - start
    assert elapsed_seconds <= RUNTIME_LIMIT_SECONDS, (
        f"Timed experiment took {elapsed_seconds / 60:.3f} minutes, exceeding 30"
    )

    eligible = ~(optimum_reached[:, 0, 0] | optimum_reached[:, 1, 0])
    eligible_n = int(eligible.sum())
    eligible_fraction = eligible_n / N_REPLICATES
    paired_solved_differences = (
        solved_blocks[:, 0, :].astype(np.float64)
        - solved_blocks[:, 1, :].astype(np.float64)
    )
    paired_fitness_differences = (
        best_fitness[:, 0, :].astype(np.float64)
        - best_fitness[:, 1, :].astype(np.float64)
    )

    if eligible_n > 0:
        eligible_solved = paired_solved_differences[eligible, :]
        primary_means = eligible_solved.mean(axis=0)
        fitness_means = paired_fitness_differences[eligible, :].mean(axis=0)
        bootstrap_rng = np.random.Generator(np.random.PCG64(BOOTSTRAP_SEED))
        bootstrap_indices = bootstrap_rng.integers(
            0, eligible_n, size=(N_BOOTSTRAP, eligible_n)
        )
        bootstrap_means = eligible_solved[bootstrap_indices, :].mean(axis=1)
        ci_low = np.percentile(bootstrap_means, 5, axis=0)
        ci_high = np.percentile(bootstrap_means, 95, axis=0)
        decisions = np.where(primary_means >= 1.0, "supported", "refuted")
    else:
        primary_means = np.full(len(CHECKPOINTS), np.nan)
        fitness_means = np.full(len(CHECKPOINTS), np.nan)
        ci_low = np.full(len(CHECKPOINTS), np.nan)
        ci_high = np.full(len(CHECKPOINTS), np.nan)
        decisions = np.array(["refuted"] * len(CHECKPOINTS))

    serial_success = optimum_reached[:, 0, :].mean(axis=0)
    batch_success = optimum_reached[:, 1, :].mean(axis=0)
    success_difference = serial_success - batch_success
    n10 = np.sum(optimum_reached[:, 0, :] & ~optimum_reached[:, 1, :], axis=0)
    n01 = np.sum(~optimum_reached[:, 0, :] & optimum_reached[:, 1, :], axis=0)
    raw_p = np.ones(len(CHECKPOINTS), dtype=np.float64)
    for j in range(len(CHECKPOINTS)):
        discordant = int(n10[j] + n01[j])
        if discordant > 0:
            raw_p[j] = float(binom.sf(int(n10[j]) - 1, discordant, 0.5))
    adjusted_p = holm_adjust(raw_p)
    success_advantage = (serial_success > batch_success) & (adjusted_p < 0.05)

    rows: list[dict[str, object]] = []
    for replicate in range(N_REPLICATES):
        for algorithm_index, algorithm in enumerate(ALGORITHM_NAMES):
            for checkpoint_index, evaluations in enumerate(CHECKPOINTS):
                rows.append(
                    {
                        "replicate": replicate,
                        "algorithm": algorithm,
                        "evaluations": int(evaluations),
                        "best_fitness": int(
                            best_fitness[replicate, algorithm_index, checkpoint_index]
                        ),
                        "solved_blocks": int(
                            solved_blocks[replicate, algorithm_index, checkpoint_index]
                        ),
                        "optimum_reached": bool(
                            optimum_reached[replicate, algorithm_index, checkpoint_index]
                        ),
                        "eligible_at_100000": bool(eligible[replicate]),
                    }
                )
    frame = pd.DataFrame(rows)
    frame.to_csv(CSV_PATH, index=False)

    summary: dict[str, object] = {
        "experiment_topic": "Does a larger evaluation budget reveal a success-rate difference?",
        "replicate_n": N_REPLICATES,
        "population_size": POPULATION_SIZE,
        "trap_blocks": N_BLOCKS,
        "bits_per_block": BITS_PER_BLOCK,
        "genome_length": GENOME_LENGTH,
        "batch_size": BATCH_SIZE,
        "max_evaluations": int(CHECKPOINTS[-1]),
        "offspring_events_per_run": N_EVENTS,
        "eligible_n": eligible_n,
        "eligible_fraction": eligible_fraction,
        "decision_threshold_solved_blocks": 1.0,
        "bootstrap_resamples": N_BOOTSTRAP,
        "bootstrap_interval_percent": 90,
        "initialization_seed_base": INITIALIZATION_SEED_BASE,
        "initialization_seed_rule": "10000 + replicate",
        "operator_schedule_seed_base": SCHEDULE_SEED_BASE,
        "operator_schedule_seed_rule": "20000 + replicate",
        "bootstrap_seed": BOOTSTRAP_SEED,
        "schedule_rejection_redraws": schedule_rejections,
        "runtime_seconds": elapsed_seconds,
        "runtime_minutes": elapsed_seconds / 60.0,
        "runtime_within_30_minutes": elapsed_seconds <= RUNTIME_LIMIT_SECONDS,
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "numba_version": numba.__version__,
        "scipy_version": scipy.__version__,
        "pandas_version": pd.__version__,
        "matplotlib_version": matplotlib.__version__,
    }
    for j, evaluations in enumerate(CHECKPOINTS):
        prefix = f"at_{int(evaluations)}"
        summary[f"{prefix}_primary_decision"] = str(decisions[j])
        summary[f"{prefix}_eligible_mean_solved_block_difference"] = (
            float(primary_means[j]) if eligible_n > 0 else "not_applicable"
        )
        summary[f"{prefix}_bootstrap_90pct_low"] = (
            float(ci_low[j]) if eligible_n > 0 else "not_applicable"
        )
        summary[f"{prefix}_bootstrap_90pct_high"] = (
            float(ci_high[j]) if eligible_n > 0 else "not_applicable"
        )
        summary[f"{prefix}_eligible_mean_best_fitness_difference"] = (
            float(fitness_means[j]) if eligible_n > 0 else "not_applicable"
        )
        summary[f"{prefix}_serial_optimum_success_count"] = int(
            optimum_reached[:, 0, j].sum()
        )
        summary[f"{prefix}_batch16_optimum_success_count"] = int(
            optimum_reached[:, 1, j].sum()
        )
        summary[f"{prefix}_serial_optimum_success_proportion"] = float(
            serial_success[j]
        )
        summary[f"{prefix}_batch16_optimum_success_proportion"] = float(
            batch_success[j]
        )
        summary[f"{prefix}_optimum_success_proportion_difference"] = float(
            success_difference[j]
        )
        summary[f"{prefix}_mcnemar_n10_serial_only"] = int(n10[j])
        summary[f"{prefix}_mcnemar_n01_batch16_only"] = int(n01[j])
        summary[f"{prefix}_mcnemar_p_one_sided_raw"] = float(raw_p[j])
        summary[f"{prefix}_mcnemar_p_holm"] = float(adjusted_p[j])
        summary[f"{prefix}_success_rate_advantage_declared"] = bool(
            success_advantage[j]
        )

    # Every value is scalar by construction, as required for the root JSON.
    assert all(
        isinstance(value, (str, int, float, bool)) for value in summary.values()
    )
    serialized = json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ROOT_RESULTS_PATH.write_text(serialized, encoding="utf-8")
    SUMMARY_COPY_PATH.write_text(serialized, encoding="utf-8")
    write_figure(
        primary_means,
        ci_low,
        ci_high,
        eligible_n,
        serial_success,
        batch_success,
    )

    print("\nFinal summary")
    print(
        f"Ran 64 paired serial-vs-batch16 trap-5 comparisons through 500,000 "
        f"evaluations in {elapsed_seconds / 60.0:.3f} minutes."
    )
    print(f"Eligible cohort: {eligible_n}/64 ({eligible_fraction:.3f}).")
    for j, evaluations in enumerate(CHECKPOINTS):
        mean_text = "NA" if eligible_n == 0 else f"{primary_means[j]:+.3f}"
        ci_text = (
            "NA"
            if eligible_n == 0
            else f"[{ci_low[j]:+.3f}, {ci_high[j]:+.3f}]"
        )
        print(
            f"{int(evaluations):,}: mean solved-block difference {mean_text}, "
            f"90% bootstrap CI {ci_text}, {decisions[j]}; success "
            f"serial={serial_success[j]:.3f}, batch16={batch_success[j]:.3f}, "
            f"Holm p={adjusted_p[j]:.6g}, advantage={bool(success_advantage[j])}."
        )
    if np.any(decisions == "supported"):
        print("Primary result: supports at least one prospectively specified budget.")
    else:
        print("Primary result: refutes the hypothesis at all three specified budgets.")


if __name__ == "__main__":
    main()
