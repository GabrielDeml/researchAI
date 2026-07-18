#!/usr/bin/env python3
"""Paired seeded Royal Road accounting experiment.

Runs a steady-state (mu+1) GA and a generational GA with genotype-fitness
memoization. The search trajectory is allowed to continue to the cache-miss
budget so the same run can be scored under cache-miss and attempted-candidate
accounting.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


Algorithm = Literal["muplus1", "generational"]

MU = 64
N_BITS = 64
BLOCK_SIZE = 8
TARGET = 56
BUDGET = 20_000
FAILURE_SCORE = BUDGET + 1
SEEDS = tuple(range(30))
MUTATION_RATE = 1.0 / N_BITS

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "run_records.csv"
SUMMARY_PATH = ROOT / "summary.json"
RESULTS_PATH = ROOT / "results.json"
FIGURE_DIR = ROOT / "figures"
FIGURE_PATH = FIGURE_DIR / "royal_road_accounting.png"


@dataclass
class RunRecord:
    algorithm: str
    seed: int
    target_reached: bool
    target_C_miss: int | None
    target_C_attempt: int | None
    S_miss: int
    S_attempt: int
    initialization_misses: int
    offspring_attempts: int
    offspring_cache_misses: int
    individual_offspring_ratio: float | None


def genotype_key(x: np.ndarray) -> bytes:
    """Convert a 64-bit uint8 genotype to exactly eight packed bytes."""
    key = np.packbits(x).tobytes()
    assert len(key) == 8
    return key


def royal_road_fitness(x: np.ndarray) -> int:
    """Eight times the number of completed consecutive eight-bit blocks."""
    return int(BLOCK_SIZE * np.all(x.reshape(-1, BLOCK_SIZE) == 1, axis=1).sum())


def cached_fitness(x: np.ndarray, cache: dict[bytes, int]) -> tuple[int, bool]:
    """Return fitness and whether this genotype caused a cache miss."""
    key = genotype_key(x)
    if key in cache:
        return cache[key], False
    fitness = royal_road_fitness(x)
    cache[key] = fitness
    return fitness, True


def select_parent_index(fitnesses: list[int], rng: np.random.Generator) -> int:
    """Size-two tournament, sampling with replacement and breaking ties first."""
    sampled = rng.integers(0, MU, size=2)
    first, second = int(sampled[0]), int(sampled[1])
    return first if fitnesses[first] >= fitnesses[second] else second


def make_child(
    population: list[np.ndarray], fitnesses: list[int], rng: np.random.Generator
) -> np.ndarray:
    """Select two parents, one-point crossover, then bitwise mutation."""
    parent1 = population[select_parent_index(fitnesses, rng)]
    parent2 = population[select_parent_index(fitnesses, rng)]
    crossover = int(rng.integers(1, N_BITS))
    child = np.concatenate((parent1[:crossover], parent2[crossover:]))
    mutation_mask = (rng.random(N_BITS) < MUTATION_RATE).astype(np.uint8)
    child ^= mutation_mask
    assert child.dtype == np.uint8 and child.shape == (N_BITS,)
    return child


def initialize_run(
    rng: np.random.Generator, cache: dict[bytes, int]
) -> tuple[list[np.ndarray], list[int], int, int | None, int | None]:
    """Build the complete population, retaining duplicates as separate members."""
    population: list[np.ndarray] = []
    fitnesses: list[int] = []
    init_cache_misses = 0
    target_c_miss: int | None = None
    target_c_attempt: int | None = None

    for attempt in range(1, MU + 1):
        genotype = rng.integers(0, 2, size=N_BITS, dtype=np.uint8)
        fitness, was_miss = cached_fitness(genotype, cache)
        init_cache_misses += int(was_miss)
        population.append(genotype)
        fitnesses.append(fitness)
        if fitness >= TARGET and target_c_attempt is None:
            target_c_miss = init_cache_misses
            target_c_attempt = attempt

    assert len(population) == MU and len(fitnesses) == MU
    return population, fitnesses, init_cache_misses, target_c_miss, target_c_attempt


def run_one(algorithm: Algorithm, seed: int) -> RunRecord:
    """Run one algorithm-seed pair through target attainment or miss budget."""
    rng = np.random.Generator(np.random.PCG64(seed))
    cache: dict[bytes, int] = {}
    (
        population,
        fitnesses,
        init_cache_misses,
        target_c_miss,
        target_c_attempt,
    ) = initialize_run(rng, cache)

    offspring_attempts = 0
    offspring_cache_misses = 0

    if target_c_attempt is None:
        if algorithm == "muplus1":
            while init_cache_misses + offspring_cache_misses < BUDGET:
                child = make_child(population, fitnesses, rng)
                offspring_attempts += 1
                child_fitness, was_miss = cached_fitness(child, cache)
                offspring_cache_misses += int(was_miss)

                current_misses = init_cache_misses + offspring_cache_misses
                current_attempts = MU + offspring_attempts
                if child_fitness >= TARGET:
                    target_c_miss = current_misses
                    target_c_attempt = current_attempts
                    break

                population.append(child)
                fitnesses.append(child_fitness)
                minimum = min(fitnesses)
                removal_candidates = np.flatnonzero(np.asarray(fitnesses) == minimum)
                removal_index = int(
                    removal_candidates[
                        int(rng.integers(0, len(removal_candidates)))
                    ]
                )
                del population[removal_index]
                del fitnesses[removal_index]
                assert len(population) == MU and len(fitnesses) == MU

        elif algorithm == "generational":
            stop = False
            while init_cache_misses + offspring_cache_misses < BUDGET and not stop:
                # These objects remain unchanged while all 64 children are made.
                parent_population = population
                parent_fitnesses = fitnesses
                children: list[np.ndarray] = []
                child_fitnesses: list[int] = []

                for _ in range(MU):
                    child = make_child(parent_population, parent_fitnesses, rng)
                    offspring_attempts += 1
                    child_fitness, was_miss = cached_fitness(child, cache)
                    offspring_cache_misses += int(was_miss)
                    children.append(child)
                    child_fitnesses.append(child_fitness)

                    current_misses = init_cache_misses + offspring_cache_misses
                    current_attempts = MU + offspring_attempts
                    if child_fitness >= TARGET:
                        target_c_miss = current_misses
                        target_c_attempt = current_attempts
                        stop = True
                        break
                    if current_misses == BUDGET:
                        stop = True
                        break

                if not stop:
                    assert len(children) == MU and len(child_fitnesses) == MU
                    population = children
                    fitnesses = child_fitnesses
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")

    target_reached = target_c_attempt is not None
    s_miss = (
        target_c_miss
        if target_reached and target_c_miss is not None and target_c_miss <= BUDGET
        else FAILURE_SCORE
    )
    s_attempt = (
        target_c_attempt
        if target_reached
        and target_c_attempt is not None
        and target_c_attempt <= BUDGET
        else FAILURE_SCORE
    )
    individual_ratio = (
        offspring_attempts / offspring_cache_misses
        if offspring_cache_misses > 0
        else None
    )

    total_misses = init_cache_misses + offspring_cache_misses
    assert init_cache_misses <= MU
    assert offspring_cache_misses <= offspring_attempts
    assert total_misses <= BUDGET
    assert target_reached or total_misses == BUDGET
    assert (s_miss <= BUDGET) == (
        target_reached and target_c_miss is not None and target_c_miss <= BUDGET
    )
    assert (s_attempt <= BUDGET) == (
        target_reached
        and target_c_attempt is not None
        and target_c_attempt <= BUDGET
    )

    return RunRecord(
        algorithm=algorithm,
        seed=seed,
        target_reached=target_reached,
        target_C_miss=target_c_miss,
        target_C_attempt=target_c_attempt,
        S_miss=s_miss,
        S_attempt=s_attempt,
        initialization_misses=init_cache_misses,
        offspring_attempts=offspring_attempts,
        offspring_cache_misses=offspring_cache_misses,
        individual_offspring_ratio=individual_ratio,
    )


def pooled_ratio(records: list[RunRecord]) -> float:
    attempts = sum(record.offspring_attempts for record in records)
    misses = sum(record.offspring_cache_misses for record in records)
    if misses == 0:
        raise RuntimeError("Pooled offspring ratio is undefined: zero cache misses")
    return attempts / misses


def write_run_records(records: list[RunRecord]) -> None:
    fieldnames = list(asdict(records[0]).keys())
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))


def make_figure(
    by_algorithm: dict[str, list[RunRecord]],
    pooled: dict[str, float],
    a_miss: float,
    a_attempt: float,
) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    fig, (ax_ratio, ax_advantage) = plt.subplots(1, 2, figsize=(16, 7), dpi=100)

    labels = {"muplus1": r"Steady-state ($\mu$+1)", "generational": "Generational"}
    colors = {"muplus1": "#2a6fbb", "generational": "#dc6b2f"}
    positions = {"muplus1": 0.0, "generational": 1.0}

    for algorithm in ("muplus1", "generational"):
        defined = [
            record.individual_offspring_ratio
            for record in by_algorithm[algorithm]
            if record.individual_offspring_ratio is not None
        ]
        jitter = np.linspace(-0.10, 0.10, num=len(defined)) if defined else np.array([])
        x = positions[algorithm] + jitter
        ax_ratio.scatter(
            x,
            defined,
            s=35,
            alpha=0.72,
            color=colors[algorithm],
            edgecolor="white",
            linewidth=0.4,
        )
        ax_ratio.scatter(
            positions[algorithm],
            pooled[algorithm],
            s=220,
            marker="D",
            color=colors[algorithm],
            edgecolor="black",
            linewidth=1.1,
            zorder=4,
            label=f"{labels[algorithm]} pooled = {pooled[algorithm]:.3f}",
        )

    ax_ratio.axhline(1.2, color="#666666", linestyle="--", linewidth=1.2)
    ax_ratio.axhline(1.8, color="#666666", linestyle="--", linewidth=1.2)
    ax_ratio.set_xticks([0, 1], [labels["muplus1"], labels["generational"]])
    ax_ratio.set_ylabel("Offspring attempts / cache misses")
    ax_ratio.set_title("Duplicate production by run")
    ax_ratio.grid(axis="y", alpha=0.2)
    ax_ratio.legend(frameon=False)

    bar_labels = [r"$A_{miss}$", r"$A_{attempt}$"]
    bar_values = [a_miss, a_attempt]
    bars = ax_advantage.bar(
        bar_labels,
        bar_values,
        color=["#3a923a", "#8c5fb3"],
        width=0.58,
    )
    threshold = 0.5 * a_miss
    ax_advantage.axhline(0, color="black", linewidth=1.0)
    ax_advantage.axhline(
        threshold,
        color="#666666",
        linestyle="--",
        linewidth=1.2,
        label=f"0.5 x A_miss = {threshold:.1f}",
    )
    span = max(abs(a_miss), abs(a_attempt), abs(threshold), 1.0)
    offset = 0.025 * span
    for bar, value in zip(bars, bar_values, strict=True):
        y = value + offset if value >= 0 else value - offset
        va = "bottom" if value >= 0 else "top"
        ax_advantage.text(
            bar.get_x() + bar.get_width() / 2,
            y,
            f"{value:.1f}",
            ha="center",
            va=va,
            fontweight="bold",
        )
    ax_advantage.margins(y=0.16)
    ax_advantage.set_ylabel("Median paired advantage (counts)")
    ax_advantage.set_title(r"Advantage of steady-state ($\mu$+1)")
    ax_advantage.grid(axis="y", alpha=0.2)
    ax_advantage.legend(frameon=False)

    fig.suptitle("Royal Road: cache-miss versus attempted-candidate accounting")
    fig.tight_layout()
    fig.savefig(FIGURE_PATH, dpi=100)
    plt.close(fig)


def main() -> None:
    records: list[RunRecord] = []
    for algorithm in ("muplus1", "generational"):
        for seed in SEEDS:
            records.append(run_one(algorithm, seed))

    by_algorithm = {
        algorithm: [r for r in records if r.algorithm == algorithm]
        for algorithm in ("muplus1", "generational")
    }
    assert all(len(group) == len(SEEDS) for group in by_algorithm.values())

    pooled = {
        algorithm: pooled_ratio(group) for algorithm, group in by_algorithm.items()
    }
    mu_by_seed = {record.seed: record for record in by_algorithm["muplus1"]}
    gen_by_seed = {record.seed: record for record in by_algorithm["generational"]}
    d_miss = np.asarray(
        [gen_by_seed[seed].S_miss - mu_by_seed[seed].S_miss for seed in SEEDS],
        dtype=np.int64,
    )
    d_attempt = np.asarray(
        [gen_by_seed[seed].S_attempt - mu_by_seed[seed].S_attempt for seed in SEEDS],
        dtype=np.int64,
    )
    a_miss = float(np.median(d_miss))
    a_attempt = float(np.median(d_attempt))

    conditions = {
        "condition_R_muplus1_ge_1_8": bool(pooled["muplus1"] >= 1.8),
        "condition_R_generational_le_1_2": bool(pooled["generational"] <= 1.2),
        "condition_A_miss_gt_0": bool(a_miss > 0.0),
        "condition_A_attempt_le_half_A_miss": bool(a_attempt <= 0.5 * a_miss),
    }
    supported = all(conditions.values())

    summary: dict[str, int | float | str | bool] = {
        "n_seeds": len(SEEDS),
        "mu": MU,
        "genotype_bits": N_BITS,
        "target_fitness": TARGET,
        "budget": BUDGET,
        "R_muplus1": float(pooled["muplus1"]),
        "R_generational": float(pooled["generational"]),
        "A_miss": a_miss,
        "A_attempt": a_attempt,
        "muplus1_success_miss_budget": sum(r.S_miss <= BUDGET for r in by_algorithm["muplus1"]),
        "generational_success_miss_budget": sum(r.S_miss <= BUDGET for r in by_algorithm["generational"]),
        "muplus1_success_attempt_budget": sum(r.S_attempt <= BUDGET for r in by_algorithm["muplus1"]),
        "generational_success_attempt_budget": sum(r.S_attempt <= BUDGET for r in by_algorithm["generational"]),
        **conditions,
        "hypothesis_supported": supported,
        "decision": "supported" if supported else "refuted",
    }

    write_run_records(records)
    with SUMMARY_PATH.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    # results.json is deliberately the same flat scalar summary required by the harness.
    with RESULTS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    make_figure(by_algorithm, pooled, a_miss, a_attempt)

    print("Royal Road experiment complete: 2 algorithms x 30 paired seeds")
    print(
        f"R_muplus1={pooled['muplus1']:.6f}, "
        f"R_generational={pooled['generational']:.6f}"
    )
    print(f"A_miss={a_miss:.1f}, A_attempt={a_attempt:.1f}")
    print(
        "Successes (miss/attempt): "
        f"muplus1={summary['muplus1_success_miss_budget']}/"
        f"{summary['muplus1_success_attempt_budget']}, "
        f"generational={summary['generational_success_miss_budget']}/"
        f"{summary['generational_success_attempt_budget']}"
    )
    print(f"Decision: hypothesis {summary['decision']}")


if __name__ == "__main__":
    main()
