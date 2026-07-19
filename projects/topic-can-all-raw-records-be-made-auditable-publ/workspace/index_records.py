#!/usr/bin/env python3
"""Independently audit worker artifacts and construct ordered raw records."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from audit_common import (
    SCHEMA_VERSION,
    STAGE_OUTPUT,
    STAGE_SOURCE,
    canonical_json_bytes,
    context_digest,
    iter_unit_coordinates,
    parser_and_fixed_point,
    safe_unit_identifier,
    semantic_bitset,
    sha256_bytes,
    sha256_file,
    unit_identifier,
    validate_zip_metadata,
    write_jsonl,
)


def audit_unit(root: Path, record_type: str, case_index: int, mutant_index: int | None):
    unit = unit_identifier(record_type, case_index, mutant_index)
    safe = safe_unit_identifier(unit)
    source_rel = Path("artifacts") / f"{safe}.source.zip"
    output_rel = Path("artifacts") / f"{safe}.output.zip"
    fresh_rel = Path("fresh_process") / f"{safe}.json"
    source_path = root / source_rel
    output_path = root / output_rel
    fresh_path = root / fresh_rel
    expected_source_names = ["baseline.json"] if record_type == "baseline" else ["baseline.json", "mutant.json"]
    validate_zip_metadata(source_path, expected_source_names)
    validate_zip_metadata(
        output_path,
        ["outcome.json", "semantic_baseline.bin", "semantic_candidate.bin"],
    )

    source_digest = sha256_file(source_path)
    output_digest = sha256_file(output_path)
    fresh_bytes = fresh_path.read_bytes()
    fresh_digest = sha256_bytes(fresh_bytes)
    if canonical_json_bytes(json.loads(fresh_bytes)) != fresh_bytes:
        raise ValueError(f"fresh payload is not canonical: {unit}")
    report = json.loads(fresh_bytes)
    if report["unit_identifier"] != unit:
        raise ValueError(f"fresh unit mismatch: {unit}")
    if report["source_archive_sha256"] != source_digest or report["output_archive_sha256"] != output_digest:
        raise ValueError(f"worker archive hash mismatch: {unit}")
    if report["files_written"] != {
        "source_archive": source_rel.as_posix(),
        "output_archive": output_rel.as_posix(),
    }:
        raise ValueError(f"worker paths mismatch: {unit}")

    parser_outcomes = {}
    fixed_point_outcomes = {}
    source_ast_hashes = {}
    parsed = {}
    with zipfile.ZipFile(source_path, "r") as archive:
        for filename in expected_source_names:
            role = filename.removesuffix(".json")
            data = archive.read(filename)
            parser_outcome, fixed, ast = parser_and_fixed_point(data)
            parser_outcomes[role] = parser_outcome
            fixed_point_outcomes[role] = fixed
            source_ast_hashes[role] = sha256_bytes(data)
            if ast is None:
                raise ValueError(f"source expression failed parser: {unit}:{role}")
            parsed[role] = ast

    baseline_bits = semantic_bitset(parsed["baseline"])
    candidate_bits = baseline_bits if record_type == "baseline" else semantic_bitset(parsed["mutant"])
    hamming_distance = sum((left ^ right).bit_count() for left, right in zip(baseline_bits, candidate_bits))
    normalized_distance = hamming_distance / 256
    semantic_hashes = {
        "baseline": sha256_bytes(baseline_bits),
        "candidate": sha256_bytes(candidate_bits),
    }
    expected_outcome = {
        "unit_identifier": unit,
        "parser_outcomes": parser_outcomes,
        "fixed_point_outcomes": fixed_point_outcomes,
        "semantic_bitset_sha256": semantic_hashes,
        "hamming_distance": hamming_distance,
        "normalized_distance": normalized_distance,
    }
    with zipfile.ZipFile(output_path, "r") as archive:
        stored_outcome = archive.read("outcome.json")
        if stored_outcome != canonical_json_bytes(expected_outcome):
            raise ValueError(f"outcome mismatch/noncanonical: {unit}")
        if archive.read("semantic_baseline.bin") != baseline_bits:
            raise ValueError(f"baseline bitset mismatch: {unit}")
        if archive.read("semantic_candidate.bin") != candidate_bits:
            raise ValueError(f"candidate bitset mismatch: {unit}")
    compared_report = {
        "unit_identifier": report["unit_identifier"],
        "source_ast_sha256": report["source_ast_sha256"],
        "parser_outcomes": report["parser_outcomes"],
        "fixed_point_outcomes": report["fixed_point_outcomes"],
        "semantic_bitset_sha256": report["semantic_bitset_sha256"],
        "hamming_distance": report["hamming_distance"],
        "normalized_distance": report["normalized_distance"],
    }
    expected_report = {
        "unit_identifier": unit,
        "source_ast_sha256": source_ast_hashes,
        "parser_outcomes": parser_outcomes,
        "fixed_point_outcomes": fixed_point_outcomes,
        "semantic_bitset_sha256": semantic_hashes,
        "hamming_distance": hamming_distance,
        "normalized_distance": normalized_distance,
    }
    if compared_report != expected_report:
        raise ValueError(f"fresh report outcome mismatch: {unit}")

    source_context = context_digest(unit, STAGE_SOURCE, [], source_digest)
    output_parents = [source_context]
    output_context = context_digest(unit, STAGE_OUTPUT, output_parents, output_digest)
    record = {
        "unit_identifier": unit,
        "record_type": record_type,
        "case_index": case_index,
        "mutant_index": mutant_index,
        "source_archive_path": source_rel.as_posix(),
        "source_archive_sha256": source_digest,
        "output_archive_path": output_rel.as_posix(),
        "output_archive_sha256": output_digest,
        "fresh_process_path": fresh_rel.as_posix(),
        "fresh_process_sha256": fresh_digest,
        "source_context_digest": source_context,
        "output_context_digest": output_context,
        "ordered_parent_digests": {
            "source_archive": [],
            "output_archive": output_parents,
        },
        "schema_version": SCHEMA_VERSION,
        "parser_outcomes": parser_outcomes,
        "fixed_point_outcomes": fixed_point_outcomes,
        "semantic_bitset_sha256": semantic_hashes,
        "hamming_distance": hamming_distance,
        "normalized_distance": normalized_distance,
    }
    bundle = {
        "unit_identifier": unit,
        "artifact_references": [
            {
                "stage_name": STAGE_SOURCE,
                "path": source_rel.as_posix(),
                "payload_digest": source_digest,
                "stored_context_digest": source_context,
                "ordered_parent_digests": [],
                "schema_version": SCHEMA_VERSION,
            },
            {
                "stage_name": STAGE_OUTPUT,
                "path": output_rel.as_posix(),
                "payload_digest": output_digest,
                "stored_context_digest": output_context,
                "ordered_parent_digests": output_parents,
                "schema_version": SCHEMA_VERSION,
            },
        ],
    }
    return record, bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    records = []
    bundles = []
    for coordinates in iter_unit_coordinates():
        record, bundle = audit_unit(args.root, *coordinates)
        records.append(record)
        bundles.append(bundle)
    write_jsonl(args.root / "records/raw_records.jsonl", records)
    write_jsonl(args.root / "records/unmodified_bundles.jsonl", bundles)
    print(len(records))


if __name__ == "__main__":
    main()
