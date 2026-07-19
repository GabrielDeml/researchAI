#!/usr/bin/env python3
"""Process exactly one deterministic baseline or pair unit."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from audit_common import (
    baseline_ast,
    canonical_json_bytes,
    deterministic_zip,
    mutant_ast,
    parser_and_fixed_point,
    semantic_bitset,
    sha256_bytes,
    sha256_file,
    unit_identifier,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=("baseline", "pair"), required=True)
    parser.add_argument("--case-index", type=int, required=True)
    parser.add_argument("--mutant-index", type=int)
    parser.add_argument("--source-path", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 0 <= args.case_index < 128:
        raise ValueError("case index out of range")
    if args.type == "pair" and (args.mutant_index is None or not 0 <= args.mutant_index < 30):
        raise ValueError("mutant index out of range")
    if args.type == "baseline" and args.mutant_index is not None:
        raise ValueError("baseline cannot have mutant index")

    unit = unit_identifier(args.type, args.case_index, args.mutant_index)
    baseline = baseline_ast(args.case_index)
    expressions = {"baseline": baseline}
    if args.type == "pair":
        expressions["mutant"] = mutant_ast(args.case_index, args.mutant_index, baseline)

    source_entries = {f"{name}.json": canonical_json_bytes(ast) for name, ast in expressions.items()}
    parser_outcomes = {}
    fixed_point_outcomes = {}
    source_ast_sha256 = {}
    parsed = {}
    for filename, source_bytes in source_entries.items():
        name = filename.removesuffix(".json")
        outcome, fixed, normalized = parser_and_fixed_point(source_bytes)
        parser_outcomes[name] = outcome
        fixed_point_outcomes[name] = fixed
        source_ast_sha256[name] = sha256_bytes(source_bytes)
        if normalized is None:
            raise ValueError("generated expression did not parse")
        parsed[name] = normalized

    baseline_bits = semantic_bitset(parsed["baseline"])
    candidate_bits = (
        baseline_bits if args.type == "baseline" else semantic_bitset(parsed["mutant"])
    )
    hamming_distance = sum((left ^ right).bit_count() for left, right in zip(baseline_bits, candidate_bits))
    normalized_distance = hamming_distance / 256
    semantic_hashes = {
        "baseline": sha256_bytes(baseline_bits),
        "candidate": sha256_bytes(candidate_bits),
    }
    outcome = {
        "unit_identifier": unit,
        "parser_outcomes": parser_outcomes,
        "fixed_point_outcomes": fixed_point_outcomes,
        "semantic_bitset_sha256": semantic_hashes,
        "hamming_distance": hamming_distance,
        "normalized_distance": normalized_distance,
    }

    deterministic_zip(args.source_path, source_entries)
    deterministic_zip(
        args.output_path,
        {
            "outcome.json": canonical_json_bytes(outcome),
            "semantic_baseline.bin": baseline_bits,
            "semantic_candidate.bin": candidate_bits,
        },
    )
    report = {
        "unit_identifier": unit,
        "source_ast_sha256": source_ast_sha256,
        "parser_outcomes": parser_outcomes,
        "fixed_point_outcomes": fixed_point_outcomes,
        "semantic_bitset_sha256": semantic_hashes,
        "hamming_distance": hamming_distance,
        "normalized_distance": normalized_distance,
        "files_written": {
            "source_archive": args.source_path.as_posix(),
            "output_archive": args.output_path.as_posix(),
        },
        "source_archive_sha256": sha256_file(args.source_path),
        "output_archive_sha256": sha256_file(args.output_path),
    }
    sys.stdout.buffer.write(canonical_json_bytes(report))


if __name__ == "__main__":
    main()
