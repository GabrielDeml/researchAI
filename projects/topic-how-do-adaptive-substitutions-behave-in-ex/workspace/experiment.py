#!/usr/bin/env python3
"""Deterministic executable test of inventory- versus relationship-committing roots."""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import random
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

WORKSPACE = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(WORKSPACE / ".matplotlib-cache"))
os.environ.setdefault("XDG_CACHE_HOME", str(WORKSPACE / ".cache"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import fisher_exact


SEED = 20250308
GRAPH_COUNT = 40
UNITS_PER_GRAPH = 16
SOURCE_SIZE = 256
ROOT = WORKSPACE
FIGURES_DIR = ROOT / "figures"
CSV_PATH = ROOT / "candidate_results.csv"
RESULTS_PATH = ROOT / "results.json"
FIGURE_PATH = FIGURES_DIR / "acceptance_rates.png"


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def reverse_v1(value: bytes) -> bytes:
    return value[::-1]


def xor_a5_v1(value: bytes) -> bytes:
    return bytes(byte ^ 0xA5 for byte in value)


def add_17_v1(value: bytes) -> bytes:
    return bytes((byte + 17) % 256 for byte in value)


def rol1_v1(value: bytes) -> bytes:
    return bytes(((byte << 1) & 255) | (byte >> 7) for byte in value)


OPERATIONS: dict[str, Callable[[bytes], bytes]] = {
    "reverse_v1": reverse_v1,
    "xor_a5_v1": xor_a5_v1,
    "add_17_v1": add_17_v1,
    "rol1_v1": rol1_v1,
}


def operation_for_unit(unit_index: int) -> str:
    return tuple(OPERATIONS)[unit_index // 4]


def artifact_id(kind: str, content: bytes) -> str:
    return sha256_hex(b"artifact-v1\0" + kind.encode("ascii") + b"\0" + content)


def make_artifact(kind: str, content: bytes) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id(kind, content),
        "kind": kind,
        "size": len(content),
        "content_sha256": sha256_hex(content),
        "content_base64": base64.b64encode(content).decode("ascii"),
    }


def decode_artifact(record: dict[str, Any]) -> bytes:
    return base64.b64decode(record["content_base64"], validate=True)


def context_for(source: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_size": source["size"],
        "output_size": output["size"],
        "source_sha256": source["content_sha256"],
        "output_sha256": output["content_sha256"],
    }


def inventory_root(artifacts: dict[str, dict[str, Any]]) -> str:
    rows = [
        [
            record["artifact_id"],
            record["kind"],
            record["size"],
            record["content_sha256"],
        ]
        for record in artifacts.values()
    ]
    rows.sort()
    return sha256_hex(b"inventory-root-v1\0" + canonical_json(rows))


def relationship_root(manifest: dict[str, Any]) -> str:
    tuples = [
        [
            unit["unit_id"],
            unit["operation"],
            unit["source_id"],
            unit["output_id"],
        ]
        for unit in manifest["units"]
    ]
    tuples.sort(key=lambda row: row[0])
    payload = {
        "inventory_root": inventory_root(manifest["artifacts"]),
        "tuples": tuples,
    }
    return sha256_hex(b"relationship-root-v1\0" + canonical_json(payload))


@dataclass(frozen=True)
class TrustedRoots:
    """Authenticated out-of-band state that candidates cannot replace."""

    graph_index: int
    inventory_root: str
    relationship_root: str


def build_baseline(graph_index: int, rng: random.Random) -> dict[str, Any]:
    artifacts: dict[str, dict[str, Any]] = {}
    units: list[dict[str, Any]] = []
    for unit_index in range(UNITS_PER_GRAPH):
        source = (
            graph_index.to_bytes(4, "big")
            + unit_index.to_bytes(4, "big")
            + bytes(rng.getrandbits(8) for _ in range(SOURCE_SIZE - 8))
        )
        operation = operation_for_unit(unit_index)
        output = OPERATIONS[operation](source)
        source_record = make_artifact("source", source)
        output_record = make_artifact("output", output)
        source_id = source_record["artifact_id"]
        output_id = output_record["artifact_id"]
        assert (
            source_id != output_id
            and source_id not in artifacts
            and output_id not in artifacts
        )
        artifacts[source_id] = source_record
        artifacts[output_id] = output_record
        units.append(
            {
                "unit_id": f"g{graph_index:02d}_u{unit_index:02d}",
                "operation": operation,
                "source_id": source_id,
                "output_id": output_id,
                "context": context_for(source_record, output_record),
            }
        )
    assert len(artifacts) == 2 * UNITS_PER_GRAPH
    manifest: dict[str, Any] = {
        "graph_index": graph_index,
        "artifacts": artifacts,
        "units": units,
        "declared_relationship_root": "",
    }
    manifest["declared_relationship_root"] = relationship_root(manifest)
    return manifest


def make_paired_swap(
    baseline: dict[str, Any], first_unit: int, second_unit: int
) -> dict[str, Any]:
    candidate = deepcopy(baseline)
    first = candidate["units"][first_unit]
    second = candidate["units"][second_unit]
    assert first["operation"] == second["operation"]
    for field in ("source_id", "output_id"):
        first[field], second[field] = second[field], first[field]
    for unit in (first, second):
        unit["context"] = context_for(
            candidate["artifacts"][unit["source_id"]],
            candidate["artifacts"][unit["output_id"]],
        )
    candidate["declared_relationship_root"] = relationship_root(candidate)
    return candidate


def strict_type(value: Any, expected: type) -> bool:
    return type(value) is expected


def is_hex_digest(value: Any) -> bool:
    if not strict_type(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value)


def common_validate(manifest: dict[str, Any]) -> bool:
    """Fail closed on schema, artifact integrity, context, or execution errors."""

    try:
        if not strict_type(manifest, dict) or set(manifest) != {
            "graph_index",
            "artifacts",
            "units",
            "declared_relationship_root",
        }:
            return False
        if not strict_type(manifest["graph_index"], int):
            return False
        if not is_hex_digest(manifest["declared_relationship_root"]):
            return False
        artifacts = manifest["artifacts"]
        units = manifest["units"]
        if not strict_type(artifacts, dict) or len(artifacts) != 32:
            return False
        if not strict_type(units, list) or len(units) != UNITS_PER_GRAPH:
            return False

        for key, record in artifacts.items():
            if not strict_type(key, str) or not strict_type(record, dict):
                return False
            if set(record) != {
                "artifact_id",
                "kind",
                "size",
                "content_sha256",
                "content_base64",
            }:
                return False
            if record["artifact_id"] != key or not is_hex_digest(key):
                return False
            if record["kind"] not in {"source", "output"}:
                return False
            if not strict_type(record["size"], int) or record["size"] < 0:
                return False
            if not is_hex_digest(record["content_sha256"]):
                return False
            if not strict_type(record["content_base64"], str):
                return False
            content = decode_artifact(record)
            if record["size"] != len(content):
                return False
            if record["content_sha256"] != sha256_hex(content):
                return False
            if record["artifact_id"] != artifact_id(record["kind"], content):
                return False

        seen_unit_ids: set[str] = set()
        for unit in units:
            if not strict_type(unit, dict) or set(unit) != {
                "unit_id",
                "operation",
                "source_id",
                "output_id",
                "context",
            }:
                return False
            if not all(
                strict_type(unit[field], str)
                for field in ("unit_id", "operation", "source_id", "output_id")
            ):
                return False
            if unit["unit_id"] in seen_unit_ids:
                return False
            seen_unit_ids.add(unit["unit_id"])
            if unit["operation"] not in OPERATIONS:
                return False
            if unit["source_id"] not in artifacts or unit["output_id"] not in artifacts:
                return False
            source_record = artifacts[unit["source_id"]]
            output_record = artifacts[unit["output_id"]]
            if source_record["kind"] != "source" or output_record["kind"] != "output":
                return False
            context = unit["context"]
            if not strict_type(context, dict) or set(context) != {
                "source_size",
                "output_size",
                "source_sha256",
                "output_sha256",
            }:
                return False
            if not strict_type(context["source_size"], int) or not strict_type(
                context["output_size"], int
            ):
                return False
            if not is_hex_digest(context["source_sha256"]) or not is_hex_digest(
                context["output_sha256"]
            ):
                return False
            if context != context_for(source_record, output_record):
                return False
            source_bytes = decode_artifact(source_record)
            expected_output = OPERATIONS[unit["operation"]](source_bytes)
            if expected_output != decode_artifact(output_record):
                return False
        return True
    except (KeyError, TypeError, ValueError, base64.binascii.Error):
        return False


def all_units_reexecute(manifest: dict[str, Any]) -> bool:
    try:
        return all(
            OPERATIONS[unit["operation"]](
                decode_artifact(manifest["artifacts"][unit["source_id"]])
            )
            == decode_artifact(manifest["artifacts"][unit["output_id"]])
            for unit in manifest["units"]
        )
    except (KeyError, TypeError, ValueError, base64.binascii.Error):
        return False


def mutation_invariants(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    changed_edges: list[tuple[int, str]] = []
    changed_operations = 0
    for unit_index, (before, after) in enumerate(
        zip(baseline["units"], candidate["units"], strict=True)
    ):
        for field in ("source_id", "output_id"):
            if before[field] != after[field]:
                changed_edges.append((unit_index, field))
        if before["operation"] != after["operation"]:
            changed_operations += 1
    changed_units = {unit_index for unit_index, _ in changed_edges}
    candidate_inventory_root = inventory_root(candidate["artifacts"])
    baseline_inventory_root = inventory_root(baseline["artifacts"])
    candidate_relationship_root = relationship_root(candidate)
    baseline_relationship_root = relationship_root(baseline)
    shape_valid = (
        len(changed_edges) == 4
        and len(changed_units) == 2
        and all(
            {field for changed_unit, field in changed_edges if changed_unit == unit_index}
            == {"source_id", "output_id"}
            for unit_index in changed_units
        )
        and changed_operations == 0
        and candidate_relationship_root != baseline_relationship_root
    )
    values = {
        "artifact_records_equal_baseline": candidate["artifacts"]
        == baseline["artifacts"],
        "inventory_root_equal_baseline": candidate_inventory_root
        == baseline_inventory_root,
        "relationship_root_changed": candidate_relationship_root
        != baseline_relationship_root,
        "reexecution_all_units": all_units_reexecute(candidate),
        "changed_edge_field_count": len(changed_edges),
        "changed_edge_unit_count": len(changed_units),
        "no_operation_changes": changed_operations == 0,
        "mutation_shape_valid": shape_valid,
    }
    values["all_altered_invariants"] = all(
        (
            values["artifact_records_equal_baseline"],
            values["inventory_root_equal_baseline"],
            values["relationship_root_changed"],
            values["reexecution_all_units"],
            values["mutation_shape_valid"],
        )
    )
    return values


def evaluate_candidate(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    trusted: TrustedRoots,
    graph_index: int,
    candidate_type: str,
    alteration: str,
) -> dict[str, Any]:
    common = common_validate(candidate)
    recomputed_inventory = inventory_root(candidate["artifacts"])
    recomputed_relationship = relationship_root(candidate)
    if candidate_type == "altered":
        invariants = mutation_invariants(baseline, candidate)
    else:
        invariants = {
            "artifact_records_equal_baseline": candidate["artifacts"]
            == baseline["artifacts"],
            "inventory_root_equal_baseline": recomputed_inventory
            == trusted.inventory_root,
            "relationship_root_changed": False,
            "reexecution_all_units": all_units_reexecute(candidate),
            "changed_edge_field_count": 0,
            "changed_edge_unit_count": 0,
            "no_operation_changes": True,
            "mutation_shape_valid": True,
            "all_altered_invariants": True,
        }
    return {
        "graph_index": graph_index,
        "candidate_type": candidate_type,
        "alteration": alteration,
        **invariants,
        "common_validation": common,
        "recomputed_inventory_root": recomputed_inventory,
        "recomputed_relationship_root": recomputed_relationship,
        "trusted_inventory_root": trusted.inventory_root,
        "trusted_relationship_root": trusted.relationship_root,
        "declared_relationship_root": candidate["declared_relationship_root"],
        "auth_inventory_accept": common
        and recomputed_inventory == trusted.inventory_root,
        "auth_relationship_accept": common
        and recomputed_relationship == trusted.relationship_root,
        "unauth_relationship_accept": common
        and recomputed_relationship == candidate["declared_relationship_root"],
    }


def write_csv(rows: list[dict[str, Any]]) -> None:
    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def count_accepts(
    rows: list[dict[str, Any]], candidate_type: str, condition: str
) -> int:
    return sum(
        row[condition]
        for row in rows
        if row["candidate_type"] == candidate_type
    )


def plot_acceptance_rates(rows: list[dict[str, Any]]) -> None:
    conditions = (
        ("auth_inventory_accept", "Authenticated inventory", "#4C78A8"),
        ("auth_relationship_accept", "Authenticated relationships", "#F58518"),
        ("unauth_relationship_accept", "Unauthenticated relationships", "#54A24B"),
    )
    candidate_types = ("control", "altered")
    group_labels = ("Unmodified controls (n=40)", "Paired swaps (n=80)")
    denominators = (40, 80)
    x_positions = (0.0, 1.0)
    width = 0.24

    figure, axis = plt.subplots(figsize=(9, 5), dpi=150)
    for condition_index, (field, label, color) in enumerate(conditions):
        offset = (condition_index - 1) * width
        numerators = [
            count_accepts(rows, candidate_type, field)
            for candidate_type in candidate_types
        ]
        proportions = [
            numerator / denominator
            for numerator, denominator in zip(numerators, denominators, strict=True)
        ]
        bars = axis.bar(
            [position + offset for position in x_positions],
            proportions,
            width=width,
            label=label,
            color=color,
        )
        for bar, numerator, denominator, proportion in zip(
            bars, numerators, denominators, proportions, strict=True
        ):
            axis.annotate(
                f"{numerator}/{denominator}\n{proportion:.2f}",
                (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
            )
    axis.set_xticks(x_positions, group_labels)
    axis.set_ylim(0, 1)
    axis.set_ylabel("Acceptance proportion")
    axis.set_title("Root-condition acceptance of executable transformation graphs")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3)
    figure.tight_layout()
    figure.savefig(FIGURE_PATH, dpi=150)
    plt.close(figure)


def main() -> None:
    FIGURES_DIR.mkdir(exist_ok=True)
    rng = random.Random(SEED)
    baselines = [build_baseline(graph_index, rng) for graph_index in range(GRAPH_COUNT)]
    trusted_roots = tuple(
        TrustedRoots(
            graph_index=graph_index,
            inventory_root=inventory_root(baseline["artifacts"]),
            relationship_root=relationship_root(baseline),
        )
        for graph_index, baseline in enumerate(baselines)
    )

    rows: list[dict[str, Any]] = []
    for graph_index, (baseline, trusted) in enumerate(
        zip(baselines, trusted_roots, strict=True)
    ):
        control = deepcopy(baseline)
        rows.append(
            evaluate_candidate(
                baseline, control, trusted, graph_index, "control", "none"
            )
        )
        for alteration, unit_pair in (
            ("A_swap_units_0_1", (0, 1)),
            ("B_swap_units_8_9", (8, 9)),
        ):
            candidate = make_paired_swap(baseline, *unit_pair)
            invariant_values = mutation_invariants(baseline, candidate)
            assert invariant_values["all_altered_invariants"]
            rows.append(
                evaluate_candidate(
                    baseline,
                    candidate,
                    trusted,
                    graph_index,
                    "altered",
                    alteration,
                )
            )

    write_csv(rows)
    plot_acceptance_rates(rows)

    control_rows = [row for row in rows if row["candidate_type"] == "control"]
    altered_rows = [row for row in rows if row["candidate_type"] == "altered"]
    altered_auth_relationship_accepted = count_accepts(
        rows, "altered", "auth_relationship_accept"
    )
    control_auth_relationship_accepted = count_accepts(
        rows, "control", "auth_relationship_accept"
    )
    fisher_table = [
        [
            altered_auth_relationship_accepted,
            len(altered_rows) - altered_auth_relationship_accepted,
        ],
        [
            control_auth_relationship_accepted,
            len(control_rows) - control_auth_relationship_accepted,
        ],
    ]
    fisher_result = fisher_exact(fisher_table, alternative="less")
    acceptance_rate_difference = (
        control_auth_relationship_accepted / len(control_rows)
        - altered_auth_relationship_accepted / len(altered_rows)
    )

    altered_inventory_preserved = sum(
        row["artifact_records_equal_baseline"]
        and row["inventory_root_equal_baseline"]
        for row in altered_rows
    )
    altered_reexecution = sum(row["reexecution_all_units"] for row in altered_rows)
    altered_mutation_shape = sum(row["mutation_shape_valid"] for row in altered_rows)
    altered_common_validation = sum(row["common_validation"] for row in altered_rows)
    control_common_validation = sum(row["common_validation"] for row in control_rows)
    altered_auth_inventory = count_accepts(rows, "altered", "auth_inventory_accept")
    control_auth_inventory = count_accepts(rows, "control", "auth_inventory_accept")
    altered_unauth_relationship = count_accepts(
        rows, "altered", "unauth_relationship_accept"
    )
    control_unauth_relationship = count_accepts(
        rows, "control", "unauth_relationship_accept"
    )
    negative_control_sanity = (
        altered_unauth_relationship == 80 and control_unauth_relationship == 40
    )
    hypothesis_supported = (
        altered_inventory_preserved == 80
        and altered_reexecution == 80
        and altered_mutation_shape == 80
        and altered_common_validation == 80
        and control_common_validation == 40
        and altered_auth_inventory == 80
        and control_auth_inventory == 40
        and altered_auth_relationship_accepted == 0
        and control_auth_relationship_accepted == 40
        and acceptance_rate_difference == 1.0
        and float(fisher_result.pvalue) < 0.001
        and negative_control_sanity
    )

    results: dict[str, str | int | float | bool] = {
        "seed": SEED,
        "graph_count": GRAPH_COUNT,
        "units_per_graph": UNITS_PER_GRAPH,
        "artifacts_per_graph": 2 * UNITS_PER_GRAPH,
        "control_candidate_count": len(control_rows),
        "altered_candidate_count": len(altered_rows),
        "total_candidate_count": len(rows),
        "csv_row_count": len(rows),
        "altered_inventory_preservation_count": altered_inventory_preserved,
        "altered_inventory_preservation_denominator": len(altered_rows),
        "altered_inventory_preservation_rate": altered_inventory_preserved
        / len(altered_rows),
        "altered_reexecution_success_count": altered_reexecution,
        "altered_reexecution_success_denominator": len(altered_rows),
        "altered_reexecution_success_rate": altered_reexecution / len(altered_rows),
        "altered_mutation_shape_valid_count": altered_mutation_shape,
        "altered_mutation_shape_valid_denominator": len(altered_rows),
        "altered_mutation_shape_valid_rate": altered_mutation_shape / len(altered_rows),
        "altered_common_validation_pass_count": altered_common_validation,
        "altered_common_validation_denominator": len(altered_rows),
        "control_common_validation_pass_count": control_common_validation,
        "control_common_validation_denominator": len(control_rows),
        "auth_inventory_altered_accepted": altered_auth_inventory,
        "auth_inventory_altered_total": len(altered_rows),
        "auth_inventory_altered_rate": altered_auth_inventory / len(altered_rows),
        "auth_inventory_control_accepted": control_auth_inventory,
        "auth_inventory_control_total": len(control_rows),
        "auth_inventory_control_rate": control_auth_inventory / len(control_rows),
        "auth_relationship_altered_accepted": altered_auth_relationship_accepted,
        "auth_relationship_altered_total": len(altered_rows),
        "auth_relationship_altered_rate": altered_auth_relationship_accepted
        / len(altered_rows),
        "auth_relationship_control_accepted": control_auth_relationship_accepted,
        "auth_relationship_control_total": len(control_rows),
        "auth_relationship_control_rate": control_auth_relationship_accepted
        / len(control_rows),
        "unauth_relationship_altered_accepted": altered_unauth_relationship,
        "unauth_relationship_altered_total": len(altered_rows),
        "unauth_relationship_altered_rate": altered_unauth_relationship
        / len(altered_rows),
        "unauth_relationship_control_accepted": control_unauth_relationship,
        "unauth_relationship_control_total": len(control_rows),
        "unauth_relationship_control_rate": control_unauth_relationship
        / len(control_rows),
        "relationship_acceptance_rate_difference": acceptance_rate_difference,
        "fisher_table_altered_accepted": fisher_table[0][0],
        "fisher_table_altered_rejected": fisher_table[0][1],
        "fisher_table_control_accepted": fisher_table[1][0],
        "fisher_table_control_rejected": fisher_table[1][1],
        "fisher_alternative": "less",
        "fisher_odds_ratio": float(fisher_result.statistic),
        "fisher_p_value": float(fisher_result.pvalue),
        "negative_control_sanity_passed": negative_control_sanity,
        "hypothesis_supported": hypothesis_supported,
        "hypothesis_classification": "SUPPORTED" if hypothesis_supported else "REFUTED",
        "figure_path": "figures/acceptance_rates.png",
        "csv_path": "candidate_results.csv",
    }
    assert all(
        isinstance(value, (str, int, float, bool)) for value in results.values()
    )
    RESULTS_PATH.write_text(
        json.dumps(results, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    print("Ran 40 deterministic 16-unit graphs, 40 controls, and 80 paired swaps.")
    print(
        "Altered invariants: "
        f"inventory {altered_inventory_preserved}/80, "
        f"re-execution {altered_reexecution}/80, "
        f"mutation shape {altered_mutation_shape}/80."
    )
    print(
        "Acceptance (altered/control): "
        f"AUTH_INVENTORY {altered_auth_inventory}/80 and {control_auth_inventory}/40; "
        "AUTH_RELATIONSHIP "
        f"{altered_auth_relationship_accepted}/80 and "
        f"{control_auth_relationship_accepted}/40; "
        "UNAUTH_RELATIONSHIP "
        f"{altered_unauth_relationship}/80 and {control_unauth_relationship}/40."
    )
    print(
        f"Relationship rate difference={acceptance_rate_difference:.1f}; "
        f"one-sided Fisher p={float(fisher_result.pvalue):.6g}."
    )
    print(f"Hypothesis classification: {results['hypothesis_classification']}")


if __name__ == "__main__":
    main()
