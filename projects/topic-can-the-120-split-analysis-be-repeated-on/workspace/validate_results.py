#!/usr/bin/env python3
"""Independent read-back validation for saved experiment artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    metrics = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))
    assert all(isinstance(value, (str, int, float, bool)) for value in metrics.values())

    assert sha256(ROOT / "preregistration.json") == (ROOT / "preregistration.sha256").read_text().strip()
    assert sha256(ROOT / "selections.csv") == (ROOT / "selections.sha256").read_text().strip()
    freeze = json.loads((ROOT / "freeze_manifest.json").read_text(encoding="utf-8"))
    assert freeze["replication_generation_calls_before_freeze"] == 0
    assert freeze["verified_no_replication_generation_before_freeze"] is True

    grid = pd.read_csv(ROOT / "grid_permutations.csv", index_col=0).to_numpy(dtype=np.int64)
    expected_grid = np.stack([np.random.default_rng(400000 + k).permutation(12) for k in range(25)])
    assert np.array_equal(grid, expected_grid)

    selections = pd.read_csv(ROOT / "selections.csv")
    results = pd.read_csv(ROOT / "results.csv")
    summary = pd.read_csv(ROOT / "dataset_summary.csv")
    regime = pd.read_csv(ROOT / "regime_check.csv")
    bootstrap = pd.read_csv(ROOT / "bootstrap.csv")
    assert selections.shape[0] == 1500
    assert results.shape[0] == 3000
    assert summary.shape[0] == 60
    assert regime.shape[0] == 60 and bool(regime["passed"].all())
    assert bootstrap.shape[0] == 10000

    total = results[results["rule"] == "total_order"].sort_values(["dataset_id", "permutation_id"])
    first = results[results["rule"] == "first_encountered"].sort_values(["dataset_id", "permutation_id"])
    assert total.shape[0] == first.shape[0] == 1500
    total_ids = total["selected_config_id"].to_numpy().reshape(60, 25)
    first_ids = first["selected_config_id"].to_numpy().reshape(60, 25)
    total_estimates = total["final_120_split_estimate"].to_numpy().reshape(60, 25)
    first_estimates = first["final_120_split_estimate"].to_numpy().reshape(60, 25)
    total_labels = total["optimizer_label"].to_numpy().reshape(60, 25)
    first_labels = first["optimizer_label"].to_numpy().reshape(60, 25)

    invariant = np.array(
        [len(np.unique(total_ids[d])) == 1 and np.ptp(total_estimates[d]) <= 1e-12 for d in range(60)]
    )
    varying = np.array([len(np.unique(first_ids[d])) > 1 for d in range(60)])
    winner_change = np.any(first_labels != total_labels, axis=1)
    material_change = np.any(np.abs(first_estimates - total_estimates) > 0.005, axis=1)
    assert int(invariant.sum()) == metrics["total_order_invariant_datasets"]
    assert int(varying.sum()) == metrics["first_rule_configuration_varying_datasets"]
    assert int(winner_change.sum()) == metrics["reported_winner_change_datasets"]
    assert int(material_change.sum()) == metrics["material_estimate_change_datasets"]
    assert int(np.count_nonzero(first_ids != total_ids)) == metrics["different_id_cases"]

    bootstrap_columns = {
        "first_rule_configuration_variation_proportion": (
            "bootstrap_configuration_variation_proportion_ci95_lower",
            "bootstrap_configuration_variation_proportion_ci95_upper",
        ),
        "reported_winner_change_proportion": (
            "bootstrap_reported_winner_change_proportion_ci95_lower",
            "bootstrap_reported_winner_change_proportion_ci95_upper",
        ),
        "material_estimate_change_proportion": (
            "bootstrap_material_estimate_change_proportion_ci95_lower",
            "bootstrap_material_estimate_change_proportion_ci95_upper",
        ),
    }
    for column, metric_keys in bootstrap_columns.items():
        interval = np.quantile(bootstrap[column].to_numpy(), [0.025, 0.975], method="linear")
        assert np.array_equal(interval, np.array([metrics[metric_keys[0]], metrics[metric_keys[1]]]))

    image = Image.open(ROOT / "figures" / "tie_breaking_results.png")
    assert image.format == "PNG" and image.width > 2000 and image.height > 1000
    assert metrics["hypothesis_supported"] is (
        metrics["total_order_invariant_datasets"] == 60
        and metrics["first_rule_configuration_varying_datasets"] >= 40
        and metrics["reported_winner_change_datasets"] >= 15
    )
    print("Independent artifact validation passed: hashes, seeds, row counts, primary counts, bootstrap intervals, and PNG verified.")


if __name__ == "__main__":
    main()
