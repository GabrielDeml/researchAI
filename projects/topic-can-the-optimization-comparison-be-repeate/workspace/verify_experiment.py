#!/usr/bin/env python3
"""Audit the completed experiment without rerunning any GA evaluations."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
import pandas as pd

import experiment as exp


ROOT = Path(__file__).resolve().parent


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def main() -> None:
    candidates = pd.read_csv(ROOT / "calibration_results.csv")
    selected = pd.read_csv(ROOT / "selected_settings_prevalidation.csv")
    results = pd.read_csv(ROOT / "results.csv")
    paired = pd.read_csv(ROOT / "paired_validation_outcomes.csv")
    summary = json.loads((ROOT / "run_summary.json").read_text(encoding="utf-8"))
    flat = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))

    assert len(candidates) == exp.N_SPLITS * 18
    assert len(selected) == exp.N_SPLITS
    assert len(results) == exp.N_SPLITS
    assert len(paired) == exp.N_SPLITS * exp.N_VALIDATION
    assert list(results.columns) == exp.RESULT_COLUMNS
    assert all(isinstance(value, (str, int, float, bool)) for value in flat.values())

    for split, group in candidates.groupby("split", sort=True):
        chosen = min(
            group.to_dict("records"),
            key=lambda row: (
                row["target_deviation"],
                row["B"],
                row["P"],
                exp.MUTATION_TIE_RANK[row["mutation_multiplier"]],
            ),
        )
        actual = selected.loc[selected["split"] == split].iloc[0]
        assert int(actual["P"]) == int(chosen["P"])
        assert float(actual["mutation_multiplier"]) == float(
            chosen["mutation_multiplier"]
        )
        assert int(actual["B"]) == int(chosen["B"])
        assert float(actual["calibration_success_rate"]) == float(
            chosen["calibration_success_rate"]
        )

    exp.validate_seed_schedule()
    expected_validation_seeds = {
        exp.BASE_SEED_START
        + exp.BASE_SEED_STRIDE * split
        + exp.VALIDATION_SEED_OFFSET
        + j
        for split in range(exp.N_SPLITS)
        for j in range(exp.N_VALIDATION)
    }
    assert set(paired["validation_seed"]) == expected_validation_seeds
    assert not paired.duplicated(["split", "validation_seed"]).any()

    d_value, d_ci, q_value, q_ci = exp.bootstrap(results)
    assert d_value == summary["primary_effect_D"]
    assert list(d_ci) == summary["primary_D_ci_95"]
    assert q_value == summary["batch_effect_Q"]
    assert list(q_ci) == summary["batch_Q_ci_95"]
    only_serial = int(
        ((paired["serial_success"] == 1) & (paired["batch_success"] == 0)).sum()
    )
    only_batch = int(
        ((paired["serial_success"] == 0) & (paired["batch_success"] == 1)).sum()
    )
    assert only_serial == summary["only_serial_succeeds"]
    assert only_batch == summary["only_batch_succeeds"]
    assert q_value == (only_batch - only_serial) / len(paired)

    assert png_dimensions(ROOT / "calibration_optimism.png") == (1600, 700)
    assert png_dimensions(ROOT / "figures" / "calibration_optimism.png") == (
        1600,
        700,
    )
    assert (ROOT / "preregistration.json").stat().st_mtime_ns < (
        ROOT / "selected_settings_prevalidation.csv"
    ).stat().st_mtime_ns
    assert (ROOT / "selected_settings_prevalidation.csv").stat().st_mtime_ns < (
        ROOT / "results.csv"
    ).stat().st_mtime_ns

    print(
        "Artifact audit passed: calibration selection, seed schedule, bootstrap "
        "metrics, scalar JSON, row counts, lock ordering, and PNG dimensions verified."
    )


if __name__ == "__main__":
    main()
