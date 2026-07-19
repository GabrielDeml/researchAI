"""Run two fresh experiments, render the chart, and atomically publish results."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent
RESULTS_PATH = ROOT / "results.json"
RESULTS_HASH_PATH = ROOT / "results.sha256"
FIGURE_PATH = ROOT / "figures" / "key_result.png"


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
        + b"\n"
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fresh_run() -> tuple[bytes, float]:
    environment = os.environ.copy()
    environment["PYTHONHASHSEED"] = "0"
    start = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, str(ROOT / "run_once.py")],
        cwd=ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    elapsed = time.perf_counter() - start
    if completed.returncode != 0:
        raise RuntimeError(
            f"run_once.py failed ({completed.returncode}): "
            f"{completed.stderr.decode('utf-8', errors='replace')}"
        )
    return completed.stdout, elapsed


def _archive_hashes(payload: dict) -> list[str]:
    hashes = [record["archive_sha256"] for record in payload["c0"]["cases"]]
    hashes.extend(
        record["archive_sha256"]
        for mutant in payload["mutants"]
        for record in mutant["cases"]
    )
    return hashes


def _validate_payload(payload: dict) -> None:
    assert len(payload["sources"]) == 128
    assert len(payload["c0"]["cases"]) == 128
    assert len(payload["mutants"]) == 30
    assert all(len(mutant["cases"]) == 128 for mutant in payload["mutants"])
    assert sum(len(mutant["cases"]) for mutant in payload["mutants"]) == 3840
    chart = payload["chart_values"]
    for key in (
        "mutant_ids",
        "accepted_case_count",
        "fixed_point_case_count",
        "counterexample_case_count",
    ):
        assert len(chart[key]) == 30


def _render_chart(chart: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ids = chart["mutant_ids"]
    accepted = chart["accepted_case_count"]
    fixed = chart["fixed_point_case_count"]
    counterexamples = chart["counterexample_case_count"]
    positions = list(range(len(ids)))
    width = 0.38

    plt.rcParams.update({"font.size": 9})
    figure, (upper, lower) = plt.subplots(2, 1, figsize=(14, 7), sharex=True)
    upper.bar(
        [position - width / 2 for position in positions],
        accepted,
        width,
        color="#4C78A8",
        label="Parser accepted",
    )
    upper.bar(
        [position + width / 2 for position in positions],
        fixed,
        width,
        color="#F58518",
        label="Byte fixed point",
    )
    upper.set_ylim(0, 128)
    upper.set_ylabel("Cases (of 128)")
    upper.set_title("Independent acceptance and canonicalizer fixed points")
    upper.legend(loc="lower right")
    upper.grid(axis="y", color="#D9D9D9", linewidth=0.6)

    lower.bar(positions, counterexamples, width=0.7, color="#E45756")
    lower.axhline(1, color="#222222", linewidth=1.2, linestyle="--", label="Threshold = 1")
    lower.set_ylim(0, 128)
    lower.set_ylabel("Counterexample cases")
    lower.set_xlabel("Lossy canonicalizer mutant")
    lower.set_title("Cases with exact semantic differences")
    lower.set_xticks(positions, ids, rotation=45, ha="right")
    lower.legend(loc="upper right")
    lower.grid(axis="y", color="#D9D9D9", linewidth=0.6)
    figure.tight_layout()
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        FIGURE_PATH,
        dpi=150,
        metadata={"Software": "policy-equivalence-experiment"},
    )
    plt.close(figure)


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _flat_results_bytes(results: dict) -> bytes:
    assert all(
        isinstance(value, (str, int, float, bool)) and value is not None
        for value in results.values()
    ), "results.json must be a flat object of scalar values"
    return _canonical_bytes(results)


def _manifest(figure_bytes: bytes, payload_bytes: bytes, results_size: int) -> dict:
    # The results file's digest is deliberately stored only in results.sha256.
    # Hashing results.sha256 inside results.json would create the same self-reference.
    return {
        "deterministic_payload_manifest_sha256": _sha256(payload_bytes),
        "artifacts": {
            "results.json": {
                "byte_size": results_size,
                "sha256": "recorded-in-results.sha256",
            },
            "results.sha256": {
                "byte_size": 65,
                "sha256": "deferred-because-it-contains-results-json-hash",
            },
            "figures/key_result.png": {
                "byte_size": len(figure_bytes),
                "sha256": _sha256(figure_bytes),
            },
        },
    }


def _validate_completed_results(path: Path) -> None:
    with path.open("r", encoding="utf-8") as stream:
        flat = json.load(stream)
    assert all(
        isinstance(value, (str, int, float, bool)) and value is not None
        for value in flat.values()
    )
    payload = json.loads(flat["deterministic_payload"])
    repeat = json.loads(flat["repeat_run"])
    runtime = json.loads(flat["runtime"])
    chart = json.loads(flat["chart_values"])
    manifest = json.loads(flat["artifact_manifest"])
    _validate_payload(payload)
    assert len(payload["c0"]["cases"]) == 128
    assert len(payload["mutants"]) == 30
    assert all(len(mutant["cases"]) == 128 for mutant in payload["mutants"])
    assert sum(len(mutant["cases"]) for mutant in payload["mutants"]) == 3840
    assert all(len(chart[key]) == 30 for key in (
        "mutant_ids", "accepted_case_count", "fixed_point_case_count",
        "counterexample_case_count"
    ))
    assert repeat["first_payload_sha256"] and repeat["second_payload_sha256"]
    assert all(key in runtime for key in (
        "first_run_seconds", "second_run_seconds", "artifact_generation_seconds",
        "total_elapsed_seconds"
    ))
    assert flat["hypothesis_decision"]
    assert manifest["artifacts"]["results.json"]["byte_size"] == path.stat().st_size


def main() -> None:
    overall_start = time.perf_counter()
    first_bytes, first_elapsed = _fresh_run()
    second_bytes, second_elapsed = _fresh_run()
    first_payload = json.loads(first_bytes)
    second_payload = json.loads(second_bytes)
    _validate_payload(first_payload)
    _validate_payload(second_payload)
    assert _canonical_bytes(first_payload) == first_bytes
    assert _canonical_bytes(second_payload) == second_bytes

    first_hash = _sha256(first_bytes)
    second_hash = _sha256(second_bytes)
    payload_bytes_equal = first_bytes == second_bytes
    archive_hashes_equal = _archive_hashes(first_payload) == _archive_hashes(second_payload)
    repeat_run_equal = payload_bytes_equal and archive_hashes_equal

    chart = first_payload["chart_values"]
    _render_chart(chart)
    figure_bytes = FIGURE_PATH.read_bytes()
    artifact_generation_seconds = time.perf_counter() - overall_start - first_elapsed - second_elapsed
    total_elapsed = time.perf_counter() - overall_start

    c0 = first_payload["c0"]["aggregates"]
    mutants = first_payload["mutant_aggregates"]
    conditions = {
        "c0_parser_acceptance_is_128": c0["parser_acceptance_count"] == 128,
        "c0_byte_fixed_points_is_128": c0["byte_fixed_point_count"] == 128,
        "c0_semantic_preservation_is_128": c0["semantic_equivalence_count"] == 128,
        "mutant_parser_acceptance_is_3840": mutants["parser_acceptance_count"] == 3840,
        "mutant_fixed_points_is_3840": mutants["byte_fixed_point_count"] == 3840,
        "semantically_rejected_mutants_at_least_27": mutants[
            "semantically_rejected_mutant_count"
        ]
        >= 27,
        "repeat_run_equal": repeat_run_equal,
        "runtime_at_most_1800_seconds": total_elapsed <= 1800,
        "artifact_payload_complete": True,
    }
    failed_conditions = [name for name, passed in conditions.items() if not passed]
    decision = "supported" if not failed_conditions else "refuted"
    repeat_run = {
        "repeat_run_equal": repeat_run_equal,
        "payload_bytes_equal": payload_bytes_equal,
        "archive_sha256_values_equal": archive_hashes_equal,
        "first_payload_sha256": first_hash,
        "second_payload_sha256": second_hash,
    }
    runtime = {
        "first_run_seconds": first_elapsed,
        "second_run_seconds": second_elapsed,
        "artifact_generation_seconds": artifact_generation_seconds,
        "total_elapsed_seconds": total_elapsed,
    }
    results = {
        "schema_version": 1,
        "deterministic_payload": first_bytes.decode("utf-8"),
        "deterministic_payload_sha256": first_hash,
        "repeat_run": json.dumps(repeat_run, sort_keys=True, separators=(",", ":")),
        "runtime": json.dumps(runtime, sort_keys=True, separators=(",", ":")),
        "hypothesis_decision": decision,
        "chart_values": json.dumps(chart, sort_keys=True, separators=(",", ":")),
        "artifact_manifest": "",
        "failed_conditions": json.dumps(failed_conditions, separators=(",", ":")),
        "c0_parser_acceptance_count": c0["parser_acceptance_count"],
        "c0_byte_fixed_point_count": c0["byte_fixed_point_count"],
        "c0_semantic_equivalence_count": c0["semantic_equivalence_count"],
        "mutant_parser_acceptance_count": mutants["parser_acceptance_count"],
        "mutant_parser_acceptance_denominator": 3840,
        "mutant_byte_fixed_point_count": mutants["byte_fixed_point_count"],
        "mutant_byte_fixed_point_denominator": 3840,
        "mutant_semantic_equivalence_count": mutants["semantic_equivalence_count"],
        "semantically_rejected_mutant_count": mutants[
            "semantically_rejected_mutant_count"
        ],
        "semantically_rejected_mutant_threshold": 27,
        "c0_case_record_count": len(first_payload["c0"]["cases"]),
        "mutant_record_count": len(first_payload["mutants"]),
        "mutant_case_record_count": sum(
            len(mutant["cases"]) for mutant in first_payload["mutants"]
        ),
        "request_domain_size": first_payload["request_domain_size"],
        "repeat_run_equal": repeat_run_equal,
        "total_elapsed_seconds": total_elapsed,
    }

    # Stabilize the reported results.json byte size (normally two passes).
    reported_size = 0
    for _ in range(10):
        results["artifact_manifest"] = json.dumps(
            _manifest(figure_bytes, first_bytes, reported_size),
            sort_keys=True,
            separators=(",", ":"),
        )
        output = _flat_results_bytes(results)
        if len(output) == reported_size:
            break
        reported_size = len(output)
    else:
        raise AssertionError("results.json size manifest did not stabilize")

    _atomic_write(RESULTS_PATH, output)
    _validate_completed_results(RESULTS_PATH)
    results_digest = _sha256(RESULTS_PATH.read_bytes())
    _atomic_write(RESULTS_HASH_PATH, (results_digest + "\n").encode("ascii"))
    assert RESULTS_HASH_PATH.stat().st_size == 65
    assert RESULTS_HASH_PATH.read_text(encoding="ascii").strip() == _sha256(
        RESULTS_PATH.read_bytes()
    )
    assert FIGURE_PATH.is_file() and FIGURE_PATH.stat().st_size > 0

    print(
        "Ran 128 C0 cases and 3,840 mutant/case comparisons twice; "
        f"C0 checks={c0['parser_acceptance_count']}/"
        f"{c0['byte_fixed_point_count']}/{c0['semantic_equivalence_count']}, "
        f"mutant acceptance={mutants['parser_acceptance_count']}/3840, "
        f"fixed points={mutants['byte_fixed_point_count']}/3840, "
        f"rejected mutants={mutants['semantically_rejected_mutant_count']}/30, "
        f"repeat={repeat_run_equal}, total={total_elapsed:.3f}s: {decision}."
    )


if __name__ == "__main__":
    main()
