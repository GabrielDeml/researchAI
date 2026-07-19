#!/usr/bin/env python3
"""Deterministic repository/release reconciliation experiment.

This program creates 20 synthetic repository snapshots and 60 release cases,
verifies their cryptographic construction, evaluates three reconciliation
algorithms, and writes machine-readable results plus a summary figure.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import shutil
import struct
import tarfile
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


SEED = 20250308
REPOSITORY_COUNT = 20
FORMAT_VERSION = 1
EXCLUSIONS = [".DS_Store", "build/tmp.bin"]
COMMITTED_SPECS = [
    ("src/main.py", "source"),
    ("schema/schema.json", "schema"),
    ("requirements.lock", "lock_file"),
    ("Makefile", "makefile"),
    ("README.md", "readme"),
    ("mutations/spec.yaml", "mutation_specification"),
]
GENERATED_SPECS = [
    ("outputs/summary.json", "output"),
    ("results/raw.csv", "raw_results"),
    ("logs/run.log", "log"),
    ("figures/result.png", "figure"),
]
CASE_TYPES = ["valid", "omitted", "undeclared_extra", "reclassified"]
ALGORITHMS = ["strict_equality", "committed_subset", "role_aware"]

WORKSPACE_ROOT = Path(__file__).resolve().parent
EXPERIMENT_ROOT = WORKSPACE_ROOT / "artifact_reconciliation_experiment"
REPOSITORIES_ROOT = EXPERIMENT_ROOT / "repositories"
RELEASES_ROOT = EXPERIMENT_ROOT / "releases"
OUTPUTS_ROOT = EXPERIMENT_ROOT / "outputs"
ROOT_FIGURES = WORKSPACE_ROOT / "figures"


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def deterministic_token(repository_index: int, label: str, length: int = 32) -> str:
    material = f"{SEED}:{repository_index}:{label}".encode("utf-8")
    output = bytearray()
    counter = 0
    while len(output) < length:
        output.extend(hashlib.sha256(material + counter.to_bytes(4, "big")).digest())
        counter += 1
    return bytes(output[:length]).hex()


def committed_content(repository_index: int, path: str) -> bytes:
    token = deterministic_token(repository_index, f"committed:{path}", 16)
    if path == "src/main.py":
        text = (
            f'"""Synthetic repository {repository_index}."""\n\n'
            f'SEED = {SEED}\nREPOSITORY_INDEX = {repository_index}\n'
            f'CONTENT_TOKEN = "{token}"\n'
        )
    elif path == "schema/schema.json":
        value = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "additionalProperties": False,
            "properties": {
                "repository_index": {"const": repository_index, "type": "integer"},
                "token": {"const": token, "type": "string"},
            },
            "required": ["repository_index", "token"],
            "title": f"SyntheticRepository{repository_index}",
            "type": "object",
        }
        text = canonical_json_bytes(value).decode("utf-8") + "\n"
    elif path == "requirements.lock":
        text = f"# seed={SEED} repo={repository_index} token={token}\n"
    elif path == "Makefile":
        text = (
            f"# deterministic repository {repository_index}; token={token}\n"
            "all:\n\t@printf 'synthetic artifact\\n'\n"
        )
    elif path == "README.md":
        text = (
            f"# Synthetic Repository {repository_index}\n\n"
            f"Seed: `{SEED}`  \nContent token: `{token}`\n"
        )
    elif path == "mutations/spec.yaml":
        text = (
            f"repository_index: {repository_index}\nseed: {SEED}\n"
            f"mutation_token: {token}\nstrategy: deterministic\n"
        )
    else:
        raise ValueError(f"unknown committed path: {path}")
    return text.encode("utf-8")


def excluded_content(repository_index: int, path: str) -> bytes:
    token = deterministic_token(repository_index, f"excluded:{path}", 24)
    return (
        f"excluded workspace file\nrepository={repository_index}\n"
        f"path={path}\nseed={SEED}\ntoken={token}\n"
    ).encode("utf-8")


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type)
    crc = zlib.crc32(data, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def deterministic_png(repository_index: int, committed_digest_text: str) -> bytes:
    """Write a fixed 48x32 RGB PNG using only the standard library."""
    width, height = 48, 32
    key = hashlib.sha256(
        f"{SEED}:{repository_index}:{committed_digest_text}".encode("utf-8")
    ).digest()
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # PNG filter type: None
        for x in range(width):
            rows.extend(
                (
                    (key[0] + 5 * x + 3 * y) % 256,
                    (key[1] + 7 * x + 11 * y) % 256,
                    (key[2] + (x ^ y) * 13) % 256,
                )
            )
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    compressed = zlib.compress(bytes(rows), level=9)
    return (
        signature
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", compressed)
        + png_chunk(b"IEND", b"")
    )


def generated_content(
    repository_index: int,
    path: str,
    committed_table: list[dict[str, Any]],
) -> bytes:
    digest_text = "".join(entry["sha256"] for entry in committed_table)
    aggregate = sha256_bytes(digest_text.encode("ascii"))
    token = deterministic_token(repository_index, f"generated:{path}:{aggregate}", 20)
    if path == "outputs/summary.json":
        value = {
            "committed_hash_aggregate": aggregate,
            "repository_index": repository_index,
            "seed": SEED,
            "token": token,
        }
        return canonical_json_bytes(value) + b"\n"
    if path == "results/raw.csv":
        return (
            "repository_index,seed,committed_hash_aggregate,token\n"
            f"{repository_index},{SEED},{aggregate},{token}\n"
        ).encode("utf-8")
    if path == "logs/run.log":
        return (
            f"status=complete repository={repository_index} seed={SEED} "
            f"aggregate={aggregate} token={token}\n"
        ).encode("utf-8")
    if path == "figures/result.png":
        return deterministic_png(repository_index, digest_text)
    raise ValueError(f"unknown generated path: {path}")


def table_entry(path: str, data: bytes) -> dict[str, Any]:
    return {"path": path, "size": len(data), "sha256": sha256_bytes(data)}


def commit_identifier(committed_table: list[dict[str, Any]]) -> str:
    normalized = sorted(
        (
            {"path": row["path"], "size": row["size"], "sha256": row["sha256"]}
            for row in committed_table
        ),
        key=lambda row: row["path"],
    )
    return "sha256:" + sha256_bytes(canonical_json_bytes(normalized))


def write_file(root: Path, path: str, data: bytes) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def build_repository(repository_index: int) -> dict[str, Any]:
    snapshot_root = REPOSITORIES_ROOT / f"repo_{repository_index:02d}" / "workspace"
    committed_files: dict[str, bytes] = {}
    committed_roles: dict[str, str] = {}
    for path, _semantic_kind in COMMITTED_SPECS:
        data = committed_content(repository_index, path)
        committed_files[path] = data
        committed_roles[path] = "committed"
        write_file(snapshot_root, path, data)
    excluded_files: dict[str, bytes] = {}
    for path in EXCLUSIONS:
        data = excluded_content(repository_index, path)
        excluded_files[path] = data
        write_file(snapshot_root, path, data)

    committed_table = sorted(
        (table_entry(path, data) for path, data in committed_files.items()),
        key=lambda row: row["path"],
    )
    generated_files: dict[str, bytes] = {}
    generated_roles: dict[str, str] = {}
    for path, _semantic_kind in GENERATED_SPECS:
        generated_files[path] = generated_content(
            repository_index, path, committed_table
        )
        generated_roles[path] = "generated"
    generated_table = sorted(
        (table_entry(path, data) for path, data in generated_files.items()),
        key=lambda row: row["path"],
    )
    return {
        "repository_index": repository_index,
        "committed_files": committed_files,
        "committed_roles": committed_roles,
        "committed_table": committed_table,
        "commit_identifier": commit_identifier(committed_table),
        "excluded_files": excluded_files,
        "generated_files": generated_files,
        "generated_roles": generated_roles,
        "generated_table": generated_table,
    }


def make_tar(payload: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for path in sorted(payload):
            data = payload[path]
            member = tarfile.TarInfo(name=path)
            member.size = len(data)
            member.mtime = 0
            member.uid = 0
            member.gid = 0
            member.uname = ""
            member.gname = ""
            member.mode = 0o644
            member.type = tarfile.REGTYPE
            archive.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


def archive_inventory(tar_bytes: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as archive:
        members = archive.getmembers()
        if any(not member.isfile() for member in members):
            raise AssertionError("payload tar contains a non-regular member")
        paths = [member.name for member in members]
        if len(paths) != len(set(paths)):
            raise AssertionError("payload tar contains duplicate paths")
        if paths != sorted(paths):
            raise AssertionError("payload tar members are not lexicographically ordered")
        for member in members:
            if not (
                member.mtime == 0
                and member.uid == 0
                and member.gid == 0
                and member.uname == ""
                and member.gname == ""
                and member.mode == 0o644
            ):
                raise AssertionError(f"non-canonical tar metadata for {member.name}")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise AssertionError(f"cannot read tar member {member.name}")
            data = extracted.read()
            records.append(table_entry(member.name, data))
    return sorted(records, key=lambda row: row["path"])


def inventory_with_roles(
    payload: dict[str, bytes], roles: dict[str, str]
) -> list[dict[str, Any]]:
    return sorted(
        (
            {**table_entry(path, data), "role": roles[path]}
            for path, data in payload.items()
        ),
        key=lambda row: row["path"],
    )


def create_release(
    repository: dict[str, Any], case_type: str
) -> dict[str, Any]:
    repository_index = repository["repository_index"]
    payload = dict(repository["committed_files"])
    payload.update(repository["generated_files"])
    roles = dict(repository["committed_roles"])
    roles.update(repository["generated_roles"])
    generated_table = [dict(row) for row in repository["generated_table"]]

    if case_type == "undeclared_extra":
        extra_path = f"extras/undeclared_{repository_index}.txt"
        extra_data = (
            f"undeclared extra\nrepository={repository_index}\nseed={SEED}\n"
            f"token={deterministic_token(repository_index, extra_path, 24)}\n"
        ).encode("utf-8")
        payload[extra_path] = extra_data
        roles[extra_path] = "undeclared"
    elif case_type == "omitted":
        selected_path = COMMITTED_SPECS[repository_index % len(COMMITTED_SPECS)][0]
        del payload[selected_path]
        del roles[selected_path]
    elif case_type == "reclassified":
        selected_path = COMMITTED_SPECS[repository_index % len(COMMITTED_SPECS)][0]
        generated_table.append(table_entry(selected_path, payload[selected_path]))
        generated_table.sort(key=lambda row: row["path"])
        roles[selected_path] = "generated"
    elif case_type != "valid":
        raise ValueError(f"unknown case type: {case_type}")

    tar_bytes = make_tar(payload)
    archive_filename = "payload.tar"
    manifest = {
        "format_version": FORMAT_VERSION,
        "repository_index": repository_index,
        "commit_identifier": repository["commit_identifier"],
        "archive_filename": archive_filename,
        "archive_sha256": sha256_bytes(tar_bytes),
        "committed_files": repository["committed_table"],
        "declared_generated": generated_table,
        "exclusions": list(EXCLUSIONS),
        "payload_inventory": inventory_with_roles(payload, roles),
    }
    release_dir = (
        RELEASES_ROOT / f"repo_{repository_index:02d}" / case_type
    )
    release_dir.mkdir(parents=True, exist_ok=True)
    archive_path = release_dir / archive_filename
    manifest_path = release_dir / "release_manifest.json"
    archive_path.write_bytes(tar_bytes)
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    return {
        "repository": repository,
        "repository_index": repository_index,
        "case_type": case_type,
        "ground_truth_valid": case_type == "valid",
        "archive_path": archive_path,
        "manifest_path": manifest_path,
    }


def load_case(case: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    manifest = json.loads(case["manifest_path"].read_text(encoding="utf-8"))
    tar_bytes = case["archive_path"].read_bytes()
    return manifest, tar_bytes


def projected_manifest_inventory(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        (
            {"path": row["path"], "size": row["size"], "sha256": row["sha256"]}
            for row in manifest["payload_inventory"]
        ),
        key=lambda row: row["path"],
    )


def verify_construction(case: dict[str, Any]) -> dict[str, bool]:
    manifest, tar_bytes = load_case(case)
    actual = archive_inventory(tar_bytes)
    actual_by_path = {row["path"]: row for row in actual}
    inventory = projected_manifest_inventory(manifest)
    listed_hashes_correct = all(
        row["path"] in actual_by_path
        and row["size"] == actual_by_path[row["path"]]["size"]
        and row["sha256"] == actual_by_path[row["path"]]["sha256"]
        for row in manifest["payload_inventory"]
    )
    sorted_tables = (
        [row["path"] for row in manifest["committed_files"]]
        == sorted(row["path"] for row in manifest["committed_files"])
        and [row["path"] for row in manifest["declared_generated"]]
        == sorted(row["path"] for row in manifest["declared_generated"])
        and [row["path"] for row in manifest["payload_inventory"]]
        == sorted(row["path"] for row in manifest["payload_inventory"])
    )
    return {
        "archive_digest": manifest["archive_sha256"] == sha256_bytes(tar_bytes),
        "inventory_exact": inventory == actual,
        "listed_hashes": listed_hashes_correct,
        "manifest_canonical": case["manifest_path"].read_bytes()
        == canonical_json_bytes(manifest),
        "manifest_tables_sorted": sorted_tables,
        "exclusions_exact": manifest["exclusions"] == EXCLUSIONS,
    }


def path_sets(case: dict[str, Any]) -> tuple[set[str], set[str]]:
    _, tar_bytes = load_case(case)
    committed = {row["path"] for row in case["repository"]["committed_table"]}
    payload = {row["path"] for row in archive_inventory(tar_bytes)}
    return committed, payload


def role_aware_reconciliation(case: dict[str, Any]) -> tuple[bool, list[str]]:
    manifest, tar_bytes = load_case(case)
    repository = case["repository"]
    actual_inventory = archive_inventory(tar_bytes)
    actual_by_path = {row["path"]: row for row in actual_inventory}
    committed_by_path = {
        row["path"]: row for row in repository["committed_table"]
    }
    generated_by_path = {
        row["path"]: row for row in manifest["declared_generated"]
    }
    committed_paths = set(committed_by_path)
    generated_paths = set(generated_by_path)
    payload_paths = set(actual_by_path)
    inventory_roles = {
        row["path"]: row["role"] for row in manifest["payload_inventory"]
    }
    exclusions = manifest["exclusions"]
    known_uncommitted = set(repository["excluded_files"])

    checks = {
        "commit_identifier": manifest["commit_identifier"]
        == commit_identifier(repository["committed_table"]),
        "archive_digest": manifest["archive_sha256"] == sha256_bytes(tar_bytes),
        "inventory_exact": projected_manifest_inventory(manifest)
        == actual_inventory,
        "committed_files_match": all(
            path in actual_by_path
            and actual_by_path[path]["size"] == expected["size"]
            and actual_by_path[path]["sha256"] == expected["sha256"]
            for path, expected in committed_by_path.items()
        ),
        "generated_files_match": all(
            path in actual_by_path
            and actual_by_path[path]["size"] == expected["size"]
            and actual_by_path[path]["sha256"] == expected["sha256"]
            for path, expected in generated_by_path.items()
        ),
        "generated_disjoint_from_committed": generated_paths.isdisjoint(
            committed_paths
        ),
        "exclusions_known_uncommitted": all(
            path in known_uncommitted for path in exclusions
        ),
        "exclusions_disjoint_from_committed_generated": set(exclusions).isdisjoint(
            committed_paths | generated_paths
        ),
        "exclusions_absent_from_payload": set(exclusions).isdisjoint(payload_paths),
        "payload_equals_committed_union_generated": payload_paths
        == committed_paths | generated_paths
        and all(inventory_roles.get(path) == "committed" for path in committed_paths)
        and all(inventory_roles.get(path) == "generated" for path in generated_paths),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return not failed, failed


def evaluate(cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        committed, payload = path_sets(case)
        predictions = {
            "strict_equality": committed == payload,
            "committed_subset": committed.issubset(payload),
        }
        role_aware_prediction, failed = role_aware_reconciliation(case)
        predictions["role_aware"] = role_aware_prediction
        for algorithm in ALGORITHMS:
            prediction = predictions[algorithm]
            truth = case["ground_truth_valid"]
            rows.append(
                {
                    "repository_index": case["repository_index"],
                    "case_type": case["case_type"],
                    "ground_truth_valid": truth,
                    "algorithm": algorithm,
                    "predicted_acceptance": prediction,
                    "correct": prediction == truth,
                    "failed_role_aware_checks": json.dumps(failed, separators=(",", ":"))
                    if algorithm == "role_aware"
                    else "",
                }
            )

    by_algorithm_case: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for algorithm in ALGORITHMS:
        for case_type in CASE_TYPES:
            selected = [
                row
                for row in rows
                if row["algorithm"] == algorithm and row["case_type"] == case_type
            ]
            accepted = sum(row["predicted_acceptance"] for row in selected)
            by_algorithm_case[algorithm][case_type] = {
                "accepted": accepted,
                "total": len(selected),
                "acceptance_rate": accepted / len(selected),
            }

    role_rows = [row for row in rows if row["algorithm"] == "role_aware"]
    role_valid = [row for row in role_rows if row["ground_truth_valid"]]
    role_invalid = [row for row in role_rows if not row["ground_truth_valid"]]
    invalid_rejections = {
        case_type: sum(
            not row["predicted_acceptance"]
            for row in role_rows
            if row["case_type"] == case_type
        )
        for case_type in ("omitted", "undeclared_extra", "reclassified")
    }
    strict_valid = [
        row
        for row in rows
        if row["algorithm"] == "strict_equality" and row["case_type"] == "valid"
    ]
    subset_extra = [
        row
        for row in rows
        if row["algorithm"] == "committed_subset"
        and row["case_type"] == "undeclared_extra"
    ]
    metrics = {
        "case_counts": dict(Counter(case["case_type"] for case in cases)),
        "total_cases": len(cases),
        "per_algorithm_case_type": by_algorithm_case,
        "role_aware": {
            "correct": sum(row["correct"] for row in role_rows),
            "overall_accuracy": sum(row["correct"] for row in role_rows)
            / len(role_rows),
            "valid_accepted": sum(row["predicted_acceptance"] for row in role_valid),
            "valid_total": len(role_valid),
            "valid_acceptance_rate": sum(
                row["predicted_acceptance"] for row in role_valid
            )
            / len(role_valid),
            "invalid_rejected": sum(
                not row["predicted_acceptance"] for row in role_invalid
            ),
            "invalid_total": len(role_invalid),
            "invalid_rejection_rate": sum(
                not row["predicted_acceptance"] for row in role_invalid
            )
            / len(role_invalid),
            "rejection_counts_by_invalid_subtype": invalid_rejections,
        },
        "strict_equality_valid_rejection_count": sum(
            not row["predicted_acceptance"] for row in strict_valid
        ),
        "strict_equality_valid_total": len(strict_valid),
        "committed_subset_undeclared_extra_acceptance_count": sum(
            row["predicted_acceptance"] for row in subset_extra
        ),
        "committed_subset_undeclared_extra_total": len(subset_extra),
    }
    return rows, metrics


def write_csv(rows: list[dict[str, Any]]) -> None:
    path = OUTPUTS_ROOT / "per_case_results.csv"
    fieldnames = [
        "repository_index",
        "case_type",
        "ground_truth_valid",
        "algorithm",
        "predicted_acceptance",
        "correct",
        "failed_role_aware_checks",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def make_chart(metrics: dict[str, Any]) -> None:
    labels = ["Valid", "Omitted", "Undeclared extra", "Reclassified"]
    x_positions = list(range(len(CASE_TYPES)))
    width = 0.24
    colors = ["#4C78A8", "#F58518", "#54A24B"]
    display_names = ["Strict equality", "Committed subset", "Role-aware"]
    figure, axis = plt.subplots(figsize=(10, 5.5))
    for algorithm_index, (algorithm, display_name, color) in enumerate(
        zip(ALGORITHMS, display_names, colors, strict=True)
    ):
        offset = (algorithm_index - 1) * width
        values = [
            metrics["per_algorithm_case_type"][algorithm][case_type][
                "acceptance_rate"
            ]
            for case_type in CASE_TYPES
        ]
        bars = axis.bar(
            [position + offset for position in x_positions],
            values,
            width,
            label=display_name,
            color=color,
        )
        for bar, case_type in zip(bars, CASE_TYPES, strict=True):
            data = metrics["per_algorithm_case_type"][algorithm][case_type]
            axis.annotate(
                f'{data["accepted"]}/{data["total"]}',
                xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
            )
    axis.set_ylabel("Acceptance rate")
    axis.set_xlabel("Release case type")
    axis.set_title("Release acceptance by reconciliation algorithm")
    axis.set_xticks(x_positions, labels)
    axis.set_ylim(0, 1.12)
    axis.set_yticks([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    axis.grid(axis="y", alpha=0.25)
    axis.legend(loc="upper center", ncol=3, frameon=False)
    figure.tight_layout()
    output_path = OUTPUTS_ROOT / "reconciliation_acceptance.png"
    figure.savefig(
        output_path,
        dpi=150,
        metadata={"Software": "artifact_reconciliation_experiment"},
    )
    plt.close(figure)
    ROOT_FIGURES.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(output_path, ROOT_FIGURES / output_path.name)


def main() -> None:
    random.seed(SEED)
    if EXPERIMENT_ROOT.exists():
        shutil.rmtree(EXPERIMENT_ROOT)
    EXPERIMENT_ROOT.mkdir()
    REPOSITORIES_ROOT.mkdir()
    RELEASES_ROOT.mkdir()
    OUTPUTS_ROOT.mkdir()

    repositories = [build_repository(index) for index in range(REPOSITORY_COUNT)]
    cases: list[dict[str, Any]] = []
    for repository in repositories:
        cases.append(create_release(repository, "valid"))
        cases.append(create_release(repository, "undeclared_extra"))
        index = repository["repository_index"]
        cases.append(
            create_release(repository, "omitted" if index < 10 else "reclassified")
        )

    counts = Counter(case["case_type"] for case in cases)
    assert len(cases) == 60
    assert counts == {
        "valid": 20,
        "undeclared_extra": 20,
        "omitted": 10,
        "reclassified": 10,
    }
    case_lookup = {
        (case["repository_index"], case["case_type"]): case for case in cases
    }
    for index in range(10, 20):
        assert (
            case_lookup[(index, "valid")]["archive_path"].read_bytes()
            == case_lookup[(index, "reclassified")]["archive_path"].read_bytes()
        )

    construction_results = [verify_construction(case) for case in cases]
    assert all(all(checks.values()) for checks in construction_results)
    construction_integrity_passed = sum(
        all(checks.values()) for checks in construction_results
    )

    rows, metrics = evaluate(cases)
    assert len(rows) == 180
    metrics["cryptographic_construction_integrity_passed"] = (
        construction_integrity_passed
    )
    metrics["cryptographic_construction_integrity_total"] = len(cases)
    write_csv(rows)
    (OUTPUTS_ROOT / "metrics.json").write_bytes(canonical_json_bytes(metrics))
    make_chart(metrics)

    role = metrics["role_aware"]
    components = {
        "role_aware_accepts_all_valid": role["valid_accepted"] == 20
        and role["valid_total"] == 20,
        "role_aware_rejects_all_invalid": role["invalid_rejected"] == 40
        and role["invalid_total"] == 40,
        "strict_equality_rejects_all_valid": metrics[
            "strict_equality_valid_rejection_count"
        ]
        == 20
        and metrics["strict_equality_valid_total"] == 20,
        "committed_subset_accepts_all_undeclared_extra": metrics[
            "committed_subset_undeclared_extra_acceptance_count"
        ]
        == 20
        and metrics["committed_subset_undeclared_extra_total"] == 20,
        "cryptographic_construction_integrity": construction_integrity_passed == 60,
    }
    decision = {
        "decision": "supported" if all(components.values()) else "refuted",
        "component_checks": components,
    }
    (OUTPUTS_ROOT / "decision.json").write_bytes(canonical_json_bytes(decision))

    flat_results = {
        "seed": SEED,
        "repository_count": REPOSITORY_COUNT,
        "release_count": len(cases),
        "valid_release_count": counts["valid"],
        "invalid_release_count": len(cases) - counts["valid"],
        "role_aware_correct_count": role["correct"],
        "role_aware_overall_accuracy": role["overall_accuracy"],
        "role_aware_valid_accepted": role["valid_accepted"],
        "role_aware_valid_total": role["valid_total"],
        "role_aware_valid_acceptance_rate": role["valid_acceptance_rate"],
        "role_aware_invalid_rejected": role["invalid_rejected"],
        "role_aware_invalid_total": role["invalid_total"],
        "role_aware_invalid_rejection_rate": role["invalid_rejection_rate"],
        "role_aware_omitted_rejected": role[
            "rejection_counts_by_invalid_subtype"
        ]["omitted"],
        "role_aware_undeclared_extra_rejected": role[
            "rejection_counts_by_invalid_subtype"
        ]["undeclared_extra"],
        "role_aware_reclassified_rejected": role[
            "rejection_counts_by_invalid_subtype"
        ]["reclassified"],
        "strict_equality_valid_rejected": metrics[
            "strict_equality_valid_rejection_count"
        ],
        "committed_subset_undeclared_extra_accepted": metrics[
            "committed_subset_undeclared_extra_acceptance_count"
        ],
        "cryptographic_construction_integrity_passed": construction_integrity_passed,
        "cryptographic_construction_integrity_total": len(cases),
        "hypothesis_supported": decision["decision"] == "supported",
        "decision": decision["decision"],
    }
    for algorithm in ALGORITHMS:
        for case_type in CASE_TYPES:
            aggregate = metrics["per_algorithm_case_type"][algorithm][case_type]
            prefix = f"{algorithm}_{case_type}"
            flat_results[f"{prefix}_accepted"] = aggregate["accepted"]
            flat_results[f"{prefix}_total"] = aggregate["total"]
            flat_results[f"{prefix}_acceptance_rate"] = aggregate[
                "acceptance_rate"
            ]
    for check_name, passed in components.items():
        flat_results[f"component_{check_name}"] = passed
    assert all(
        isinstance(value, (str, int, float, bool)) and value is not None
        for value in flat_results.values()
    )
    (WORKSPACE_ROOT / "results.json").write_bytes(canonical_json_bytes(flat_results))

    print(
        "Ran 20 deterministic repositories and 60 release cases "
        "(180 algorithm evaluations)."
    )
    print(
        f"Role-aware: {role['correct']}/60 correct, "
        f"{role['valid_accepted']}/20 valid accepted, "
        f"{role['invalid_rejected']}/40 invalid rejected."
    )
    print(
        "Subtype rejections: "
        f"omitted={role['rejection_counts_by_invalid_subtype']['omitted']}/10, "
        "undeclared-extra="
        f"{role['rejection_counts_by_invalid_subtype']['undeclared_extra']}/20, "
        "reclassified="
        f"{role['rejection_counts_by_invalid_subtype']['reclassified']}/10."
    )
    print(
        "Baselines: strict rejected "
        f"{metrics['strict_equality_valid_rejection_count']}/20 valid; subset accepted "
        f"{metrics['committed_subset_undeclared_extra_acceptance_count']}/20 "
        "undeclared-extra."
    )
    print(
        f"Construction integrity: {construction_integrity_passed}/60. "
        f"Hypothesis: {decision['decision']}."
    )


if __name__ == "__main__":
    main()
