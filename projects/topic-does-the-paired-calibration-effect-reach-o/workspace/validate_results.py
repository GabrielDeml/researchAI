#!/usr/bin/env python3
"""Independent checks for experiment outputs and the vectorized ECE routine."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image

from experiment import (
    CSV_COLUMNS,
    N_BINS,
    N_SPLITS,
    affine_logit_predictions,
    ece,
    ece_many,
    make_sample,
)


ROOT = Path(__file__).resolve().parent


def reference_ece(predictions: np.ndarray, y: np.ndarray) -> float:
    """Literal loop implementation of the protocol's ECE definition."""

    n = predictions.size
    bin_indices = np.minimum(
        np.floor(N_BINS * predictions).astype(np.int64), N_BINS - 1
    )
    result = 0.0
    for bin_index in range(N_BINS):
        mask = bin_indices == bin_index
        count = int(mask.sum())
        if count:
            result += (count / n) * abs(
                float(np.mean(y[mask])) - float(np.mean(predictions[mask]))
            )
    return result


def main() -> None:
    q, y = make_sample([20250308, 17, 0, 9], 50)
    a = np.asarray([0.0, 0.7, 1.0, 1.8])
    b = np.asarray([0.0, -0.4, 0.0, 1.2])
    predictions = affine_logit_predictions(q, a, b)
    vectorized = ece_many(predictions, y)
    reference = np.asarray([reference_ece(row, y) for row in predictions])
    np.testing.assert_allclose(vectorized, reference, rtol=0.0, atol=2e-16)
    np.testing.assert_allclose(ece(q, y), reference_ece(q, y), rtol=0.0, atol=2e-16)

    with (ROOT / "split_results.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == CSV_COLUMNS
        rows = list(reader)
    assert len(rows) == N_SPLITS
    assert [int(row["split"]) for row in rows] == list(range(N_SPLITS))

    with (ROOT / "results.json").open(encoding="utf-8") as handle:
        results = json.load(handle)
    assert all(not isinstance(value, (dict, list)) for value in results.values())
    reused = np.asarray([float(row["reused_paired_reduction"]) for row in rows])
    evaluation = np.asarray(
        [float(row["evaluation_paired_reduction"]) for row in rows]
    )
    np.testing.assert_allclose(
        results["mean_reused_paired_ece_reduction_A"], np.mean(reused),
        rtol=0.0, atol=1e-15
    )
    np.testing.assert_allclose(
        results["mean_independent_paired_ece_reduction_B"], np.mean(evaluation),
        rtol=0.0, atol=1e-15
    )

    with (ROOT / "summary.json").open(encoding="utf-8") as handle:
        summary = json.load(handle)
    assert results["decision"] == summary["decision"]
    assert results["hypothesis_supported"] == summary["hypothesis_supported"]

    for path in (
        ROOT / "figures" / "paired_calibration_effects.png",
        ROOT / "paired_calibration_effects.png",
    ):
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.width >= 1600 and image.height >= 700

    print(
        "Validation passed: reference ECE agreement, 80-row CSV schema, flat "
        "results JSON, aggregate consistency, decision consistency, and PNG dimensions."
    )


if __name__ == "__main__":
    main()
