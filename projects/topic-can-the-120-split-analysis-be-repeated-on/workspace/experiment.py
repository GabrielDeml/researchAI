#!/usr/bin/env python3
"""Preregistered synthetic tie-breaking replication experiment.

The preregistration is written and hashed before NumPy is imported or any
experiment arrays are created. All randomness uses the fixed seed formulas in
the protocol.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# These must be set before importing NumPy, SciPy, or scikit-learn.
for _thread_variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ[_thread_variable] = "1"


ROOT = Path(__file__).resolve().parent
IMPLEMENTATION_VERSION = "1.0.0"
PACKAGE_VERSIONS = {
    "python": "3.11",
    "numpy": "1.26.4",
    "pandas": "2.2.2",
    "scikit_learn": "1.4.2",
    "matplotlib": "3.8.4",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_digest(path: Path, digest_path: Path) -> str:
    digest = sha256_file(path)
    digest_path.write_text(digest + "\n", encoding="utf-8")
    return digest


def build_preregistration(timestamp: str) -> dict[str, Any]:
    """Return every fixed constant and analysis rule before array generation."""
    return {
        "topic": "Can the 120-split analysis be repeated on a genuinely untouched replication set under a time-stamped fixed protocol?",
        "hypothesis": "Permutation-invariant lexicographic tie-breaking will be stable while first-encountered-maximum tie-breaking will vary across fixed grid permutations.",
        "implementation_version": IMPLEMENTATION_VERSION,
        "preregistration_utc_timestamp": timestamp,
        "environment": {
            "required_versions": PACKAGE_VERSIONS,
            "thread_environment": {
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
            },
            "single_threaded": True,
        },
        "configurations": {
            "count": 12,
            "ids": [f"C{j:02d}" for j in range(12)],
            "numeric_ids": list(range(12)),
            "prediction_rule": "Configuration Cj predicts binary feature column X[:, j].",
            "optimizer_A_numeric_ids": list(range(0, 6)),
            "optimizer_B_numeric_ids": list(range(6, 12)),
            "reported_winner_rule": "The optimizer label of the selected configuration.",
            "total_order": "Ascending numeric configuration ID.",
        },
        "grid_permutations": {
            "count": 25,
            "seed_formula": "400000 + k for k=0,...,24",
            "generator": "numpy.random.default_rng(seed).permutation(12)",
            "reuse_rule": "Generate once, save before data generation, and reuse for all datasets.",
            "output": "grid_permutations.csv",
        },
        "tuning_data": {
            "dataset_count": 60,
            "dataset_ids": "d=0,...,59",
            "n": 400,
            "class_0_count": 200,
            "class_1_count": 200,
            "observation_permutation_seed_formula": "100000 + d",
            "maximum_set_formula": "T_d={(d+0) mod 12,(d+1) mod 12,(d+6) mod 12,(d+7) mod 12}",
            "error_seed_formula": "110000 + 100*d + j",
            "maximum_configuration_errors_per_class": 50,
            "other_configuration_errors_per_class": 60,
            "maximum_balanced_accuracy": 0.75,
            "other_balanced_accuracy": 0.70,
            "prediction_construction": "X[:,j] = y XOR error_indicator; choose errors independently without replacement within each class.",
            "fit_model": False,
            "score_rounding": False,
        },
        "tuning_score": {
            "metric": "Balanced accuracy",
            "definition": "Unweighted arithmetic mean of sensitivity and specificity.",
            "comparison_precision": "Unrounded float64 exact comparisons.",
        },
        "regime_check": {
            "timing": "Before any replication outcomes are generated.",
            "requirements": [
                "Exactly four configurations tie at the exact maximum 0.75 for every dataset.",
                "All remaining configurations equal exactly 0.70.",
                "The observed maximum set equals T_d.",
            ],
            "failure_rule": "Any failure invalidates the implementation and cannot alter the protocol.",
            "output": "regime_check.csv",
        },
        "selection_rules": {
            "total_order": "Find the exact maximum and select the tied configuration with the smallest numeric ID, independent of encounter order.",
            "first_encountered": "Scan in permutation order; initialize the first configuration; replace only when score is strictly greater; never replace on equality.",
            "cases": 1500,
        },
        "selection_freeze": {
            "shape": "60 datasets x 25 permutations",
            "outputs": ["selections.csv", "selections.sha256"],
            "rule": "Freeze and hash every selection before calling the replication-generation function; verify its call count is zero at freeze time.",
        },
        "replication_data": {
            "timing": "Generate only after selections.csv is frozen and hashed.",
            "dataset_count": 60,
            "n": 1200,
            "class_0_count": 600,
            "class_1_count": 600,
            "observation_permutation_seed_formula": "200000 + d",
            "q_formula": "q=(j+5*d) mod 12",
            "target_balanced_accuracy_formula": "p=0.55+0.01*q",
            "correct_per_class_formula": "330+6*q",
            "errors_per_class_formula": "600-(330+6*q)",
            "error_seed_formula": "210000 + 100*d + j",
            "prediction_construction": "X_rep[:,j] = y_rep XOR error_indicator; choose errors independently without replacement within each class.",
            "full_balanced_accuracy_min": 0.55,
            "full_balanced_accuracy_max": 0.66,
        },
        "replication_splits": {
            "splitter": "sklearn.model_selection.StratifiedShuffleSplit",
            "n_splits": 120,
            "test_size": 0.25,
            "random_state_formula": "300000 + d",
            "test_n": 300,
            "test_class_0_count": 150,
            "test_class_1_count": 150,
            "sharing_rule": "Apply every configuration to the same test indices within each dataset.",
            "training_indices_used": False,
            "final_estimate": "Arithmetic mean of the 120 test balanced accuracies.",
        },
        "reporting": {
            "unit": "rule x dataset x permutation",
            "fields": ["selected configuration", "optimizer label", "final 120-split estimate"],
            "comparison_values": "Unrounded float64",
            "display_rounding_decimal_places": 4,
        },
        "dataset_definitions": {
            "total_order_invariance": "One unique total-order selected ID across 25 permutations and final-estimate max-minus-min range <=1e-12.",
            "total_order_range_tolerance": 1e-12,
            "first_rule_configuration_variation": "More than one unique first-rule selected ID across 25 permutations.",
            "reported_winner_change": "At least one first-rule optimizer label differs from the total-order optimizer label.",
            "rope": [-0.005, 0.005],
            "material_estimate_change": "At least one first-rule estimate has absolute difference from the total-order estimate >0.005.",
        },
        "primary_decision": {
            "total_order_invariant_required": 60,
            "first_rule_configuration_varying_minimum": 40,
            "reported_winner_change_minimum": 15,
            "supported_if_and_only_if": "All three thresholds are satisfied; failure of any one threshold yields REFUTED.",
            "material_change_role": "Prespecified corroborating result only.",
        },
        "bootstrap": {
            "unit": "dataset",
            "seed": 987654,
            "replicates": 10000,
            "sample_size_per_replicate": 60,
            "sampling": "Dataset IDs sampled with replacement.",
            "statistics": [
                "first-rule configuration variation proportion",
                "reported-winner change proportion",
                "material-estimate change proportion",
            ],
            "interval": "Percentile 95% interval",
            "quantiles": [0.025, 0.975],
            "quantile_method": "linear",
            "role": "Descriptive; does not replace fixed-count decision thresholds.",
        },
        "secondary_analyses": {
            "distinct_first_rule_selections_per_dataset": True,
            "within_dataset_first_rule_estimate_range": True,
            "case_fractions_denominator": 1500,
            "case_fraction_events": [
                "different selected ID from total order",
                "different optimizer label from total order",
                "absolute estimate difference >0.005 from total order",
            ],
            "absolute_estimate_change_sensitivity_thresholds": [0.0, 0.0025, 0.005, 0.01],
            "decision_role": "Cannot change the primary conclusion.",
        },
        "outputs": {
            "tables": ["results.csv", "dataset_summary.csv", "bootstrap.csv"],
            "flat_metrics": "results.json",
            "figure": "figures/tie_breaking_results.png",
            "figure_dpi": 180,
            "figure_panels": [
                "60-by-25 heatmap of first-rule selected IDs using distinct optimizer-A and optimizer-B palettes",
                "bar chart of the four dataset counts with reference lines at 60, 40, and 15",
            ],
        },
        "stdout_rule": "Print the three primary counts and exactly one final SUPPORTED or REFUTED label, plus a concise run summary.",
        "sample_size_reduction_rule": "No reductions are permitted in this run because the fixed protocol fits the wall-clock budget.",
    }


def optimizer_label(config_id: int) -> str:
    return "optimizer-A" if config_id < 6 else "optimizer-B"


def config_name(config_id: int) -> str:
    return f"C{config_id:02d}"


def balanced_accuracy(y_true: Any, predictions: Any, np: Any) -> float:
    class_zero = y_true == 0
    class_one = y_true == 1
    specificity = np.mean(predictions[class_zero] == 0, dtype=np.float64)
    sensitivity = np.mean(predictions[class_one] == 1, dtype=np.float64)
    return float((specificity + sensitivity) / np.float64(2.0))


def generate_tuning_dataset(dataset_id: int, np: Any) -> tuple[Any, Any, set[int]]:
    y = np.concatenate((np.zeros(200, dtype=np.int8), np.ones(200, dtype=np.int8)))
    y = np.random.default_rng(100000 + dataset_id).permutation(y)
    maximum_set = {
        (dataset_id + 0) % 12,
        (dataset_id + 1) % 12,
        (dataset_id + 6) % 12,
        (dataset_id + 7) % 12,
    }
    x = np.empty((400, 12), dtype=np.int8)
    for config_id in range(12):
        error_count = 50 if config_id in maximum_set else 60
        rng = np.random.default_rng(110000 + 100 * dataset_id + config_id)
        error_indicator = np.zeros(400, dtype=np.int8)
        for class_value in (0, 1):
            class_positions = np.flatnonzero(y == class_value)
            error_positions = rng.choice(class_positions, size=error_count, replace=False)
            error_indicator[error_positions] = 1
        x[:, config_id] = np.bitwise_xor(y, error_indicator)
    return x, y, maximum_set


def generate_replication_dataset(
    dataset_id: int, np: Any, replication_state: dict[str, int]
) -> tuple[Any, Any]:
    replication_state["calls"] += 1
    y = np.concatenate((np.zeros(600, dtype=np.int8), np.ones(600, dtype=np.int8)))
    y = np.random.default_rng(200000 + dataset_id).permutation(y)
    x = np.empty((1200, 12), dtype=np.int8)
    for config_id in range(12):
        q = (config_id + 5 * dataset_id) % 12
        errors_per_class = 600 - (330 + 6 * q)
        rng = np.random.default_rng(210000 + 100 * dataset_id + config_id)
        error_indicator = np.zeros(1200, dtype=np.int8)
        for class_value in (0, 1):
            class_positions = np.flatnonzero(y == class_value)
            error_positions = rng.choice(
                class_positions, size=errors_per_class, replace=False
            )
            error_indicator[error_positions] = 1
        x[:, config_id] = np.bitwise_xor(y, error_indicator)
    return x, y


def select_total_order(scores: Any, permutation: Any, np: Any) -> int:
    exact_maximum = np.max(scores)
    tied = [int(config_id) for config_id in permutation if scores[config_id] == exact_maximum]
    return min(tied)


def select_first_encountered(scores: Any, permutation: Any) -> int:
    incumbent = int(permutation[0])
    incumbent_score = scores[incumbent]
    for config_value in permutation[1:]:
        config_id = int(config_value)
        if scores[config_id] > incumbent_score:
            incumbent = config_id
            incumbent_score = scores[config_id]
    return incumbent


def assert_flat_scalar_json(payload: dict[str, Any]) -> None:
    scalar_types = (str, int, float, bool)
    if not all(isinstance(value, scalar_types) for value in payload.values()):
        invalid = {key: type(value).__name__ for key, value in payload.items() if not isinstance(value, scalar_types)}
        raise AssertionError(f"results.json is not flat and scalar: {invalid}")


def run_experiment(preregistration_digest: str, preregistration_timestamp: str) -> None:
    # Deliberately imported only after preregistration.json and its digest exist.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import sklearn
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from sklearn.model_selection import StratifiedShuffleSplit

    actual_versions = {
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
        "matplotlib": matplotlib.__version__,
    }
    expected_runtime_versions = {key: value for key, value in PACKAGE_VERSIONS.items() if key != "python"}
    if actual_versions != expected_runtime_versions:
        raise RuntimeError(f"Package version mismatch: {actual_versions} != {expected_runtime_versions}")
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError(f"Python 3.11 required, got {platform.python_version()}")
    for variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        if os.environ.get(variable) != "1":
            raise RuntimeError(f"{variable} must equal 1")

    # Generate and save the one shared grid-permutation matrix before any data.
    grid_permutations = np.stack(
        [np.random.default_rng(400000 + k).permutation(12) for k in range(25)]
    ).astype(np.int64, copy=False)
    if grid_permutations.shape != (25, 12):
        raise AssertionError("Grid-permutation matrix has the wrong shape")
    for row in grid_permutations:
        if not np.array_equal(np.sort(row), np.arange(12)):
            raise AssertionError("A grid-permutation row is invalid")
    permutation_columns = [f"position_{position:02d}" for position in range(12)]
    pd.DataFrame(grid_permutations, columns=permutation_columns).rename_axis(
        "permutation_id"
    ).to_csv(ROOT / "grid_permutations.csv")

    # Tuning generation and the implementation-invalidating regime check.
    tuning_scores = np.empty((60, 12), dtype=np.float64)
    regime_rows: list[dict[str, Any]] = []
    for dataset_id in range(60):
        x_tune, y_tune, expected_maximum_set = generate_tuning_dataset(dataset_id, np)
        scores = np.array(
            [balanced_accuracy(y_tune, x_tune[:, config_id], np) for config_id in range(12)],
            dtype=np.float64,
        )
        tuning_scores[dataset_id] = scores
        exact_maximum = float(np.max(scores))
        observed_maximum_set = set(np.flatnonzero(scores == exact_maximum).tolist())
        exact_four = len(observed_maximum_set) == 4
        maximum_exact = exact_maximum == 0.75
        maximum_set_exact = observed_maximum_set == expected_maximum_set
        others_exact = all(scores[j] == 0.70 for j in range(12) if j not in expected_maximum_set)
        passed = exact_four and maximum_exact and maximum_set_exact and others_exact
        row: dict[str, Any] = {
            "dataset_id": dataset_id,
            "expected_maximum_ids": "|".join(map(str, sorted(expected_maximum_set))),
            "observed_maximum_ids": "|".join(map(str, sorted(observed_maximum_set))),
            "maximum_score": exact_maximum,
            "exactly_four_maxima": exact_four,
            "maximum_equals_0_75": maximum_exact,
            "maximum_set_matches": maximum_set_exact,
            "all_others_equal_0_70": others_exact,
            "passed": passed,
        }
        row.update({f"score_C{j:02d}": float(scores[j]) for j in range(12)})
        regime_rows.append(row)
        if not passed:
            raise RuntimeError(f"Implementation-invalidating regime-check failure for dataset {dataset_id}: {row}")
    regime_check = pd.DataFrame(regime_rows)
    regime_check.to_csv(ROOT / "regime_check.csv", index=False)
    if not bool(regime_check["passed"].all()):
        raise AssertionError("Not all regime checks passed")

    # Make all selections using tuning scores, then freeze and hash them.
    selection_rows: list[dict[str, Any]] = []
    total_selected = np.empty((60, 25), dtype=np.int64)
    first_selected = np.empty((60, 25), dtype=np.int64)
    for dataset_id in range(60):
        for permutation_id, permutation in enumerate(grid_permutations):
            total_id = select_total_order(tuning_scores[dataset_id], permutation, np)
            first_id = select_first_encountered(tuning_scores[dataset_id], permutation)
            total_selected[dataset_id, permutation_id] = total_id
            first_selected[dataset_id, permutation_id] = first_id
            selection_rows.append(
                {
                    "dataset_id": dataset_id,
                    "permutation_id": permutation_id,
                    "permutation_order": "|".join(map(str, permutation.tolist())),
                    "exact_tuning_maximum": float(np.max(tuning_scores[dataset_id])),
                    "total_order_selected_id": total_id,
                    "total_order_selected_config": config_name(total_id),
                    "total_order_optimizer_label": optimizer_label(total_id),
                    "first_rule_selected_id": first_id,
                    "first_rule_selected_config": config_name(first_id),
                    "first_rule_optimizer_label": optimizer_label(first_id),
                }
            )
    selections = pd.DataFrame(selection_rows)
    if len(selections) != 1500:
        raise AssertionError("Selections must have exactly 1500 rows")
    selections_path = ROOT / "selections.csv"
    selections.to_csv(selections_path, index=False)
    selections_digest = write_digest(selections_path, ROOT / "selections.sha256")

    replication_state = {"calls": 0}
    if replication_state["calls"] != 0:
        raise AssertionError("Replication generation occurred before selection freeze")
    freeze_manifest = {
        "selection_rows": int(len(selections)),
        "selections_sha256": selections_digest,
        "selections_frozen_utc_timestamp": utc_now(),
        "replication_generation_calls_before_freeze": replication_state["calls"],
        "verified_no_replication_generation_before_freeze": True,
    }
    (ROOT / "freeze_manifest.json").write_text(
        json.dumps(freeze_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # Only now generate replication outcomes and shared fixed splits.
    final_estimates = np.empty((60, 12), dtype=np.float64)
    full_replication_scores = np.empty((60, 12), dtype=np.float64)
    for dataset_id in range(60):
        x_rep, y_rep = generate_replication_dataset(dataset_id, np, replication_state)
        full_scores = np.array(
            [balanced_accuracy(y_rep, x_rep[:, config_id], np) for config_id in range(12)],
            dtype=np.float64,
        )
        expected_full_scores = np.array(
            [0.55 + 0.01 * ((config_id + 5 * dataset_id) % 12) for config_id in range(12)],
            dtype=np.float64,
        )
        if not np.allclose(full_scores, expected_full_scores, rtol=0.0, atol=1e-15):
            raise AssertionError(f"Full replication scores are wrong for dataset {dataset_id}")
        full_replication_scores[dataset_id] = full_scores

        splitter = StratifiedShuffleSplit(
            n_splits=120, test_size=0.25, random_state=300000 + dataset_id
        )
        split_scores = np.empty((120, 12), dtype=np.float64)
        split_counter = 0
        splitter_input = np.zeros((1200, 1), dtype=np.int8)
        for split_id, (_train_indices, test_indices) in enumerate(splitter.split(splitter_input, y_rep)):
            if len(test_indices) != 300:
                raise AssertionError("Replication test split does not contain 300 observations")
            test_y = y_rep[test_indices]
            if np.count_nonzero(test_y == 0) != 150 or np.count_nonzero(test_y == 1) != 150:
                raise AssertionError("Replication test split is not balanced 150/150")
            for config_id in range(12):
                split_scores[split_id, config_id] = balanced_accuracy(
                    test_y, x_rep[test_indices, config_id], np
                )
            split_counter += 1
        if split_counter != 120:
            raise AssertionError("Replication did not produce exactly 120 splits")
        final_estimates[dataset_id] = np.mean(split_scores, axis=0, dtype=np.float64)
    if replication_state["calls"] != 60:
        raise AssertionError("Replication generation function must be called exactly 60 times")

    # Rule x dataset x permutation result table.
    result_rows: list[dict[str, Any]] = []
    for dataset_id in range(60):
        for permutation_id in range(25):
            for rule, selected_matrix in (
                ("total_order", total_selected),
                ("first_encountered", first_selected),
            ):
                selected_id = int(selected_matrix[dataset_id, permutation_id])
                result_rows.append(
                    {
                        "dataset_id": dataset_id,
                        "permutation_id": permutation_id,
                        "rule": rule,
                        "selected_config_id": selected_id,
                        "selected_configuration": config_name(selected_id),
                        "optimizer_label": optimizer_label(selected_id),
                        "final_120_split_estimate": float(final_estimates[dataset_id, selected_id]),
                    }
                )
    results_table = pd.DataFrame(result_rows)
    if len(results_table) != 3000:
        raise AssertionError("results.csv must have exactly 3000 rows")
    results_table.to_csv(ROOT / "results.csv", index=False)

    # Dataset-level primary definitions and secondary analyses.
    summary_rows: list[dict[str, Any]] = []
    case_absolute_changes = np.empty((60, 25), dtype=np.float64)
    threshold_keys = {0.0: "0", 0.0025: "0_0025", 0.005: "0_005", 0.01: "0_01"}
    for dataset_id in range(60):
        total_ids = total_selected[dataset_id]
        first_ids = first_selected[dataset_id]
        total_values = final_estimates[dataset_id, total_ids]
        first_values = final_estimates[dataset_id, first_ids]
        total_unique_ids = np.unique(total_ids)
        first_unique_ids = np.unique(first_ids)
        total_range = float(np.max(total_values) - np.min(total_values))
        first_range = float(np.max(first_values) - np.min(first_values))
        total_invariant = len(total_unique_ids) == 1 and total_range <= 1e-12
        configuration_variation = len(first_unique_ids) > 1
        total_optimizer = optimizer_label(int(total_ids[0]))
        first_labels = np.array([optimizer_label(int(value)) for value in first_ids], dtype=object)
        winner_change_mask = first_labels != total_optimizer
        absolute_changes = np.abs(first_values - total_values)
        case_absolute_changes[dataset_id] = absolute_changes
        material_change_mask = absolute_changes > 0.005
        summary_row: dict[str, Any] = {
            "dataset_id": dataset_id,
            "total_order_selected_id": int(total_ids[0]),
            "total_order_selected_config": config_name(int(total_ids[0])),
            "total_order_optimizer_label": total_optimizer,
            "total_order_final_estimate": float(total_values[0]),
            "total_order_unique_selected_ids": int(len(total_unique_ids)),
            "total_order_estimate_range": total_range,
            "total_order_invariant": bool(total_invariant),
            "first_rule_distinct_selected_ids": "|".join(map(str, first_unique_ids.tolist())),
            "first_rule_unique_selected_id_count": int(len(first_unique_ids)),
            "first_rule_configuration_variation": bool(configuration_variation),
            "first_rule_estimate_min": float(np.min(first_values)),
            "first_rule_estimate_max": float(np.max(first_values)),
            "first_rule_estimate_range": first_range,
            "reported_winner_change": bool(np.any(winner_change_mask)),
            "material_estimate_change": bool(np.any(material_change_mask)),
            "different_id_case_count": int(np.count_nonzero(first_ids != total_ids)),
            "different_optimizer_case_count": int(np.count_nonzero(winner_change_mask)),
            "material_estimate_case_count": int(np.count_nonzero(material_change_mask)),
        }
        for threshold, key_suffix in threshold_keys.items():
            summary_row[f"any_absolute_estimate_change_gt_{key_suffix}"] = bool(
                np.any(absolute_changes > threshold)
            )
            summary_row[f"case_count_absolute_estimate_change_gt_{key_suffix}"] = int(
                np.count_nonzero(absolute_changes > threshold)
            )
        summary_rows.append(summary_row)
    dataset_summary = pd.DataFrame(summary_rows)
    dataset_summary.to_csv(ROOT / "dataset_summary.csv", index=False)

    total_invariant_flags = dataset_summary["total_order_invariant"].to_numpy(dtype=bool)
    variation_flags = dataset_summary["first_rule_configuration_variation"].to_numpy(dtype=bool)
    winner_change_flags = dataset_summary["reported_winner_change"].to_numpy(dtype=bool)
    material_change_flags = dataset_summary["material_estimate_change"].to_numpy(dtype=bool)
    total_invariant_count = int(np.count_nonzero(total_invariant_flags))
    variation_count = int(np.count_nonzero(variation_flags))
    winner_change_count = int(np.count_nonzero(winner_change_flags))
    material_change_count = int(np.count_nonzero(material_change_flags))
    hypothesis_supported = (
        total_invariant_count == 60 and variation_count >= 40 and winner_change_count >= 15
    )
    final_label = "SUPPORTED" if hypothesis_supported else "REFUTED"

    # Fixed dataset-level bootstrap.
    bootstrap_rng = np.random.default_rng(987654)
    bootstrap_indices = bootstrap_rng.integers(0, 60, size=(10000, 60))
    bootstrap_variation = np.mean(variation_flags[bootstrap_indices], axis=1, dtype=np.float64)
    bootstrap_winner = np.mean(winner_change_flags[bootstrap_indices], axis=1, dtype=np.float64)
    bootstrap_material = np.mean(material_change_flags[bootstrap_indices], axis=1, dtype=np.float64)
    bootstrap = pd.DataFrame(
        {
            "bootstrap_replicate": np.arange(10000, dtype=np.int64),
            "first_rule_configuration_variation_proportion": bootstrap_variation,
            "reported_winner_change_proportion": bootstrap_winner,
            "material_estimate_change_proportion": bootstrap_material,
        }
    )
    bootstrap.to_csv(ROOT / "bootstrap.csv", index=False)

    def percentile_interval(values: Any) -> tuple[float, float]:
        interval = np.quantile(values, [0.025, 0.975], method="linear")
        return float(interval[0]), float(interval[1])

    variation_ci = percentile_interval(bootstrap_variation)
    winner_ci = percentile_interval(bootstrap_winner)
    material_ci = percentile_interval(bootstrap_material)

    first_estimate_ranges = dataset_summary["first_rule_estimate_range"].to_numpy(dtype=np.float64)
    range_quartiles = np.quantile(first_estimate_ranges, [0.25, 0.50, 0.75], method="linear")
    distinct_counts = dataset_summary["first_rule_unique_selected_id_count"].to_numpy(dtype=np.int64)
    different_id_cases = int(np.count_nonzero(first_selected != total_selected))
    total_optimizer_matrix = np.array(
        [[optimizer_label(int(value)) for value in row] for row in total_selected], dtype=object
    )
    first_optimizer_matrix = np.array(
        [[optimizer_label(int(value)) for value in row] for row in first_selected], dtype=object
    )
    different_optimizer_cases = int(np.count_nonzero(first_optimizer_matrix != total_optimizer_matrix))
    material_cases = int(np.count_nonzero(case_absolute_changes > 0.005))

    flat_metrics: dict[str, Any] = {
        "implementation_version": IMPLEMENTATION_VERSION,
        "preregistration_utc_timestamp": preregistration_timestamp,
        "preregistration_sha256": preregistration_digest,
        "selections_sha256": selections_digest,
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "pandas_version": pd.__version__,
        "scikit_learn_version": sklearn.__version__,
        "matplotlib_version": matplotlib.__version__,
        "single_thread_environment_verified": True,
        "replication_calls_before_selection_freeze": int(freeze_manifest["replication_generation_calls_before_freeze"]),
        "replication_generation_calls_total": int(replication_state["calls"]),
        "n_datasets": 60,
        "n_grid_permutations": 25,
        "n_replication_splits_per_dataset": 120,
        "n_dataset_permutation_cases": 1500,
        "n_bootstrap_replicates": 10000,
        "regime_check_passed_datasets": int(regime_check["passed"].sum()),
        "total_order_invariant_datasets": total_invariant_count,
        "total_order_invariant_required": 60,
        "first_rule_configuration_varying_datasets": variation_count,
        "first_rule_configuration_varying_required_minimum": 40,
        "reported_winner_change_datasets": winner_change_count,
        "reported_winner_change_required_minimum": 15,
        "material_estimate_change_datasets": material_change_count,
        "hypothesis_supported": bool(hypothesis_supported),
        "final_label": final_label,
        "different_id_cases": different_id_cases,
        "different_id_case_fraction": float(different_id_cases / 1500),
        "different_optimizer_label_cases": different_optimizer_cases,
        "different_optimizer_label_case_fraction": float(different_optimizer_cases / 1500),
        "material_estimate_change_cases": material_cases,
        "material_estimate_change_case_fraction": float(material_cases / 1500),
        "first_rule_distinct_selection_count_min": int(np.min(distinct_counts)),
        "first_rule_distinct_selection_count_median": float(np.median(distinct_counts)),
        "first_rule_distinct_selection_count_max": int(np.max(distinct_counts)),
        "within_dataset_estimate_range_q1": float(range_quartiles[0]),
        "within_dataset_estimate_range_median": float(range_quartiles[1]),
        "within_dataset_estimate_range_q3": float(range_quartiles[2]),
        "within_dataset_estimate_range_iqr": float(range_quartiles[2] - range_quartiles[0]),
        "within_dataset_estimate_range_max": float(np.max(first_estimate_ranges)),
        "bootstrap_configuration_variation_proportion_ci95_lower": variation_ci[0],
        "bootstrap_configuration_variation_proportion_ci95_upper": variation_ci[1],
        "bootstrap_reported_winner_change_proportion_ci95_lower": winner_ci[0],
        "bootstrap_reported_winner_change_proportion_ci95_upper": winner_ci[1],
        "bootstrap_material_estimate_change_proportion_ci95_lower": material_ci[0],
        "bootstrap_material_estimate_change_proportion_ci95_upper": material_ci[1],
    }
    for threshold, key_suffix in threshold_keys.items():
        flat_metrics[f"sensitivity_case_count_abs_estimate_change_gt_{key_suffix}"] = int(
            np.count_nonzero(case_absolute_changes > threshold)
        )
        flat_metrics[f"sensitivity_dataset_count_any_abs_estimate_change_gt_{key_suffix}"] = int(
            dataset_summary[f"any_absolute_estimate_change_gt_{key_suffix}"].sum()
        )
    assert_flat_scalar_json(flat_metrics)
    (ROOT / "results.json").write_text(
        json.dumps(flat_metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # Prespecified two-panel figure.
    figure_dir = ROOT / "figures"
    figure_dir.mkdir(exist_ok=True)
    optimizer_a_colors = plt.cm.Blues(np.linspace(0.35, 0.90, 6))
    optimizer_b_colors = plt.cm.Oranges(np.linspace(0.35, 0.90, 6))
    configuration_cmap = ListedColormap(np.vstack((optimizer_a_colors, optimizer_b_colors)))
    configuration_norm = BoundaryNorm(np.arange(-0.5, 12.5, 1.0), configuration_cmap.N)
    figure, (heatmap_axis, count_axis) = plt.subplots(
        1, 2, figsize=(15.0, 8.5), gridspec_kw={"width_ratios": [2.2, 1.0]}
    )
    heatmap = heatmap_axis.imshow(
        first_selected,
        aspect="auto",
        interpolation="nearest",
        cmap=configuration_cmap,
        norm=configuration_norm,
    )
    heatmap_axis.set_title("First-encountered selected configuration IDs")
    heatmap_axis.set_xlabel("Fixed grid permutation")
    heatmap_axis.set_ylabel("Untouched replication dataset")
    heatmap_axis.set_xticks(np.arange(0, 25, 2))
    heatmap_axis.set_yticks(np.arange(0, 60, 5))
    colorbar = figure.colorbar(heatmap, ax=heatmap_axis, ticks=np.arange(12), pad=0.02)
    colorbar.ax.set_yticklabels([config_name(j) for j in range(12)])
    colorbar.set_label("Blue: optimizer-A; orange: optimizer-B")

    count_labels = ["Total-order\ninvariant", "First-rule\nvaried", "Winner\nchanged", "Material\nchange"]
    count_values = [total_invariant_count, variation_count, winner_change_count, material_change_count]
    bars = count_axis.bar(
        np.arange(4), count_values, color=["#4C78A8", "#72B7B2", "#F58518", "#E45756"]
    )
    count_axis.set_title("Dataset-level preregistered counts")
    count_axis.set_ylabel("Datasets (out of 60)")
    count_axis.set_xticks(np.arange(4), count_labels)
    count_axis.set_ylim(0, 66)
    count_axis.axhline(60, color="#4C78A8", linestyle="--", linewidth=1.2, label="Required: 60")
    count_axis.axhline(40, color="#72B7B2", linestyle="--", linewidth=1.2, label="Required: 40")
    count_axis.axhline(15, color="#F58518", linestyle="--", linewidth=1.2, label="Required: 15")
    count_axis.legend(loc="lower right", frameon=True)
    for bar, value in zip(bars, count_values):
        count_axis.text(
            bar.get_x() + bar.get_width() / 2,
            value + 1.0,
            str(value),
            ha="center",
            va="bottom",
            fontsize=10,
        )
    figure.suptitle("Tie-breaking stability on preregistered untouched replication data", fontsize=14)
    figure.tight_layout()
    figure.savefig(figure_dir / "tie_breaking_results.png", dpi=180, bbox_inches="tight")
    plt.close(figure)

    # Read-back validation of every required output and both hashes.
    required_paths = [
        ROOT / "preregistration.json",
        ROOT / "preregistration.sha256",
        ROOT / "grid_permutations.csv",
        ROOT / "regime_check.csv",
        ROOT / "selections.csv",
        ROOT / "selections.sha256",
        ROOT / "freeze_manifest.json",
        ROOT / "results.csv",
        ROOT / "dataset_summary.csv",
        ROOT / "bootstrap.csv",
        ROOT / "results.json",
        figure_dir / "tie_breaking_results.png",
    ]
    missing = [str(path) for path in required_paths if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise AssertionError(f"Required outputs are missing or empty: {missing}")
    if sha256_file(ROOT / "preregistration.json") != (ROOT / "preregistration.sha256").read_text(encoding="utf-8").strip():
        raise AssertionError("Preregistration digest verification failed")
    if sha256_file(ROOT / "selections.csv") != (ROOT / "selections.sha256").read_text(encoding="utf-8").strip():
        raise AssertionError("Selection digest verification failed")
    loaded_metrics = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))
    assert_flat_scalar_json(loaded_metrics)
    if pd.read_csv(ROOT / "results.csv").shape[0] != 3000:
        raise AssertionError("results.csv read-back row count failed")
    if pd.read_csv(ROOT / "dataset_summary.csv").shape[0] != 60:
        raise AssertionError("dataset_summary.csv read-back row count failed")
    if pd.read_csv(ROOT / "bootstrap.csv").shape[0] != 10000:
        raise AssertionError("bootstrap.csv read-back row count failed")

    print("Ran 60 datasets x 25 fixed permutations x 120 shared replication splits; all artifact checks passed.")
    print(f"Total-order invariant datasets: {total_invariant_count}/60 (required 60)")
    print(f"First-rule configuration-varying datasets: {variation_count}/60 (required >=40)")
    print(f"Reported-winner-change datasets: {winner_change_count}/60 (required >=15)")
    print(f"FINAL_LABEL={final_label}")


def main() -> None:
    # This is intentionally the first protocol action: no NumPy import or arrays
    # exist before the preregistration and its digest are durably written.
    preregistration_timestamp = utc_now()
    preregistration = build_preregistration(preregistration_timestamp)
    preregistration_path = ROOT / "preregistration.json"
    preregistration_path.write_text(
        json.dumps(preregistration, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    preregistration_digest = write_digest(
        preregistration_path, ROOT / "preregistration.sha256"
    )
    run_experiment(preregistration_digest, preregistration_timestamp)


if __name__ == "__main__":
    main()
