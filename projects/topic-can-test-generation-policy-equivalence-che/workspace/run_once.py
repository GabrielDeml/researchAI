"""Produce one deterministic, complete experiment payload."""

from __future__ import annotations

import hashlib
import json
import sys

from canonicalizers import (
    MUTATION_CATALOG,
    canonical_json_bytes,
    canonicalize,
    canonicalize_mutant,
)
from independent_parser import PolicyParseError, parse_archive
from independent_verifier import (
    REQUEST_DOMAIN_SIZE,
    behavioral_distance,
    first_counterexample,
    policy_bitset,
)
from policy_generator import SEED, UNIVERSES, generate_source_policies


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_payload_bytes(payload: dict) -> bytes:
    return canonical_json_bytes(payload)


def run_once() -> dict:
    sources = generate_source_policies()
    c0_cases: list[dict] = []
    c0_archives: dict[str, bytes] = {}
    c0_policies: dict[str, dict] = {}
    c0_bitsets: dict[str, int] = {}

    for source in sources:
        case_id = source["case_id"]
        policy = source["source_policy"]
        source_bytes = canonical_json_bytes({"version": 1, "policy": policy})
        error: str | None = None
        parser_accepted = False
        byte_fixed_point = False
        semantically_equivalent = False
        c0_bytes = b""
        parsed_policy: dict | None = None
        source_bits: int | None = None
        try:
            c0_bytes = canonicalize(source_bytes)
            parsed_policy = parse_archive(c0_bytes)
            parser_accepted = True
        except Exception as exc:  # retained in deterministic results if validation fails
            error = f"{type(exc).__name__}: {exc}"
        if c0_bytes:
            try:
                byte_fixed_point = canonicalize(c0_bytes) == c0_bytes
            except Exception as exc:
                error = error or f"{type(exc).__name__}: {exc}"
        if parsed_policy is not None:
            try:
                source_bits = policy_bitset(policy)
                parsed_bits = policy_bitset(parsed_policy)
                semantically_equivalent = source_bits == parsed_bits
            except Exception as exc:
                error = error or f"{type(exc).__name__}: {exc}"

        record = {
            "case_id": case_id,
            "x": source["x"],
            "source_policy": policy,
            "parser_accepted": parser_accepted,
            "byte_fixed_point": byte_fixed_point,
            "semantically_equivalent": semantically_equivalent,
            "archive_sha256": _sha256(c0_bytes) if c0_bytes else None,
            "archive_byte_length": len(c0_bytes),
            "allowed_request_count": source_bits.bit_count() if source_bits is not None else None,
            "error": error,
        }
        c0_cases.append(record)
        if parsed_policy is not None and source_bits is not None:
            c0_archives[case_id] = c0_bytes
            c0_policies[case_id] = parsed_policy
            c0_bitsets[case_id] = policy_bitset(parsed_policy)

    c0_aggregates = {
        "parser_acceptance_count": sum(r["parser_accepted"] for r in c0_cases),
        "byte_fixed_point_count": sum(r["byte_fixed_point"] for r in c0_cases),
        "semantic_equivalence_count": sum(r["semantically_equivalent"] for r in c0_cases),
        "case_count": len(c0_cases),
    }

    mutant_records: list[dict] = []
    for mutant_id in MUTATION_CATALOG:
        case_records: list[dict] = []
        for source in sources:
            case_id = source["case_id"]
            c0_bytes = c0_archives[case_id]
            y = canonicalize_mutant(c0_bytes, mutant_id)
            z = canonicalize_mutant(y, mutant_id)
            parser_accepted = False
            equivalent = False
            distance: int | None = None
            counterexample = None
            error = None
            try:
                mutant_policy = parse_archive(y)
                parser_accepted = True
                mutant_bits = policy_bitset(mutant_policy)
                baseline_bits = c0_bitsets[case_id]
                distance = behavioral_distance(baseline_bits, mutant_bits)
                equivalent = distance == 0
                counterexample = first_counterexample(baseline_bits, mutant_bits)
            except (PolicyParseError, KeyError, TypeError, ValueError) as exc:
                error = f"{type(exc).__name__}: {exc}"
            case_records.append(
                {
                    "case_id": case_id,
                    "parser_accepted": parser_accepted,
                    "byte_fixed_point": y == z,
                    "semantically_equivalent": equivalent,
                    "behavioral_distance": distance,
                    "archive_sha256": _sha256(y),
                    "c0_byte_length": len(c0_bytes),
                    "mutant_byte_length": len(y),
                    "first_counterexample": counterexample,
                    "error": error,
                }
            )

        failing = [record for record in case_records if not record["semantically_equivalent"]]
        distances = [
            record["behavioral_distance"]
            for record in case_records
            if record["behavioral_distance"] is not None
        ]
        aggregate = {
            "accepted_case_count": sum(r["parser_accepted"] for r in case_records),
            "fixed_point_case_count": sum(r["byte_fixed_point"] for r in case_records),
            "equivalent_case_count": sum(r["semantically_equivalent"] for r in case_records),
            "counterexample_case_count": 128
            - sum(r["semantically_equivalent"] for r in case_records),
            "total_behavioral_distance": sum(distances),
            "maximum_behavioral_distance": max(distances, default=0),
            "first_failing_case": failing[0]["case_id"] if failing else None,
            "first_counterexample": failing[0]["first_counterexample"] if failing else None,
        }
        mutant_records.append(
            {
                "mutant_id": mutant_id,
                "description": MUTATION_CATALOG[mutant_id],
                "cases": case_records,
                "aggregate": aggregate,
            }
        )

    total_acceptances = sum(
        mutant["aggregate"]["accepted_case_count"] for mutant in mutant_records
    )
    total_fixed_points = sum(
        mutant["aggregate"]["fixed_point_case_count"] for mutant in mutant_records
    )
    total_equivalent = sum(
        mutant["aggregate"]["equivalent_case_count"] for mutant in mutant_records
    )
    rejected_mutants = sum(
        mutant["aggregate"]["counterexample_case_count"] > 0 for mutant in mutant_records
    )
    mutant_aggregates = {
        "parser_acceptance_count": total_acceptances,
        "parser_acceptance_denominator": 3840,
        "byte_fixed_point_count": total_fixed_points,
        "byte_fixed_point_denominator": 3840,
        "semantic_equivalence_count": total_equivalent,
        "semantic_equivalence_denominator": 3840,
        "semantically_rejected_mutant_count": rejected_mutants,
        "mutant_count": 30,
    }
    chart_values = {
        "mutant_ids": [m["mutant_id"] for m in mutant_records],
        "accepted_case_count": [
            m["aggregate"]["accepted_case_count"] for m in mutant_records
        ],
        "fixed_point_case_count": [
            m["aggregate"]["fixed_point_case_count"] for m in mutant_records
        ],
        "counterexample_case_count": [
            m["aggregate"]["counterexample_case_count"] for m in mutant_records
        ],
        "semantically_rejected_mutant_count": rejected_mutants,
        "rejection_threshold": 27,
    }
    payload = {
        "seed": SEED,
        "schema": {
            "archive": "UTF-8 JSON followed by exactly one newline",
            "top_level": {"version": 1, "policy": "object"},
            "required_policy_fields": ["policy_id"],
            "optional_policy_fields": [
                "effect",
                "subjects",
                "actions",
                "resources",
                "time_slots",
                "regions",
                "min_clearance",
                "require_mfa",
                "max_amount",
            ],
            "defaults": {
                "effect": "deny",
                "subjects": UNIVERSES["subjects"],
                "actions": UNIVERSES["actions"],
                "resources": UNIVERSES["resources"],
                "time_slots": UNIVERSES["time_slots"],
                "regions": UNIVERSES["regions"],
                "min_clearance": 0,
                "require_mfa": False,
                "max_amount": 3,
            },
        },
        "universes": UNIVERSES,
        "request_domain_size": REQUEST_DOMAIN_SIZE,
        "mutation_catalog": MUTATION_CATALOG,
        "sources": sources,
        "c0": {"cases": c0_cases, "aggregates": c0_aggregates},
        "mutants": mutant_records,
        "mutant_aggregates": mutant_aggregates,
        "chart_values": chart_values,
    }

    assert len(payload["sources"]) == 128
    assert len(payload["c0"]["cases"]) == 128
    assert len(payload["mutants"]) == 30
    assert all(len(mutant["cases"]) == 128 for mutant in payload["mutants"])
    assert sum(len(mutant["cases"]) for mutant in payload["mutants"]) == 3840
    assert all(len(chart_values[key]) == 30 for key in (
        "mutant_ids", "accepted_case_count", "fixed_point_case_count",
        "counterexample_case_count"
    ))
    return payload


def main() -> None:
    sys.stdout.buffer.write(canonical_payload_bytes(run_once()))


if __name__ == "__main__":
    main()
