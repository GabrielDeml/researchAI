"""Run the complete canonicalization-separation experiment reproducibly."""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import platform
import shutil
import statistics
import tempfile
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import canonicalizer
import independent_parser
import testgen
import verifier


ROOT = Path(__file__).resolve().parent
CANONICALIZER_IDS = ["C0", *canonicalizer.MUTANT_IDS]
CSV_FIELDS = [
    "canonicalizer_id",
    "seed",
    "policy_id",
    "structural_accept",
    "fixed_point",
    "equivalent",
    "differing_requests",
    "differing_fraction",
    "first_counterexample",
]


def check_static_dependencies() -> bool:
    for filename in ("independent_parser.py", "verifier.py"):
        tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            else:
                continue
            if "canonicalizer" in names:
                raise AssertionError(f"{filename} imports canonicalizer.py")
    return True


def _aggregate(rows: list[dict]) -> dict:
    baseline = [row for row in rows if row["canonicalizer_id"] == "C0"]
    mutants = [row for row in rows if row["canonicalizer_id"] != "C0"]
    aggregate = {
        "baseline_structural_accepted": sum(row["structural_accept"] for row in baseline),
        "baseline_fixed_points": sum(row["fixed_point"] for row in baseline),
        "baseline_equivalent": sum(row["equivalent"] for row in baseline),
        "mutant_structural_accepted": sum(row["structural_accept"] for row in mutants),
        "mutant_fixed_points": sum(row["fixed_point"] for row in mutants),
        "mutant_inequivalent_pairs": sum(not row["equivalent"] for row in mutants),
    }
    structurally_all = 0
    fixed_all = 0
    rejected = 0
    per_mutant = {}
    for mutant_id in canonicalizer.MUTANT_IDS:
        selected = [row for row in mutants if row["canonicalizer_id"] == mutant_id]
        structurally_all += int(all(row["structural_accept"] for row in selected))
        fixed_all += int(all(row["fixed_point"] for row in selected))
        rejected += int(any(not row["equivalent"] for row in selected))
        distances = [row["differing_fraction"] for row in selected]
        per_mutant[mutant_id] = {
            "mean": statistics.fmean(distances),
            "median": statistics.median(distances),
            "maximum": max(distances),
            "nonzero": sum(distance > 0 for distance in distances),
        }
    aggregate.update(
        {
            "mutants_structural_all": structurally_all,
            "mutants_fixed_all": fixed_all,
            "semantically_rejected_mutants": rejected,
            "per_mutant": per_mutant,
        }
    )
    return aggregate


def run_once(run_root: Path) -> dict:
    source_dir = run_root / "sources"
    output_dir = run_root / "outputs"
    source_archives = testgen.generate_corpus(source_dir)

    # Step 11 gate: no canonicalization occurs until all source archives pass.
    for policy_id, archive in source_archives.items():
        try:
            independent_parser.parse_archive(archive)
        except Exception as exc:
            raise AssertionError(f"source archive {policy_id} was rejected") from exc

    output_archives: dict[str, bytes] = {}
    rows = []
    fixed_point_mismatches = []
    for canonicalizer_id in CANONICALIZER_IDS:
        canonicalizer_dir = output_dir / canonicalizer_id
        canonicalizer_dir.mkdir(parents=True, exist_ok=True)
        seed = canonicalizer.MUTANT_SEEDS.get(canonicalizer_id, 0)
        for policy_id, source_archive in source_archives.items():
            output = canonicalizer.canonicalize(source_archive, canonicalizer_id)
            output_archives[f"{canonicalizer_id}/{policy_id}.zip"] = output
            (canonicalizer_dir / f"{policy_id}.zip").write_bytes(output)
            try:
                independent_parser.parse_archive(output)
                structural_accept = True
            except independent_parser.ArchiveValidationError:
                structural_accept = False

            try:
                second_pass = canonicalizer.canonicalize(output, canonicalizer_id)
                fixed_point = output == second_pass
                if not fixed_point:
                    fixed_point_mismatches.append(
                        {
                            "canonicalizer_id": canonicalizer_id,
                            "policy_id": policy_id,
                            "first_pass_sha256": hashlib.sha256(output).hexdigest(),
                            "second_pass_sha256": hashlib.sha256(second_pass).hexdigest(),
                        }
                    )
            except Exception as exc:
                fixed_point = False
                fixed_point_mismatches.append(
                    {
                        "canonicalizer_id": canonicalizer_id,
                        "policy_id": policy_id,
                        "first_pass_sha256": hashlib.sha256(output).hexdigest(),
                        "second_pass_sha256": "ERROR",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

            if structural_accept:
                comparison = verifier.compare_archives(source_archive, output)
            else:
                comparison = {
                    "equivalent": False,
                    "differing_requests": 1024,
                    "differing_fraction": 1.0,
                    "first_counterexample": None,
                }
            rows.append(
                {
                    "canonicalizer_id": canonicalizer_id,
                    "seed": seed,
                    "policy_id": policy_id,
                    "structural_accept": structural_accept,
                    "fixed_point": fixed_point,
                    **comparison,
                }
            )
    aggregate = _aggregate(rows)
    return {
        "source_archives": source_archives,
        "output_archives": output_archives,
        "rows": rows,
        "aggregate": aggregate,
        "fixed_point_mismatches": fixed_point_mismatches,
    }


def _matrix(rows: list[dict]) -> list[tuple]:
    return [
        (
            row["canonicalizer_id"],
            row["policy_id"],
            row["structural_accept"],
            row["fixed_point"],
            row["equivalent"],
            row["differing_requests"],
            row["differing_fraction"],
            row["first_counterexample"],
        )
        for row in rows
    ]


def _write_csv(rows: list[dict]) -> None:
    with (ROOT / "results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            output = dict(row)
            first = output["first_counterexample"]
            output["first_counterexample"] = (
                ""
                if first is None
                else json.dumps(first, ensure_ascii=False, separators=(",", ":"))
            )
            writer.writerow({field: output[field] for field in CSV_FIELDS})


def _plot(aggregate: dict, baseline_correct: bool) -> None:
    figure_dir = ROOT / "figures"
    figure_dir.mkdir(exist_ok=True)
    values = [
        aggregate["mutants_structural_all"],
        aggregate["mutants_fixed_all"],
        aggregate["semantically_rejected_mutants"],
    ]
    labels = ["Structural acceptance\non all policies", "Byte fixed point\non all policies", "Semantic rejection\non at least one policy"]
    colors = ["#4C78A8", "#72B7B2", "#E45756"]
    fig, ax = plt.subplots(figsize=(12, 6), dpi=150)
    bars = ax.bar(range(3), values, width=0.62, color=colors)
    ax.set_ylim(0, 30)
    ax.set_yticks(range(0, 31, 5))
    ax.set_ylabel("Number of deterministic lossy mutants")
    ax.set_xticks(range(3), labels)
    ax.set_title("Canonical archive checks versus exhaustive policy equivalence")
    ax.grid(axis="y", alpha=0.22)
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            min(value + 0.5, 29.4),
            str(value),
            ha="center",
            va="bottom",
            fontsize=13,
            fontweight="bold",
        )
    ax.hlines(27, 1.62, 2.38, colors="#7A1F1F", linestyles="--", linewidth=2)
    ax.text(2.39, 27, " threshold = 27", va="center", fontsize=9, color="#7A1F1F")
    caption = f"Reference canonicalizer C0 {'passed' if baseline_correct else 'failed'} all baseline checks."
    fig.text(0.5, 0.015, caption, ha="center", fontsize=10)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(figure_dir / "key_result.png", dpi=150)
    plt.close(fig)


def _flat_results(
    aggregate: dict,
    determinism: dict,
    elapsed_seconds: float,
    static_dependency_test_passed: bool,
) -> dict:
    baseline_correct = (
        aggregate["baseline_structural_accepted"] == 128
        and aggregate["baseline_fixed_points"] == 128
        and aggregate["baseline_equivalent"] == 128
    )
    conditions = {
        "baseline_correct": baseline_correct,
        "all_mutants_structurally_accepted": aggregate["mutants_structural_all"] == 30,
        "all_mutants_byte_idempotent": aggregate["mutants_fixed_all"] == 30,
        "semantic_rejection_threshold_met": aggregate["semantically_rejected_mutants"] >= 27,
        "repeated_run_identical": all(determinism.values()),
        "runtime_within_30_minutes": elapsed_seconds <= 30 * 60,
        "static_dependency_test_passed": static_dependency_test_passed,
    }
    supported = all(conditions.values())
    failures = [name for name, passed in conditions.items() if not passed]
    result = {
        "hypothesis": "SUPPORTED" if supported else "REFUTED",
        "hypothesis_supported": supported,
        "failed_conditions": ";".join(failures),
        "corpus_seed": testgen.CORPUS_SEED,
        "python_version": platform.python_version(),
        "matplotlib_version": matplotlib.__version__,
        "policy_count": 128,
        "random_policy_count": 112,
        "edge_policy_count": 16,
        "requests_per_policy": 1024,
        "canonicalizer_count": 31,
        "mutant_count": 30,
        "canonicalizer_policy_pair_count": 3968,
        "mutant_policy_pair_count": 3840,
        "baseline_structural_accepted": aggregate["baseline_structural_accepted"],
        "baseline_fixed_points": aggregate["baseline_fixed_points"],
        "baseline_equivalent": aggregate["baseline_equivalent"],
        "baseline_correct": baseline_correct,
        "mutant_structural_accepted": aggregate["mutant_structural_accepted"],
        "mutant_structural_acceptance_rate": aggregate["mutant_structural_accepted"] / 3840,
        "mutants_structural_all": aggregate["mutants_structural_all"],
        "mutant_fixed_points": aggregate["mutant_fixed_points"],
        "mutant_fixed_point_rate": aggregate["mutant_fixed_points"] / 3840,
        "mutants_fixed_all": aggregate["mutants_fixed_all"],
        "semantically_rejected_mutants": aggregate["semantically_rejected_mutants"],
        "semantic_rejection_proportion": aggregate["semantically_rejected_mutants"] / 30,
        "mutant_inequivalent_pairs": aggregate["mutant_inequivalent_pairs"],
        "archive_semantic_inequivalence_rate": aggregate["mutant_inequivalent_pairs"] / 3840,
        "fixed_point_mismatch_count": 3968
        - aggregate["baseline_fixed_points"]
        - aggregate["mutant_fixed_points"],
        "deterministic_source_archives": determinism["source_archives"],
        "deterministic_canonical_outputs": determinism["canonical_outputs"],
        "deterministic_equivalence_matrix": determinism["equivalence_matrix"],
        "deterministic_aggregate_counts": determinism["aggregate_counts"],
        "repeated_run_identical": conditions["repeated_run_identical"],
        "static_dependency_test_passed": static_dependency_test_passed,
        "elapsed_seconds": elapsed_seconds,
        "elapsed_minutes": elapsed_seconds / 60,
        "runtime_within_30_minutes": conditions["runtime_within_30_minutes"],
    }
    for mutant_id in canonicalizer.MUTANT_IDS:
        stats = aggregate["per_mutant"][mutant_id]
        result[f"{mutant_id}_seed"] = canonicalizer.MUTANT_SEEDS[mutant_id]
        result[f"{mutant_id}_behavioral_distance_mean"] = stats["mean"]
        result[f"{mutant_id}_behavioral_distance_median"] = stats["median"]
        result[f"{mutant_id}_behavioral_distance_maximum"] = stats["maximum"]
        result[f"{mutant_id}_behavioral_distance_nonzero_count"] = stats["nonzero"]
    if not all(isinstance(value, (str, int, float, bool)) for value in result.values()):
        raise AssertionError("results.json must remain a flat scalar object")
    return result


def main() -> None:
    static_passed = check_static_dependencies()
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="policy-run1-", dir=ROOT) as first_dir, tempfile.TemporaryDirectory(
        prefix="policy-run2-", dir=ROOT
    ) as second_dir:
        first = run_once(Path(first_dir))
        second = run_once(Path(second_dir))
        determinism = {
            "source_archives": first["source_archives"] == second["source_archives"],
            "canonical_outputs": first["output_archives"] == second["output_archives"],
            "equivalence_matrix": _matrix(first["rows"]) == _matrix(second["rows"]),
            "aggregate_counts": first["aggregate"] == second["aggregate"],
        }
        artifacts = ROOT / "artifacts"
        if artifacts.exists():
            shutil.rmtree(artifacts)
        shutil.copytree(first_dir, artifacts)
        _write_csv(first["rows"])
        (ROOT / "fixed_point_mismatches.json").write_text(
            json.dumps(first["fixed_point_mismatches"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        aggregate = first["aggregate"]
        baseline_correct = (
            aggregate["baseline_structural_accepted"] == 128
            and aggregate["baseline_fixed_points"] == 128
            and aggregate["baseline_equivalent"] == 128
        )
        _plot(aggregate, baseline_correct)
        elapsed = time.perf_counter() - started
        results = _flat_results(aggregate, determinism, elapsed, static_passed)
        (ROOT / "results.json").write_text(
            json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    print(
        "Ran 128 policies through C0 and 30 deterministic mutants twice; "
        f"C0={results['baseline_structural_accepted']}/128 structural, "
        f"{results['baseline_fixed_points']}/128 fixed, "
        f"{results['baseline_equivalent']}/128 equivalent; "
        f"mutants={results['mutant_structural_accepted']}/3840 structural, "
        f"{results['mutant_fixed_points']}/3840 fixed, "
        f"{results['semantically_rejected_mutants']}/30 semantically rejected; "
        f"repeat_identical={results['repeated_run_identical']}; "
        f"elapsed={results['elapsed_minutes']:.3f} min; {results['hypothesis']}."
    )


if __name__ == "__main__":
    main()

