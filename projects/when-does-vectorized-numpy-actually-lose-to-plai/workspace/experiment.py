#!/usr/bin/env python3
"""Benchmark np.where against the specified scalar Python selection loop."""

from __future__ import annotations

import csv
import gc
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable


# These variables must be set before NumPy (or a linked numerical library) loads.
THREAD_ENVIRONMENT = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
}
for _name, _value in THREAD_ENVIRONMENT.items():
    os.environ[_name] = _value

# Keep plotting caches within the reproducible workspace on sandboxed macOS.
os.environ.setdefault(
    "MPLCONFIGDIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".matplotlib")
)


WORKSPACE = Path(__file__).resolve().parent
K_VALUES = tuple(range(1, 21))
MASK_TYPES = ("random_50pct", "all_true")
ROUNDS = 15
BOOTSTRAP_REPLICATES = 10_000
PRACTICAL_THRESHOLD = 1.05
DATA_SEED_BASE = 20_000
MASK_SEED_BASE = 10_000
ORDER_SEED = 314_159
BOOTSTRAP_SEED = 271_828
TARGET_BLOCK_NS = 20_000_000
MAX_REPETITIONS = 200_000

# Bound in main only after the arm64 check, keeping NumPy unimported until then.
np: Any = None


def numpy_select(mask, a, b):
    return np.where(mask, a, b)


def python_select(mask, a, b):
    out = np.empty_like(a)
    for i in range(a.size):
        if mask[i]:
            out[i] = a[i]
        else:
            out[i] = b[i]
    return out


def cpu_model() -> str:
    """Read only non-sensitive hardware fields, preferring the Apple chip name."""
    try:
        completed = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"],
            check=False,
            capture_output=True,
            text=True,
        )
        value = completed.stdout.strip()
        if completed.returncode == 0 and value:
            return value
    except OSError:
        pass

    try:
        completed = subprocess.run(
            ["/usr/sbin/system_profiler", "SPHardwareDataType"],
            check=False,
            capture_output=True,
            text=True,
        )
        for line in completed.stdout.splitlines():
            match = re.match(r"\s*Chip:\s*(.+?)\s*$", line)
            if match:
                return match.group(1)
    except OSError:
        pass
    return "unknown"


def base_environment() -> dict[str, Any]:
    return {
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "python_executable": sys.executable,
        "macos_version": platform.mac_ver()[0],
        "platform": platform.platform(),
        "cpu_model": cpu_model(),
        "thread_environment": dict(THREAD_ENVIRONMENT),
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_failure(error: str, environment: dict[str, Any]) -> None:
    write_json(WORKSPACE / "environment.json", environment)
    write_json(
        WORKSPACE / "results.json",
        {
            "completed": False,
            "decision": "not_run",
            "error": error,
            "machine": str(environment.get("machine", "unknown")),
        },
    )
    print(f"Experiment did not complete: {error}")


def make_inputs() -> dict[tuple[int, str], tuple[Any, Any, Any]]:
    inputs: dict[tuple[int, str], tuple[Any, Any, Any]] = {}
    for k in K_VALUES:
        n = 2**k
        data_rng = np.random.default_rng(DATA_SEED_BASE + k)
        a = np.ascontiguousarray(data_rng.standard_normal(n, dtype=np.float64))
        b = np.ascontiguousarray(data_rng.standard_normal(n, dtype=np.float64))

        all_true = np.ones(n, dtype=np.bool_)
        random_mask = np.zeros(n, dtype=np.bool_)
        random_mask[: n // 2] = True
        np.random.default_rng(MASK_SEED_BASE + k).shuffle(random_mask)

        assert a.dtype == np.float64 and b.dtype == np.float64
        assert a.flags.c_contiguous and b.flags.c_contiguous
        assert int(np.count_nonzero(random_mask)) == n // 2
        inputs[(k, "random_50pct")] = (random_mask, a, b)
        inputs[(k, "all_true")] = (all_true, a, b)
    return inputs


def validate_and_warm(inputs: dict[tuple[int, str], tuple[Any, Any, Any]]) -> None:
    for k in K_VALUES:
        for mask_type in MASK_TYPES:
            mask, a, b = inputs[(k, mask_type)]
            numpy_result = numpy_select(mask, a, b)
            python_result = python_select(mask, a, b)
            if not np.array_equal(numpy_result, python_result):
                raise AssertionError(f"result mismatch for k={k}, mask_type={mask_type}")
            del numpy_result, python_result
            for _ in range(3):
                numpy_select(mask, a, b)
                python_select(mask, a, b)


def one_call_ns(func: Callable[..., Any], mask: Any, a: Any, b: Any) -> int:
    start_ns = time.perf_counter_ns()
    last = func(mask, a, b)
    elapsed_ns = time.perf_counter_ns() - start_ns
    # Consume the result after the timer; keeping the local name mirrors timed blocks.
    float(last[0]) + float(last[-1])
    return elapsed_ns


def choose_repetitions(
    inputs: dict[tuple[int, str], tuple[Any, Any, Any]],
) -> dict[tuple[int, str, str], int]:
    repetitions: dict[tuple[int, str, str], int] = {}
    implementations = (("numpy", numpy_select), ("python", python_select))
    for k in K_VALUES:
        for mask_type in MASK_TYPES:
            mask, a, b = inputs[(k, mask_type)]
            for implementation, func in implementations:
                pilots = [one_call_ns(func, mask, a, b) for _ in range(3)]
                pilot_median_ns = int(np.median(np.asarray(pilots, dtype=np.int64)))
                repetitions[(k, mask_type, implementation)] = max(
                    1,
                    min(
                        MAX_REPETITIONS,
                        math.ceil(TARGET_BLOCK_NS / max(1, pilot_median_ns)),
                    ),
                )
    return repetitions


def time_block(
    func: Callable[..., Any], repetitions: int, mask: Any, a: Any, b: Any
) -> tuple[int, float]:
    start_ns = time.perf_counter_ns()
    for _ in range(repetitions):
        last = func(mask, a, b)
    elapsed_ns = time.perf_counter_ns() - start_ns
    checksum_contribution = float(last[0]) + float(last[-1])
    return elapsed_ns, checksum_contribution


def benchmark(
    inputs: dict[tuple[int, str], tuple[Any, Any, Any]],
) -> tuple[list[dict[str, Any]], float, dict[tuple[int, str, str], int]]:
    rows: list[dict[str, Any]] = []
    checksum = 0.0
    order_rng = np.random.default_rng(ORDER_SEED)
    conditions = [(k, mask_type) for k in K_VALUES for mask_type in MASK_TYPES]
    implementations = {"numpy": numpy_select, "python": python_select}

    gc_was_enabled = gc.isenabled()
    if gc_was_enabled:
        gc.disable()
    try:
        repetitions = choose_repetitions(inputs)
        for round_index in range(ROUNDS):
            order_rng.shuffle(conditions)
            for k, mask_type in conditions:
                mask, a, b = inputs[(k, mask_type)]
                if int(order_rng.integers(0, 2)) == 0:
                    implementation_order = ("numpy", "python")
                else:
                    implementation_order = ("python", "numpy")
                for implementation in implementation_order:
                    reps = repetitions[(k, mask_type, implementation)]
                    elapsed_ns, contribution = time_block(
                        implementations[implementation], reps, mask, a, b
                    )
                    checksum += contribution
                    rows.append(
                        {
                            "k": k,
                            "n": 2**k,
                            "mask_type": mask_type,
                            "implementation": implementation,
                            "round": round_index,
                            "repetitions": reps,
                            "elapsed_ns": elapsed_ns,
                            "ns_per_call": elapsed_ns / reps,
                        }
                    )
            print(f"Completed timing round {round_index + 1}/{ROUNDS}", flush=True)
    finally:
        if gc_was_enabled:
            gc.enable()
        else:
            gc.disable()
    return rows, checksum, repetitions


def write_csv(rows: list[dict[str, Any]]) -> None:
    columns = (
        "k",
        "n",
        "mask_type",
        "implementation",
        "round",
        "repetitions",
        "elapsed_ns",
        "ns_per_call",
    )
    with (WORKSPACE / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def paired_ratios(rows: list[dict[str, Any]]) -> Any:
    lookup = {
        (row["round"], row["mask_type"], row["k"], row["implementation"]): row[
            "ns_per_call"
        ]
        for row in rows
    }
    ratios = np.empty((len(MASK_TYPES), len(K_VALUES), ROUNDS), dtype=np.float64)
    for mask_index, mask_type in enumerate(MASK_TYPES):
        for k_index, k in enumerate(K_VALUES):
            for round_index in range(ROUNDS):
                python_ns = lookup[(round_index, mask_type, k, "python")]
                numpy_ns = lookup[(round_index, mask_type, k, "numpy")]
                ratios[mask_index, k_index, round_index] = python_ns / numpy_ns
    return ratios


def stable_crossover(speedups: Any) -> int | None:
    for index, k in enumerate(K_VALUES):
        if bool(np.all(speedups[index:] >= PRACTICAL_THRESHOLD)):
            return k
    return None


def analyze(ratios: Any) -> dict[str, Any]:
    median_speedups = np.median(ratios, axis=2)
    crossovers = {
        mask_type: stable_crossover(median_speedups[mask_index])
        for mask_index, mask_type in enumerate(MASK_TYPES)
    }

    bootstrap_rng = np.random.default_rng(BOOTSTRAP_SEED)
    sampled_rounds = bootstrap_rng.integers(
        0, ROUNDS, size=(BOOTSTRAP_REPLICATES, ROUNDS)
    )
    bootstrap_speedups = np.empty(
        (BOOTSTRAP_REPLICATES, len(MASK_TYPES), len(K_VALUES)), dtype=np.float64
    )
    for mask_index in range(len(MASK_TYPES)):
        for k_index in range(len(K_VALUES)):
            bootstrap_speedups[:, mask_index, k_index] = np.median(
                ratios[mask_index, k_index, sampled_rounds], axis=1
            )

    bootstrap_lower = np.percentile(bootstrap_speedups, 2.5, axis=0)
    bootstrap_upper = np.percentile(bootstrap_speedups, 97.5, axis=0)
    bootstrap_crossovers = np.full(
        (BOOTSTRAP_REPLICATES, len(MASK_TYPES)), -1, dtype=np.int16
    )
    for replicate in range(BOOTSTRAP_REPLICATES):
        for mask_index in range(len(MASK_TYPES)):
            crossover = stable_crossover(bootstrap_speedups[replicate, mask_index])
            if crossover is not None:
                bootstrap_crossovers[replicate, mask_index] = crossover

    finite = np.all(bootstrap_crossovers >= 0, axis=1)
    finite_fraction = float(np.mean(finite))
    finite_differences = (
        bootstrap_crossovers[finite, MASK_TYPES.index("all_true")]
        - bootstrap_crossovers[finite, MASK_TYPES.index("random_50pct")]
    )
    if finite_differences.size:
        difference_interval = np.percentile(finite_differences, [2.5, 50.0, 97.5])
    else:
        difference_interval = np.asarray([np.nan, np.nan, np.nan])

    random_crossover = crossovers["random_50pct"]
    all_true_crossover = crossovers["all_true"]
    observed_difference = (
        all_true_crossover - random_crossover
        if random_crossover is not None and all_true_crossover is not None
        else None
    )
    supported = bool(
        random_crossover is not None
        and all_true_crossover is not None
        and observed_difference is not None
        and observed_difference >= 1
        and finite_fraction >= 0.95
        and np.isfinite(difference_interval[0])
        and difference_interval[0] >= 1
    )
    return {
        "median_speedups": median_speedups,
        "bootstrap_lower": bootstrap_lower,
        "bootstrap_upper": bootstrap_upper,
        "crossovers": crossovers,
        "observed_difference": observed_difference,
        "difference_interval": difference_interval,
        "finite_fraction": finite_fraction,
        "finite_replicate_count": int(np.count_nonzero(finite)),
        "decision": "supported" if supported else "refuted",
    }


def crossover_text(value: int | None) -> int | str:
    return value if value is not None else "not_observed"


def finite_float_or_text(value: float) -> float | str:
    return float(value) if np.isfinite(value) else "not_observed"


def create_figure(analysis: dict[str, Any]) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures = WORKSPACE / "figures"
    figures.mkdir(exist_ok=True)
    output_path = figures / "crossover_where.png"

    x = np.asarray(K_VALUES)
    colors = {"random_50pct": "#1f77b4", "all_true": "#d62728"}
    labels = {"random_50pct": "Exactly 50% true, shuffled", "all_true": "All true"}
    fig, axis = plt.subplots(figsize=(12.5, 7.5))
    for mask_index, mask_type in enumerate(MASK_TYPES):
        speedups = analysis["median_speedups"][mask_index]
        lower = analysis["bootstrap_lower"][mask_index]
        upper = analysis["bootstrap_upper"][mask_index]
        axis.fill_between(x, lower, upper, color=colors[mask_type], alpha=0.18)
        axis.plot(
            x,
            speedups,
            color=colors[mask_type],
            marker="o",
            markersize=4,
            linewidth=1.8,
            label=labels[mask_type],
        )
        crossover = analysis["crossovers"][mask_type]
        if crossover is not None:
            axis.axvline(
                crossover,
                color=colors[mask_type],
                linestyle="--",
                linewidth=1.3,
                alpha=0.85,
                label=f"{labels[mask_type]} crossover: k={crossover}",
            )

    axis.axhline(1.00, color="#444444", linestyle=":", linewidth=1.2, label="Parity (1.00)")
    axis.axhline(
        PRACTICAL_THRESHOLD,
        color="#111111",
        linestyle="-.",
        linewidth=1.2,
        label="Practical NumPy win (1.05)",
    )
    axis.set_yscale("log")
    axis.set_xticks(x)
    axis.set_xlim(K_VALUES[0] - 0.35, K_VALUES[-1] + 0.35)
    axis.set_xlabel("Power-of-two exponent k")
    axis.set_ylabel("Median paired speedup (Python ns/call ÷ NumPy ns/call, log scale)")
    axis.set_title("np.where vs. plain Python if/else selection on Apple Silicon")
    axis.grid(True, which="both", alpha=0.22)
    axis.legend(loc="upper left", fontsize=8.5, ncol=2)

    secondary = axis.secondary_xaxis("top")
    secondary.set_xticks(x)
    secondary.set_xticklabels([f"{2**k:,}" for k in K_VALUES], rotation=60, ha="left", fontsize=7)
    secondary.set_xlabel("Array size n = 2ᵏ")

    difference = analysis["observed_difference"]
    difference_label = str(difference) if difference is not None else "not observed"
    caption = (
        f"Observed crossover-bin difference D = C_all_true − C_random: {difference_label}. "
        f"Hypothesis {analysis['decision']}. Shading shows 95% round-bootstrap percentile intervals."
    )
    fig.text(0.5, 0.012, caption, ha="center", va="bottom", fontsize=9)
    fig.tight_layout(rect=(0.02, 0.045, 0.99, 0.98))
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def serialize_summary(
    analysis: dict[str, Any],
    environment: dict[str, Any],
    checksum: float,
    total_runtime_seconds: float,
    figure_path: Path,
    repetitions: dict[tuple[int, str, str], int],
) -> dict[str, Any]:
    random_crossover = analysis["crossovers"]["random_50pct"]
    all_true_crossover = analysis["crossovers"]["all_true"]
    interval = analysis["difference_interval"]
    return {
        "crossovers": {
            "random_50pct": {
                "bin": crossover_text(random_crossover),
                "size": 2**random_crossover if random_crossover is not None else "not_observed",
            },
            "all_true": {
                "bin": crossover_text(all_true_crossover),
                "size": 2**all_true_crossover if all_true_crossover is not None else "not_observed",
            },
        },
        "crossover_bin_difference_all_true_minus_random": crossover_text(
            analysis["observed_difference"]
        ),
        "bootstrap": {
            "replicates": BOOTSTRAP_REPLICATES,
            "difference_percentiles_2_5_50_97_5": [
                finite_float_or_text(float(value)) for value in interval
            ],
            "both_crossovers_finite_fraction": analysis["finite_fraction"],
            "both_crossovers_finite_count": analysis["finite_replicate_count"],
        },
        "decision": analysis["decision"],
        "practical_speedup_threshold": PRACTICAL_THRESHOLD,
        "rounds": ROUNDS,
        "checksum": checksum,
        "total_runtime_seconds": total_runtime_seconds,
        "environment": environment,
        "seeds": {
            "data_seed_for_k": "20000 + k",
            "mask_shuffle_seed_for_k": "10000 + k",
            "condition_and_implementation_order": ORDER_SEED,
            "bootstrap": BOOTSTRAP_SEED,
        },
        "repetitions": {
            f"k{k}_{mask_type}_{implementation}": value
            for (k, mask_type, implementation), value in sorted(repetitions.items())
        },
        "figure": str(figure_path.relative_to(WORKSPACE)),
    }


def flat_results(
    analysis: dict[str, Any],
    environment: dict[str, Any],
    checksum: float,
    total_runtime_seconds: float,
) -> dict[str, Any]:
    random_crossover = analysis["crossovers"]["random_50pct"]
    all_true_crossover = analysis["crossovers"]["all_true"]
    interval = analysis["difference_interval"]
    output: dict[str, Any] = {
        "completed": True,
        "decision": analysis["decision"],
        "hypothesis_supported": analysis["decision"] == "supported",
        "crossover_random_bin": crossover_text(random_crossover),
        "crossover_random_size": 2**random_crossover if random_crossover is not None else "not_observed",
        "crossover_all_true_bin": crossover_text(all_true_crossover),
        "crossover_all_true_size": 2**all_true_crossover if all_true_crossover is not None else "not_observed",
        "crossover_bin_difference_all_true_minus_random": crossover_text(
            analysis["observed_difference"]
        ),
        "bootstrap_difference_p2_5": finite_float_or_text(float(interval[0])),
        "bootstrap_difference_p50": finite_float_or_text(float(interval[1])),
        "bootstrap_difference_p97_5": finite_float_or_text(float(interval[2])),
        "bootstrap_both_finite_fraction": analysis["finite_fraction"],
        "bootstrap_both_finite_count": analysis["finite_replicate_count"],
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "rounds": ROUNDS,
        "practical_speedup_threshold": PRACTICAL_THRESHOLD,
        "checksum": checksum,
        "total_runtime_seconds": total_runtime_seconds,
        "machine": environment["machine"],
        "cpu_model": environment["cpu_model"],
        "python_version": environment["python_version"],
        "numpy_version": environment["numpy_version"],
        "matplotlib_version": environment["matplotlib_version"],
        "macos_version": environment["macos_version"],
        "data_seed_base": DATA_SEED_BASE,
        "mask_seed_base": MASK_SEED_BASE,
        "order_seed": ORDER_SEED,
        "bootstrap_seed": BOOTSTRAP_SEED,
    }
    for mask_index, mask_type in enumerate(MASK_TYPES):
        for k_index, k in enumerate(K_VALUES):
            prefix = f"{mask_type}_k{k}"
            output[f"{prefix}_median_speedup"] = float(
                analysis["median_speedups"][mask_index, k_index]
            )
            output[f"{prefix}_bootstrap_p2_5"] = float(
                analysis["bootstrap_lower"][mask_index, k_index]
            )
            output[f"{prefix}_bootstrap_p97_5"] = float(
                analysis["bootstrap_upper"][mask_index, k_index]
            )
    return output


def main() -> None:
    global np
    started_ns = time.perf_counter_ns()
    environment = base_environment()
    if environment["machine"] != "arm64":
        write_failure(
            f"required platform.machine() == 'arm64', observed {environment['machine']!r}",
            environment,
        )
        raise SystemExit(2)
    if sys.version_info[:2] not in ((3, 11), (3, 12)):
        write_failure(
            f"required CPython 3.11 or 3.12, observed {platform.python_version()}",
            environment,
        )
        raise SystemExit(2)

    import numpy as imported_numpy
    import matplotlib

    np = imported_numpy
    environment.update(
        {
            "numpy_version": np.__version__,
            "matplotlib_version": matplotlib.__version__,
        }
    )
    if np.__version__ != "2.1.3" or matplotlib.__version__ != "3.9.2":
        raise RuntimeError(
            "exact dependency versions required: numpy==2.1.3 and matplotlib==3.9.2; "
            f"observed numpy=={np.__version__}, matplotlib=={matplotlib.__version__}"
        )
    write_json(WORKSPACE / "environment.json", environment)

    inputs = make_inputs()
    validate_and_warm(inputs)
    rows, checksum, repetitions = benchmark(inputs)
    if len(rows) != ROUNDS * len(K_VALUES) * len(MASK_TYPES) * 2:
        raise AssertionError(f"unexpected results row count: {len(rows)}")
    write_csv(rows)

    ratios = paired_ratios(rows)
    analysis = analyze(ratios)
    figure_path = create_figure(analysis)
    total_runtime_seconds = (time.perf_counter_ns() - started_ns) / 1_000_000_000
    summary = serialize_summary(
        analysis,
        environment,
        checksum,
        total_runtime_seconds,
        figure_path,
        repetitions,
    )
    write_json(WORKSPACE / "summary.json", summary)
    write_json(
        WORKSPACE / "results.json",
        flat_results(analysis, environment, checksum, total_runtime_seconds),
    )

    random_crossover = analysis["crossovers"]["random_50pct"]
    all_true_crossover = analysis["crossovers"]["all_true"]
    interval = analysis["difference_interval"]
    print(
        "Ran 15 paired rounds of np.where vs the plain Python loop for k=1..20 "
        "under deterministic 50%-true and all-true masks."
    )
    print(
        f"Crossovers: random={crossover_text(random_crossover)} "
        f"(n={2**random_crossover if random_crossover is not None else 'not observed'}), "
        f"all_true={crossover_text(all_true_crossover)} "
        f"(n={2**all_true_crossover if all_true_crossover is not None else 'not observed'})."
    )
    print(
        f"D={crossover_text(analysis['observed_difference'])}; bootstrap D 95% interval="
        f"[{finite_float_or_text(float(interval[0]))}, {finite_float_or_text(float(interval[2]))}], "
        f"both-finite fraction={analysis['finite_fraction']:.4f}."
    )
    print(f"Decision: hypothesis {analysis['decision']}. Runtime: {total_runtime_seconds:.2f} s.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exception:
        environment = base_environment()
        error = f"{type(exception).__name__}: {exception}"
        write_failure(error, environment)
        traceback.print_exc()
        raise SystemExit(1)
