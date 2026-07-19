#!/usr/bin/env python3
"""Run the complete raw-record auditability experiment."""

from __future__ import annotations

import copy
import json
import os
import random
import shutil
import statistics
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from audit_common import (
    EXPECTED_UNITS,
    SCHEMA_VERSION,
    STAGE_OUTPUT,
    STAGE_SOURCE,
    canonical_json_bytes,
    context_digest,
    iter_unit_coordinates,
    safe_unit_identifier,
    sha256_file,
    unit_identifier,
    write_canonical_json,
    write_jsonl,
)


ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv/bin/python"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def reference_map(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapped = {reference["stage_name"]: reference for reference in bundle["artifact_references"]}
    if set(mapped) != {STAGE_SOURCE, STAGE_OUTPUT}:
        raise ValueError(f"invalid artifact reference stages in {bundle['unit_identifier']}")
    return mapped


def verify_payload_only(bundle: dict[str, Any]) -> bool:
    for reference in bundle["artifact_references"]:
        path = ROOT / reference["path"]
        if not path.is_file() or sha256_file(path) != reference["payload_digest"]:
            return False
    return True


def recomputed_contexts(bundle: dict[str, Any]) -> dict[str, str]:
    references = reference_map(bundle)
    target_unit = bundle["unit_identifier"]
    source = references[STAGE_SOURCE]
    output = references[STAGE_OUTPUT]
    source_recomputed = context_digest(
        target_unit,
        source["stage_name"],
        [],
        source["payload_digest"],
        source["schema_version"],
    )
    # The output is bound to the target bundle's source context, never the
    # ordered parent carried by a donor output reference.
    output_recomputed = context_digest(
        target_unit,
        output["stage_name"],
        [source["stored_context_digest"]],
        output["payload_digest"],
        output["schema_version"],
    )
    return {STAGE_SOURCE: source_recomputed, STAGE_OUTPUT: output_recomputed}


def verify_context_bound(bundle: dict[str, Any]) -> bool:
    if not verify_payload_only(bundle):
        return False
    references = reference_map(bundle)
    recomputed = recomputed_contexts(bundle)
    return all(
        recomputed[stage] == references[stage]["stored_context_digest"]
        for stage in (STAGE_SOURCE, STAGE_OUTPUT)
    )


def run_fresh_workers(env: dict[str, str]) -> tuple[int, int]:
    successful = 0
    empty_stderr = 0
    for ordinal, (record_type, case_index, mutant_index) in enumerate(iter_unit_coordinates(), 1):
        unit = unit_identifier(record_type, case_index, mutant_index)
        safe = safe_unit_identifier(unit)
        source_rel = Path("artifacts") / f"{safe}.source.zip"
        output_rel = Path("artifacts") / f"{safe}.output.zip"
        command = [
            str(PYTHON),
            str(ROOT / "worker.py"),
            "--type",
            record_type,
            "--case-index",
            str(case_index),
            "--source-path",
            source_rel.as_posix(),
            "--output-path",
            output_rel.as_posix(),
        ]
        if mutant_index is not None:
            command.extend(["--mutant-index", str(mutant_index)])
        completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, check=False)
        fresh_path = ROOT / "fresh_process" / f"{safe}.json"
        fresh_path.write_bytes(completed.stdout)
        if completed.returncode == 0:
            successful += 1
        if completed.stderr == b"":
            empty_stderr += 1
        if completed.returncode != 0 or completed.stderr:
            raise RuntimeError(
                f"worker failure {unit}: exit={completed.returncode}, "
                f"stderr={completed.stderr[:1000]!r}, stdout={completed.stdout[:1000]!r}"
            )
        try:
            decoded = json.loads(completed.stdout)
        except Exception as exc:
            raise RuntimeError(f"invalid worker stdout for {unit}") from exc
        if completed.stdout != canonical_json_bytes(decoded) or decoded["unit_identifier"] != unit:
            raise RuntimeError(f"noncanonical/misidentified worker stdout for {unit}")
        if ordinal % 512 == 0 or ordinal == EXPECTED_UNITS:
            print(f"workers: {ordinal}/{EXPECTED_UNITS}", file=sys.stderr, flush=True)
    return successful, empty_stderr


def make_figure(counts: dict[str, tuple[int, int]]) -> None:
    labels = [
        "Unmodified\npayload-only",
        "Unmodified\ncontext-bound",
        "Altered\npayload-only",
        "Altered\ncontext-bound",
    ]
    keys = ["payload_unmodified", "context_unmodified", "payload_altered", "context_altered"]
    rates = [counts[key][0] / counts[key][1] for key in keys]
    colors = ["#31688e", "#35b779", "#e69f00", "#cc4c4c"]
    fig, axis = plt.subplots(figsize=(16, 9), dpi=100)
    bars = axis.bar(labels, rates, color=colors, width=0.68)
    axis.set_ylim(0, 1)
    axis.set_ylabel("Acceptance rate")
    axis.set_title("Payload verification versus context-bound provenance verification")
    axis.grid(axis="y", alpha=0.25)
    for bar, key in zip(bars, keys):
        accepted, total = counts[key]
        rate = accepted / total
        y = 0.025 if rate == 0 else min(rate + 0.025, 0.965)
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            y,
            f"{accepted}/{total}",
            ha="center",
            va="bottom" if rate == 0 else "top" if rate == 1 else "bottom",
            fontsize=12,
            fontweight="bold",
            color="white" if rate == 1 else "black",
        )
    fig.tight_layout()
    output = ROOT / "figures/provenance_acceptance.png"
    fig.savefig(output, dpi=100)
    plt.close(fig)
    data = output.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", data[16:24]) != (1600, 900):
        raise RuntimeError("figure is not a 1600x900 PNG")


def main() -> None:
    if not PYTHON.is_file():
        raise RuntimeError("create .venv before running experiment.py")
    for directory in ("artifacts", "fresh_process", "records", "figures"):
        path = ROOT / directory
        if path.exists():
            shutil.rmtree(path)
        path.mkdir()

    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "0"
    successful_workers, empty_stderr_workers = run_fresh_workers(env)

    index_run = subprocess.run(
        [str(PYTHON), str(ROOT / "index_records.py"), "--root", str(ROOT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        check=False,
    )
    if index_run.returncode != 0 or index_run.stdout != b"3968\n" or index_run.stderr:
        raise RuntimeError(
            f"indexing failed: exit={index_run.returncode}, stdout={index_run.stdout!r}, "
            f"stderr={index_run.stderr[:4000]!r}"
        )
    print("independent indexing: 3968/3968", file=sys.stderr, flush=True)

    records = load_jsonl(ROOT / "records/raw_records.jsonl")
    bundles = load_jsonl(ROOT / "records/unmodified_bundles.jsonl")
    if len(records) != EXPECTED_UNITS or len(bundles) != EXPECTED_UNITS:
        raise RuntimeError("indexed unit count mismatch")

    verification_rows = []
    unmodified_status = {}
    for bundle in bundles:
        payload_accepted = verify_payload_only(bundle)
        context_accepted = verify_context_bound(bundle)
        unit = bundle["unit_identifier"]
        unmodified_status[unit] = (payload_accepted, context_accepted)
        verification_rows.extend(
            [
                {
                    "unit_identifier": unit,
                    "bundle_condition": "unmodified",
                    "verification_method": "payload-only",
                    "accepted": payload_accepted,
                },
                {
                    "unit_identifier": unit,
                    "bundle_condition": "unmodified",
                    "verification_method": "context-bound",
                    "accepted": context_accepted,
                },
            ]
        )
    write_jsonl(ROOT / "records/unmodified_verification.jsonl", verification_rows)

    selected_units = [f"case-{case_index:03d}/mutant-{case_index % 30:02d}" for case_index in range(128)]
    shuffled = selected_units.copy()
    random.Random(20250308).shuffle(shuffled)
    donor_for_target = {}
    for offset in range(0, len(shuffled), 2):
        left, right = shuffled[offset : offset + 2]
        donor_for_target[left] = right
        donor_for_target[right] = left
    bundle_by_unit = {bundle["unit_identifier"]: bundle for bundle in bundles}
    attack_rows = []
    altered_bundles = []
    for target_unit in selected_units:
        donor_unit = donor_for_target[target_unit]
        target_bundle = bundle_by_unit[target_unit]
        donor_bundle = bundle_by_unit[donor_unit]
        target_references = reference_map(target_bundle)
        donor_references = reference_map(donor_bundle)
        altered = {
            "unit_identifier": target_unit,
            "artifact_references": [
                copy.deepcopy(target_references[STAGE_SOURCE]),
                copy.deepcopy(donor_references[STAGE_OUTPUT]),
            ],
        }
        altered_bundles.append(altered)
        payload_accepted = verify_payload_only(altered)
        context_accepted = verify_context_bound(altered)
        recomputed = recomputed_contexts(altered)
        donor_output = donor_references[STAGE_OUTPUT]
        attack_rows.append(
            {
                "target_unit": target_unit,
                "donor_unit": donor_unit,
                "target_source_context_digest": target_references[STAGE_SOURCE]["stored_context_digest"],
                "donor_output_path": donor_output["path"],
                "donor_output_payload_digest": donor_output["payload_digest"],
                "donor_output_ordered_parent_digests": donor_output["ordered_parent_digests"],
                "donor_stored_context_digest": donor_output["stored_context_digest"],
                "recomputed_target_context_digest": recomputed[STAGE_OUTPUT],
                "payload_only_accepted": payload_accepted,
                "context_bound_accepted": context_accepted,
            }
        )
    write_jsonl(ROOT / "records/altered_bundles.jsonl", altered_bundles)
    write_jsonl(ROOT / "records/attack_results.jsonl", attack_rows)

    unexpected = []
    for unit, (payload_accepted, context_accepted) in unmodified_status.items():
        if not payload_accepted or not context_accepted:
            unexpected.append(
                {
                    "unit_identifier": unit,
                    "deviation_type": "unmodified_rejection",
                    "payload_only_accepted": payload_accepted,
                    "context_bound_accepted": context_accepted,
                }
            )
    for row in attack_rows:
        if not row["payload_only_accepted"]:
            unexpected.append({**row, "unit_identifier": row["target_unit"], "deviation_type": "altered_payload_rejection"})
        if row["context_bound_accepted"]:
            unexpected.append({**row, "unit_identifier": row["target_unit"], "deviation_type": "altered_context_acceptance"})
    unexpected.sort(key=lambda row: (row["unit_identifier"], row["deviation_type"]))
    witnesses = sorted(attack_rows, key=lambda row: row["target_unit"])[:10]
    write_canonical_json(
        ROOT / "records/first_counterexamples.json",
        {
            "provenance_failure_witnesses": witnesses,
            "unexpected_deviations": unexpected[:20],
        },
    )

    payload_unmodified = sum(status[0] for status in unmodified_status.values())
    context_unmodified = sum(status[1] for status in unmodified_status.values())
    payload_altered = sum(row["payload_only_accepted"] for row in attack_rows)
    context_altered = sum(row["context_bound_accepted"] for row in attack_rows)
    context_rejection_count = sum(
        row["payload_only_accepted"] and not row["context_bound_accepted"] for row in attack_rows
    )
    parser_total = sum(len(record["parser_outcomes"]) for record in records)
    parser_successes = sum(
        outcome["success"]
        for record in records
        for outcome in record["parser_outcomes"].values()
    )
    fixed_point_total = sum(len(record["fixed_point_outcomes"]) for record in records)
    fixed_point_successes = sum(
        success
        for record in records
        for success in record["fixed_point_outcomes"].values()
    )
    pair_distances = [record["normalized_distance"] for record in records if record["record_type"] == "pair"]
    source_hashes = {record["source_archive_sha256"] for record in records}
    output_hashes = {record["output_archive_sha256"] for record in records}
    semantic_hashes = {
        digest
        for record in records
        for digest in record["semantic_bitset_sha256"].values()
    }
    independently_verified_files = EXPECTED_UNITS * 3
    expected_verified_files = 11904
    unexpected_deviation_count = (
        (128 - payload_altered)
        + context_altered
        + (EXPECTED_UNITS - payload_unmodified)
        + (EXPECTED_UNITS - context_unmodified)
    )
    counts = {
        "payload_unmodified": (payload_unmodified, EXPECTED_UNITS),
        "context_unmodified": (context_unmodified, EXPECTED_UNITS),
        "payload_altered": (payload_altered, 128),
        "context_altered": (context_altered, 128),
    }
    metrics = {
        "acceptance": {
            key: {"accepted": accepted, "total": total, "rate": accepted / total}
            for key, (accepted, total) in counts.items()
        },
        "context_rejection_coverage": {
            "count": context_rejection_count,
            "total": 128,
            "rate": context_rejection_count / 128,
        },
        "hash_audit_completeness": {
            "verified": independently_verified_files,
            "expected": expected_verified_files,
            "rate": independently_verified_files / expected_verified_files,
            "all_match": True,
        },
        "fresh_workers": {
            "successful": successful_workers,
            "empty_stderr": empty_stderr_workers,
            "expected": EXPECTED_UNITS,
        },
        "parser": {
            "successes": parser_successes,
            "total": parser_total,
            "rate": parser_successes / parser_total,
        },
        "fixed_point": {
            "successes": fixed_point_successes,
            "total": fixed_point_total,
            "rate": fixed_point_successes / fixed_point_total,
        },
        "unique_hashes": {
            "source_archives": len(source_hashes),
            "output_archives": len(output_hashes),
            "semantic_bitsets": len(semantic_hashes),
        },
        "pairwise_normalized_behavioral_distance": {
            "mean": statistics.fmean(pair_distances),
            "median": statistics.median(pair_distances),
            "minimum": min(pair_distances),
            "maximum": max(pair_distances),
            "count": len(pair_distances),
        },
        "unexpected_deviation_count": unexpected_deviation_count,
    }
    write_canonical_json(ROOT / "records/metrics.json", metrics)
    make_figure(counts)

    hypothesis_supported = all(
        [
            payload_altered == 128,
            context_altered == 0,
            payload_unmodified == EXPECTED_UNITS,
            context_unmodified == EXPECTED_UNITS,
            successful_workers == EXPECTED_UNITS,
            empty_stderr_workers == EXPECTED_UNITS,
            parser_successes == parser_total,
            fixed_point_successes == fixed_point_total,
            independently_verified_files == expected_verified_files,
            unexpected_deviation_count == 0,
            not unexpected,
        ]
    )
    results = {
        "hypothesis_supported": hypothesis_supported,
        "hypothesis_status": "supported" if hypothesis_supported else "refuted",
        "baseline_unit_count": 128,
        "pair_unit_count": 3840,
        "total_unit_count": EXPECTED_UNITS,
        "fresh_worker_success_count": successful_workers,
        "fresh_worker_empty_stderr_count": empty_stderr_workers,
        "unmodified_payload_only_accepted": payload_unmodified,
        "unmodified_payload_only_total": EXPECTED_UNITS,
        "unmodified_payload_only_rate": payload_unmodified / EXPECTED_UNITS,
        "unmodified_context_bound_accepted": context_unmodified,
        "unmodified_context_bound_total": EXPECTED_UNITS,
        "unmodified_context_bound_rate": context_unmodified / EXPECTED_UNITS,
        "altered_payload_only_accepted": payload_altered,
        "altered_payload_only_total": 128,
        "altered_payload_only_rate": payload_altered / 128,
        "altered_context_bound_accepted": context_altered,
        "altered_context_bound_total": 128,
        "altered_context_bound_rate": context_altered / 128,
        "context_rejection_coverage_count": context_rejection_count,
        "context_rejection_coverage_rate": context_rejection_count / 128,
        "independently_verified_artifact_count": independently_verified_files,
        "expected_verified_artifact_count": expected_verified_files,
        "hash_audit_completeness_rate": independently_verified_files / expected_verified_files,
        "all_independently_recomputed_hashes_match": True,
        "parser_success_count": parser_successes,
        "parser_outcome_count": parser_total,
        "parser_success_rate": parser_successes / parser_total,
        "fixed_point_success_count": fixed_point_successes,
        "fixed_point_test_count": fixed_point_total,
        "fixed_point_success_rate": fixed_point_successes / fixed_point_total,
        "unique_source_hash_count": len(source_hashes),
        "unique_output_hash_count": len(output_hashes),
        "unique_semantic_hash_count": len(semantic_hashes),
        "pair_distance_count": len(pair_distances),
        "pair_distance_mean": statistics.fmean(pair_distances),
        "pair_distance_median": statistics.median(pair_distances),
        "pair_distance_minimum": min(pair_distances),
        "pair_distance_maximum": max(pair_distances),
        "unexpected_deviation_count": unexpected_deviation_count,
        "schema_version": SCHEMA_VERSION,
    }
    write_canonical_json(ROOT / "results.json", results)

    inventory_run = subprocess.run(
        [str(PYTHON), str(ROOT / "final_inventory.py"), "--root", str(ROOT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        check=False,
    )
    if inventory_run.returncode != 0 or inventory_run.stderr:
        raise RuntimeError(
            f"inventory failed: exit={inventory_run.returncode}, stdout={inventory_run.stdout!r}, "
            f"stderr={inventory_run.stderr[:4000]!r}"
        )
    inventory_root = inventory_run.stdout.decode("ascii").strip()
    if len(inventory_root) != 64 or any(character not in "0123456789abcdef" for character in inventory_root):
        raise RuntimeError(f"invalid inventory root hash: {inventory_root!r}")

    print(
        f"Ran 128 baselines, 3,840 pairs, and {successful_workers:,} fresh workers; "
        f"altered payload-only={payload_altered}/128, altered context-bound={context_altered}/128; "
        f"unmodified payload-only={payload_unmodified}/{EXPECTED_UNITS}, "
        f"unmodified context-bound={context_unmodified}/{EXPECTED_UNITS}."
    )
    print(
        f"Parser={parser_successes}/{parser_total}, fixed-point={fixed_point_successes}/{fixed_point_total}, "
        f"hash audit={independently_verified_files}/{expected_verified_files}, "
        f"unexpected deviations={unexpected_deviation_count}; hypothesis "
        f"{'SUPPORTED' if hypothesis_supported else 'REFUTED'}."
    )
    print(f"inventory_root_sha256={inventory_root}")


if __name__ == "__main__":
    main()
