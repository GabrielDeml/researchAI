#!/usr/bin/env python3
"""Consistency checks for the generated experiment artifacts."""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent


def main() -> None:
    metrics = json.loads((ROOT / "metrics.json").read_text(encoding="utf-8"))
    results = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))
    blocks = pd.read_csv(ROOT / "block_results.csv")

    assert len(blocks) == 973
    assert (blocks["analysis"] == "overlapping").sum() == 953
    assert (blocks["analysis"] == "disjoint").sum() == 20
    assert blocks["selected_rule"].notna().all()
    assert blocks["n_eligible_rules"].eq(6).all()
    assert blocks["selected_rule"].between(1, 6).all()
    assert (blocks["D"] == (blocks["U_dev"] >= 0.25).astype(int)).all()
    assert blocks.loc[blocks.analysis == "overlapping", "start_seed"].tolist() == list(range(953))
    assert blocks.loc[blocks.analysis == "disjoint", "start_seed"].tolist() == list(range(0, 960, 48))

    overlap = blocks[blocks.analysis == "overlapping"]
    assert math.isclose(
        overlap["D"].mean(), metrics["overlapping_threshold_rate"], rel_tol=0.0, abs_tol=1e-12
    )
    expected_naive = math.sqrt(overlap["D"].mean() * (1 - overlap["D"].mean()) / 953)
    assert math.isclose(expected_naive, metrics["overlapping_threshold_se_naive"], rel_tol=0.0, abs_tol=1e-12)
    assert metrics["hypothesis_supported"] == all(metrics["criteria"].values())
    assert metrics["hypothesis_conclusion"] == (
        "supported" if metrics["hypothesis_supported"] else "refuted"
    )
    assert all(isinstance(value, (str, int, float, bool)) for value in results.values())
    assert all(not isinstance(value, (dict, list)) for value in results.values())

    with (ROOT / "figures" / "key_results.png").open("rb") as image:
        assert image.read(8) == b"\x89PNG\r\n\x1a\n"
        length = struct.unpack(">I", image.read(4))[0]
        assert image.read(4) == b"IHDR" and length == 13
        width, height = struct.unpack(">II", image.read(8))
        assert (width, height) == (2160, 1440)

    print("Validation passed: records, decisions, metrics, flat JSON, and 180-DPI figure are consistent.")


if __name__ == "__main__":
    main()
