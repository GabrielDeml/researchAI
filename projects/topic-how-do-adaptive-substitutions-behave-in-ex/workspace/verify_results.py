#!/usr/bin/env python3
"""Independent structural checks for experiment outputs."""

from __future__ import annotations

import csv
import json
import struct
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def as_bool(value: str) -> bool:
    if value not in {"True", "False"}:
        raise AssertionError(f"non-Boolean CSV value: {value!r}")
    return value == "True"


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        assert handle.read(8) == b"\x89PNG\r\n\x1a\n"
        length = struct.unpack(">I", handle.read(4))[0]
        assert handle.read(4) == b"IHDR" and length == 13
        return struct.unpack(">II", handle.read(8))


def main() -> None:
    results = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))
    assert isinstance(results, dict)
    assert all(
        isinstance(value, (str, int, float, bool)) and value is not None
        for value in results.values()
    )

    with (ROOT / "candidate_results.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 120
    assert Counter(row["candidate_type"] for row in rows) == {
        "control": 40,
        "altered": 80,
    }
    assert Counter(row["alteration"] for row in rows) == {
        "none": 40,
        "A_swap_units_0_1": 40,
        "B_swap_units_8_9": 40,
    }
    assert Counter(int(row["graph_index"]) for row in rows) == {
        graph_index: 3 for graph_index in range(40)
    }

    altered = [row for row in rows if row["candidate_type"] == "altered"]
    controls = [row for row in rows if row["candidate_type"] == "control"]
    for row in altered:
        assert as_bool(row["artifact_records_equal_baseline"])
        assert as_bool(row["inventory_root_equal_baseline"])
        assert as_bool(row["relationship_root_changed"])
        assert as_bool(row["reexecution_all_units"])
        assert int(row["changed_edge_field_count"]) == 4
        assert int(row["changed_edge_unit_count"]) == 2
        assert as_bool(row["no_operation_changes"])
        assert as_bool(row["mutation_shape_valid"])
        assert as_bool(row["all_altered_invariants"])
        assert as_bool(row["common_validation"])
        assert row["recomputed_inventory_root"] == row["trusted_inventory_root"]
        assert row["recomputed_relationship_root"] != row["trusted_relationship_root"]
        assert row["recomputed_relationship_root"] == row["declared_relationship_root"]
        assert as_bool(row["auth_inventory_accept"])
        assert not as_bool(row["auth_relationship_accept"])
        assert as_bool(row["unauth_relationship_accept"])
    for row in controls:
        assert as_bool(row["common_validation"])
        assert row["recomputed_inventory_root"] == row["trusted_inventory_root"]
        assert row["recomputed_relationship_root"] == row["trusted_relationship_root"]
        assert row["recomputed_relationship_root"] == row["declared_relationship_root"]
        assert as_bool(row["auth_inventory_accept"])
        assert as_bool(row["auth_relationship_accept"])
        assert as_bool(row["unauth_relationship_accept"])

    assert len({row["trusted_inventory_root"] for row in rows}) == 40
    assert len({row["trusted_relationship_root"] for row in rows}) == 40
    assert results["csv_row_count"] == len(rows)
    assert results["altered_inventory_preservation_count"] == 80
    assert results["altered_reexecution_success_count"] == 80
    assert results["altered_mutation_shape_valid_count"] == 80
    assert results["auth_inventory_altered_accepted"] == 80
    assert results["auth_inventory_control_accepted"] == 40
    assert results["auth_relationship_altered_accepted"] == 0
    assert results["auth_relationship_control_accepted"] == 40
    assert results["unauth_relationship_altered_accepted"] == 80
    assert results["unauth_relationship_control_accepted"] == 40
    assert results["relationship_acceptance_rate_difference"] == 1.0
    assert results["fisher_p_value"] < 0.001
    assert results["hypothesis_supported"] is True
    width, height = png_dimensions(ROOT / "figures" / "acceptance_rates.png")
    assert width >= 1200 and height >= 700
    print(
        f"Verified flat results.json, 120 CSV rows, all exact counts, "
        f"and {width}x{height} PNG."
    )


if __name__ == "__main__":
    main()
