#!/usr/bin/env python3
"""Run the complete deterministic mutation-detection experiment."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .generate import CSV_COLUMNS, MATRIX_FILE, RULES, generate_output_set
from .mutate import MUTATION_CLASSES, apply_mutation
from .validate import validate


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "manifest.schema.json"


def _clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def _validation_outcome(
    name: str,
    kind: str,
    output_set: Path,
    mutation_class: str | None = None,
    target_index: int | None = None,
) -> dict[str, Any]:
    checksum_result = validate(output_set, SCHEMA_PATH, "checksum_only")
    relational_result = validate(output_set, SCHEMA_PATH, "relational")
    return {
        "name": name,
        "kind": kind,
        "mutation_class": mutation_class,
        "mutation_name": MUTATION_CLASSES.get(mutation_class) if mutation_class else None,
        "target_index": target_index,
        "schema_pass": relational_result["schema_pass"],
        "parsing_pass": relational_result["parsing_pass"],
        "checksum_verification_pass": relational_result["checksum_verification_pass"],
        "checksum_only_pass": checksum_result["checksum_only_pass"],
        "relational_pass": relational_result["relational_pass"],
        "failed_rules": relational_result["failed_rules"],
        "elapsed_validation_seconds": (
            checksum_result["elapsed_seconds"] + relational_result["elapsed_seconds"]
        ),
        "checksum_only_validation": checksum_result,
        "relational_validation": relational_result,
    }


def _copy_release(clean_source: Path, release_dir: Path) -> None:
    if release_dir.exists():
        shutil.rmtree(release_dir)
    shutil.copytree(clean_source, release_dir)
    shutil.copytree(
        ROOT / "src",
        release_dir / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for filename in ("manifest.schema.json", "requirements.lock", "Makefile", "README.md"):
        shutil.copy2(ROOT / filename, release_dir / filename)


def _audit_package(release_dir: Path) -> dict[str, bool]:
    canonical_csvs = sorted(CSV_COLUMNS)
    actual_csvs = sorted(path.name for path in release_dir.glob("*.csv"))
    source_files = [
        ROOT / "src" / name
        for name in ("generate.py", "validate.py", "mutate.py", "run_experiment.py")
    ]
    release_source_files = [release_dir / "src" / path.name for path in source_files]
    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    lock_text = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    release_validation = validate(release_dir, SCHEMA_PATH, "relational")
    try:
        release_manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
        versioned_manifest = release_manifest.get("schema_version") == "1.0.0"
    except Exception:
        versioned_manifest = False
    return {
        "repository_executable_source_present": all(
            path.is_file() and os.access(path, os.X_OK) for path in source_files
        ),
        "release_executable_source_present": all(
            path.is_file() and os.access(path, os.X_OK) for path in release_source_files
        ),
        "exactly_four_canonical_release_csvs": actual_csvs == canonical_csvs,
        "release_heatmap_matrix_present": (release_dir / MATRIX_FILE).is_file(),
        "release_manifest_present": (release_dir / "manifest.json").is_file(),
        "release_manifest_schema_valid": release_validation["schema_pass"],
        "release_manifest_versioned": versioned_manifest,
        "release_output_relationally_valid": bool(release_validation["relational_pass"]),
        "environment_lock_present": (ROOT / "requirements.lock").is_file()
        and (release_dir / "requirements.lock").is_file(),
        "required_numpy_pin_present": "numpy==2.1.3" in lock_text,
        "required_matplotlib_pin_present": "matplotlib==3.9.2" in lock_text,
        "readme_present": (ROOT / "README.md").is_file()
        and (release_dir / "README.md").is_file(),
        "readme_documents_make_reproduce": "make reproduce" in readme_text,
        "schema_present": (ROOT / "manifest.schema.json").is_file()
        and (release_dir / "manifest.schema.json").is_file(),
        "makefile_present": (ROOT / "Makefile").is_file()
        and (release_dir / "Makefile").is_file(),
        "clean_00_release_files_byte_identical": all(
            (clean_file := release_dir / filename).read_bytes()
            == (release_dir.parent / "results" / "clean_00" / filename).read_bytes()
            for filename in [*CSV_COLUMNS, MATRIX_FILE, "manifest.json"]
        ),
    }


def _make_figure(
    class_counts: dict[str, int],
    relational_detected: int,
    checksum_detected: int,
    clean_passed: int,
    result_path: Path,
    figure_copy_path: Path,
) -> None:
    class_ids = list(MUTATION_CLASSES)
    left_values = [class_counts[class_id] for class_id in class_ids]
    fig, (left, right) = plt.subplots(1, 2, figsize=(16, 9), dpi=100)

    left_bars = left.bar(class_ids, left_values, color="#2878B5", edgecolor="black")
    left.axhline(4.5, color="#C43C39", linestyle="--", linewidth=2, label="90% target (4.5/5)")
    left.set_ylim(0, 5.6)
    left.set_ylabel("Relationally detected mutants (out of 5)")
    left.set_xlabel("Mutation class")
    left.set_title("Detection by mutation class")
    left.legend(loc="lower right")
    for bar, value in zip(left_bars, left_values):
        left.text(bar.get_x() + bar.get_width() / 2, value + 0.08, f"{value}/5", ha="center")

    right_labels = [
        "Relationally\ndetected mutants",
        "Checksum-only\ndetected mutants",
        "Clean sets\npassed",
    ]
    right_values = [relational_detected, checksum_detected, clean_passed]
    denominators = [40, 40, 20]
    right_bars = right.bar(
        right_labels,
        right_values,
        color=["#2CA02C", "#D62728", "#9467BD"],
        edgecolor="black",
    )
    right.set_ylim(0, 46)
    right.set_ylabel("Count")
    right.set_title("Headline validation outcomes")
    for bar, value, denominator in zip(right_bars, right_values, denominators):
        right.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.8,
            f"{value}/{denominator}",
            ha="center",
            fontweight="bold",
        )

    fig.suptitle("Checksum integrity versus relational validation", fontsize=16)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    result_path.parent.mkdir(parents=True, exist_ok=True)
    figure_copy_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(result_path, dpi=100)
    plt.close(fig)
    shutil.copy2(result_path, figure_copy_path)


def run(output_dir: Path) -> dict[str, Any]:
    experiment_start = time.perf_counter()
    output_dir = output_dir.resolve()
    if output_dir == ROOT or ROOT not in output_dir.parents:
        raise ValueError("output directory must be a child of the repository root")
    _clean_dir(output_dir)

    clean_outcomes: list[dict[str, Any]] = []
    for run_identifier in range(20):
        name = f"clean_{run_identifier:02d}"
        output_set = output_dir / name
        generate_output_set(output_set, run_identifier)
        clean_outcomes.append(_validation_outcome(name, "clean", output_set))

    mutation_base = output_dir / "mutation_base"
    generate_output_set(mutation_base, 100)
    mutant_outcomes: list[dict[str, Any]] = []
    for mutation_class in MUTATION_CLASSES:
        for target_index in range(5):
            name = f"mutant_{mutation_class}_{target_index:02d}"
            output_set = output_dir / name
            shutil.copytree(mutation_base, output_set)
            apply_mutation(output_set, mutation_class, target_index)
            mutant_outcomes.append(
                _validation_outcome(
                    name,
                    "mutant",
                    output_set,
                    mutation_class=mutation_class,
                    target_index=target_index,
                )
            )

    release_dir = ROOT / "release_output"
    _copy_release(output_dir / "clean_00", release_dir)
    package_audit = _audit_package(release_dir)

    mutant_precondition_count = sum(
        outcome["schema_pass"]
        and outcome["parsing_pass"]
        and outcome["checksum_only_pass"]
        for outcome in mutant_outcomes
    )
    relational_detected = sum(
        outcome["checksum_only_pass"] and not outcome["relational_pass"]
        for outcome in mutant_outcomes
    )
    checksum_detected = sum(not outcome["checksum_only_pass"] for outcome in mutant_outcomes)
    clean_passed = sum(
        outcome["schema_pass"]
        and outcome["parsing_pass"]
        and outcome["checksum_only_pass"]
        and outcome["relational_pass"]
        for outcome in clean_outcomes
    )
    class_counts = {
        mutation_class: sum(
            outcome["mutation_class"] == mutation_class
            and outcome["checksum_only_pass"]
            and not outcome["relational_pass"]
            for outcome in mutant_outcomes
        )
        for mutation_class in MUTATION_CLASSES
    }
    rule_counts = Counter(
        rule for outcome in mutant_outcomes for rule in outcome["failed_rules"]
    )
    rule_counts_complete = {rule: rule_counts[rule] for rule in RULES}

    precondition_holds = mutant_precondition_count == 40 and checksum_detected == 0
    if not precondition_holds:
        decision = "invalid"
    elif relational_detected >= 36 and clean_passed == 20:
        decision = "supported"
    else:
        decision = "refuted"

    _make_figure(
        class_counts,
        relational_detected,
        checksum_detected,
        clean_passed,
        output_dir / "detection_summary.png",
        ROOT / "figures" / "detection_summary.png",
    )
    figure = plt.imread(output_dir / "detection_summary.png")
    figure_dimensions_valid = tuple(figure.shape[:2]) == (900, 1600)

    software_versions = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "matplotlib": matplotlib.__version__,
        "jsonschema": importlib.metadata.version("jsonschema"),
        "platform": platform.platform(),
    }
    wall_clock_seconds = time.perf_counter() - experiment_start
    audit_complete = all(package_audit.values()) and figure_dimensions_valid

    detailed = {
        "experiment": "deterministic-synthetic-cross-file-relational-validation",
        "hypothesis_decision": decision,
        "experiment_valid": precondition_holds,
        "metrics": {
            "relational_mutation_detection_count": relational_detected,
            "relational_mutation_detection_rate_percent": relational_detected / 40 * 100,
            "clean_acceptance_count": clean_passed,
            "clean_acceptance_rate_percent": clean_passed / 20 * 100,
            "checksum_only_mutant_detection_count": checksum_detected,
            "mutant_parse_checksum_precondition_count": mutant_precondition_count,
            "support_threshold_count": 36,
            "per_class_detection_counts": class_counts,
            "rule_level_failure_counts": rule_counts_complete,
            "wall_clock_seconds": wall_clock_seconds,
            "wall_clock_under_1800_seconds": wall_clock_seconds < 1800,
        },
        "package_file_audit": {
            **package_audit,
            "detection_figure_is_1600_by_900": figure_dimensions_valid,
            "all_audits_pass": audit_complete,
        },
        "software_versions": software_versions,
        "clean_outcomes": clean_outcomes,
        "mutant_outcomes": mutant_outcomes,
    }
    (output_dir / "results.json").write_text(
        json.dumps(detailed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    flat: dict[str, str | int | float | bool] = {
        "hypothesis_decision": decision,
        "experiment_valid": precondition_holds,
        "relational_mutation_detection_count": relational_detected,
        "relational_mutation_detection_rate_percent": relational_detected / 40 * 100,
        "relational_mutation_support_threshold_count": 36,
        "relational_mutation_support_threshold_percent": 90.0,
        "clean_acceptance_count": clean_passed,
        "clean_acceptance_rate_percent": clean_passed / 20 * 100,
        "checksum_only_mutant_detection_count": checksum_detected,
        "mutant_parse_checksum_precondition_count": mutant_precondition_count,
        "mutant_parse_checksum_precondition_holds": precondition_holds,
        "artifact_completeness_audit_pass": audit_complete,
        "detection_figure_width_pixels": 1600,
        "detection_figure_height_pixels": 900,
        "wall_clock_seconds": wall_clock_seconds,
        "wall_clock_under_1800_seconds": wall_clock_seconds < 1800,
        "python_version": software_versions["python"],
        "numpy_version": software_versions["numpy"],
        "matplotlib_version": software_versions["matplotlib"],
        "jsonschema_version": software_versions["jsonschema"],
    }
    for mutation_class, count in class_counts.items():
        flat[f"{mutation_class.lower()}_{MUTATION_CLASSES[mutation_class]}_detected_count"] = count
    for rule, count in rule_counts_complete.items():
        flat[f"{rule.lower()}_failure_count"] = count
    for audit_name, passed in package_audit.items():
        flat[f"audit_{audit_name}"] = passed
    (ROOT / "results.json").write_text(
        json.dumps(flat, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(
        "Ran 20 clean regenerations and 40 checksum-refreshed mutants; "
        f"relational detections={relational_detected}/40, "
        f"checksum-only detections={checksum_detected}/40, clean accepted={clean_passed}/20, "
        f"decision={decision}, wall-clock={wall_clock_seconds:.3f}s."
    )
    return detailed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args()
    run(args.output)


if __name__ == "__main__":
    main()
