#!/usr/bin/env python3
"""Read-only consistency checks for the completed tuning-tie experiment."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pandas as pd
from PIL import Image


ROOT = Path(__file__).resolve().parent


def main() -> None:
    with (ROOT / "results.json").open(encoding="utf-8") as handle:
        results = json.load(handle)
    with (ROOT / "summary_metrics.json").open(encoding="utf-8") as handle:
        summary = json.load(handle)
    samples = pd.read_csv(ROOT / "tie_samples.csv")
    population = pd.read_csv(ROOT / "population_accuracies.csv")

    scalar_types = (str, int, float, bool, type(None))
    assert all(isinstance(value, scalar_types) for value in results.values())
    assert samples.shape[0] == 500
    assert population.shape[0] == 11
    score_columns = [f"score_j{j}" for j in range(11)]
    assert all(samples[column].between(0, 300).all() for column in score_columns)
    assert all((samples[column] % 1 == 0).all() for column in score_columns)
    assert (samples["M_s"] == samples[score_columns].max(axis=1)).all()
    assert (samples["optimizer_count"] == samples[score_columns].eq(samples["M_s"], axis=0).sum(axis=1)).all()
    assert int(samples["T_s"].sum()) == results["exact_tie_count"] == 84
    assert int(samples["W_s"].sum()) == results["wide_gap_tie_count"] == 80
    assert math.isclose(results["exact_tie_rate"], 84 / 500, rel_tol=0.0, abs_tol=1e-15)
    assert math.isclose(results["conditional_wide_gap_proportion"], 80 / 84, rel_tol=0.0, abs_tol=1e-15)
    assert results["decision"] == summary["decision"] == "SUPPORTED"
    assert results["population_checks_pass"] is True
    assert population["population_accuracy"].idxmax() == 5
    assert math.isclose(population.loc[5, "cutoff"], 0.50, abs_tol=1e-15)
    assert samples.loc[samples["T_s"] == 0, "D_s"].isna().all()
    assert (samples.loc[samples["W_s"] == 1, "D_s"] > 0.001).all()
    assert (samples.loc[samples["T_s"] == 1, "D_s"].notna()).all()

    figure = ROOT / "figures" / "tuning_tie_results.png"
    root_figure = ROOT / "tuning_tie_results.png"
    with Image.open(figure) as image:
        assert image.size == (1600, 700)
        assert image.format == "PNG"
    assert hashlib.sha256(figure.read_bytes()).digest() == hashlib.sha256(root_figure.read_bytes()).digest()

    expected_files = [
        "experiment.py",
        "results.json",
        "summary_metrics.json",
        "tie_samples.csv",
        "population_accuracies.csv",
        "tuning_tie_results.png",
        "figures/tuning_tie_results.png",
    ]
    assert all((ROOT / name).is_file() for name in expected_files)
    print(
        "Output verification PASS: 500 rows, 11 integer score columns, "
        "84 ties, 80 wide ties, flat results.json, and 1600x700 PNG."
    )


if __name__ == "__main__":
    main()
