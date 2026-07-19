#!/usr/bin/env python3
"""Read-only validation of the completed publication tree."""

from __future__ import annotations

import json
import struct
from pathlib import Path

from audit_common import canonical_json_bytes, sha256_file


ROOT = Path(__file__).resolve().parent


def read_jsonl(relative_path: str):
    data = (ROOT / relative_path).read_bytes()
    rows = [json.loads(line) for line in data.splitlines()]
    if data != b"".join(canonical_json_bytes(row) for row in rows):
        raise AssertionError(f"noncanonical JSONL: {relative_path}")
    return rows


def main() -> None:
    results_bytes = (ROOT / "results.json").read_bytes()
    results = json.loads(results_bytes)
    assert results_bytes == canonical_json_bytes(results)
    assert all(isinstance(value, (str, int, float, bool)) for value in results.values())
    assert results["hypothesis_supported"] is True
    assert results["altered_payload_only_accepted"] == 128
    assert results["altered_context_bound_accepted"] == 0
    assert results["unmodified_payload_only_accepted"] == 3968
    assert results["unmodified_context_bound_accepted"] == 3968
    assert results["unexpected_deviation_count"] == 0

    raw = read_jsonl("records/raw_records.jsonl")
    bundles = read_jsonl("records/unmodified_bundles.jsonl")
    unmodified = read_jsonl("records/unmodified_verification.jsonl")
    altered = read_jsonl("records/altered_bundles.jsonl")
    attacks = read_jsonl("records/attack_results.jsonl")
    assert len(raw) == len(bundles) == 3968
    assert len(unmodified) == 7936
    assert len(altered) == len(attacks) == 128
    assert sum(row["accepted"] for row in unmodified) == 7936
    assert sum(row["payload_only_accepted"] for row in attacks) == 128
    assert sum(row["context_bound_accepted"] for row in attacks) == 0
    assert raw[0]["unit_identifier"] == "case-000/baseline"
    assert raw[1]["unit_identifier"] == "case-000/mutant-00"
    assert raw[-1]["unit_identifier"] == "case-127/mutant-29"

    counterexamples = json.loads((ROOT / "records/first_counterexamples.json").read_bytes())
    assert len(counterexamples["provenance_failure_witnesses"]) == 10
    assert counterexamples["unexpected_deviations"] == []

    figure = (ROOT / "figures/provenance_acceptance.png").read_bytes()
    assert figure[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", figure[16:24]) == (1600, 900)

    inventory = read_jsonl("records/artifact_inventory.jsonl")
    expected_paths = []
    inventory_path = ROOT / "records/artifact_inventory.jsonl"
    for directory in ("artifacts", "fresh_process", "records", "figures"):
        for path in (ROOT / directory).rglob("*"):
            if path.is_file() and path != inventory_path:
                expected_paths.append(path.relative_to(ROOT).as_posix())
    expected_paths.sort()
    assert [row["path"] for row in inventory] == expected_paths
    assert len(inventory) == 11912
    for row in inventory:
        path = ROOT / row["path"]
        assert row["byte_length"] == path.stat().st_size
        assert row["sha256"] == sha256_file(path)
    print(
        f"validated: raw={len(raw)}, attacks={len(attacks)}, inventory={len(inventory)}, "
        f"inventory_root_sha256={sha256_file(inventory_path)}"
    )


if __name__ == "__main__":
    main()
