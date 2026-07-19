#!/usr/bin/env python3
"""Compare raw and canonical ZIP identifiers for equivalent synthetic RO-Crates."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import sys
import zipfile
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


MASTER_SEED = 20250308
PAIR_COUNT = 50
FIXED_TIMESTAMP = "2025-01-01T00:00:00Z"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
RO_CRATE_CONTEXT = "https://w3id.org/ro/crate/1.1/context"
EXECUTABLE_MODE = 0o100755
REGULAR_MODE = 0o100644

WORKSPACE = Path(__file__).resolve().parent
RAW_DIRECTORY = WORKSPACE / "artifacts" / "raw"
CANONICAL_DIRECTORY = WORKSPACE / "artifacts" / "canonical"
RESULTS_DIRECTORY = WORKSPACE / "results"
FIGURES_DIRECTORY = WORKSPACE / "figures"

CSV_COLUMNS = [
    "pair_index",
    "semantic_validation_passed",
    "raw_id_A",
    "raw_id_B",
    "raw_ids_different",
    "canonical_id_A",
    "canonical_id_B",
    "canonical_ids_equal",
    "raw_size_A",
    "raw_size_B",
    "canonical_size_A",
    "canonical_size_B",
]

RUN_SCRIPT = b'''#!/usr/bin/env python3
import json
from pathlib import Path

input_data = json.loads(Path("data/input.json").read_text(encoding="utf-8"))
result = {
    "pair_index": input_data["pair_index"],
    "sum_squares": sum(value * value for value in input_data["values"]),
    "generated_at": "2025-01-01T00:00:00Z",
}
Path("outputs").mkdir(exist_ok=True)
Path("outputs/results.json").write_text(
    json.dumps(result, sort_keys=True, separators=(",", ":")) + "\\n",
    encoding="utf-8",
)
'''

REQUIREMENTS_LOCK = (
    b"# No third-party runtime dependencies; Python standard library only\n"
)


def compact_json_line(value: Any) -> bytes:
    """Serialize deterministic compact JSON with one trailing newline."""
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_non_metadata_files(pair_index: int) -> dict[str, bytes]:
    values = [pair_index, pair_index + 1, pair_index + 2]
    sum_squares = sum(value * value for value in values)
    return {
        "src/run.py": RUN_SCRIPT,
        "data/input.json": compact_json_line(
            {"pair_index": pair_index, "values": values}
        ),
        "outputs/results.json": compact_json_line(
            {
                "pair_index": pair_index,
                "sum_squares": sum_squares,
                "generated_at": FIXED_TIMESTAMP,
            }
        ),
        "requirements-lock.txt": REQUIREMENTS_LOCK,
        "environment.json": compact_json_line(
            {
                "python": "3.12.8",
                "implementation": "CPython",
                "os": "any",
                "architecture": "any",
            }
        ),
    }


def make_metadata(pair_index: int, files: dict[str, bytes]) -> dict[str, Any]:
    file_paths = sorted(files)
    graph: list[dict[str, Any]] = [
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "about": {"@id": "./"},
        },
        {
            "@id": "./",
            "@type": "Dataset",
            "name": f"Synthetic reproducibility bundle {pair_index}",
            "datePublished": FIXED_TIMESTAMP,
            "hasPart": [{"@id": path} for path in file_paths],
        },
    ]
    for path in file_paths:
        contents = files[path]
        graph.append(
            {
                "@id": path,
                "@type": "File",
                "contentSize": len(contents),
                "sha256": sha256_hex(contents),
            }
        )

    metadata = {"@context": RO_CRATE_CONTEXT, "@graph": graph}
    entity_ids = [entity["@id"] for entity in graph]
    if len(entity_ids) != len(set(entity_ids)):
        raise AssertionError("metadata contains duplicate @id values")
    return metadata


def is_id_reference_array(value: list[Any]) -> bool:
    return bool(value) and all(
        isinstance(item, dict)
        and set(item) == {"@id"}
        and isinstance(item["@id"], str)
        for item in value
    )


def shuffled_json(value: Any, rng: random.Random, parent_key: str | None = None) -> Any:
    """Rebuild JSON recursively while randomizing all permitted ordering."""
    if isinstance(value, dict):
        keys = list(value)
        rng.shuffle(keys)
        return {key: shuffled_json(value[key], rng, key) for key in keys}
    if isinstance(value, list):
        rebuilt = [shuffled_json(item, rng) for item in value]
        if parent_key == "@graph" or is_id_reference_array(rebuilt):
            rng.shuffle(rebuilt)
        return rebuilt
    return value


def normalized_json(value: Any, parent_key: str | None = None) -> Any:
    """Apply the experiment's JSON normalization rules."""
    if isinstance(value, dict):
        return {
            key: normalized_json(value[key], key)
            for key in sorted(value)
        }
    if isinstance(value, list):
        rebuilt = [normalized_json(item) for item in value]
        if parent_key == "@graph":
            if not all(
                isinstance(item, dict) and isinstance(item.get("@id"), str)
                for item in rebuilt
            ):
                raise ValueError("every @graph entity must have a string @id")
            return sorted(rebuilt, key=lambda item: item["@id"])
        if is_id_reference_array(rebuilt):
            return sorted(rebuilt, key=lambda item: item["@id"])
        return rebuilt
    return value


def metadata_serializations(
    metadata: dict[str, Any], pair_index: int
) -> tuple[bytes, bytes]:
    rng_a = random.Random(MASTER_SEED + 2 * pair_index)
    rng_b = random.Random(MASTER_SEED + 2 * pair_index + 1)
    shuffled_a = shuffled_json(metadata, rng_a)
    shuffled_b = shuffled_json(metadata, rng_b)

    graph_a = [entity["@id"] for entity in shuffled_a["@graph"]]
    graph_b = [entity["@id"] for entity in shuffled_b["@graph"]]
    if graph_a == graph_b:
        shuffled_b["@graph"] = (
            shuffled_b["@graph"][1:] + shuffled_b["@graph"][:1]
        )
        graph_b = [entity["@id"] for entity in shuffled_b["@graph"]]
    if graph_a == graph_b:
        raise AssertionError("A and B @graph orders must differ")

    compact_variant = rng_a.choice(("A", "B"))
    pretty_rng = rng_b if compact_variant == "A" else rng_a
    pretty_indent = pretty_rng.choice((2, 4))

    compact_options = {
        "ensure_ascii": False,
        "allow_nan": False,
        "separators": (",", ":"),
    }
    pretty_options = {
        "ensure_ascii": False,
        "allow_nan": False,
        "indent": pretty_indent,
    }
    if compact_variant == "A":
        bytes_a = json.dumps(shuffled_a, **compact_options).encode("utf-8")
        bytes_b = (json.dumps(shuffled_b, **pretty_options) + "\n").encode("utf-8")
    else:
        bytes_a = (json.dumps(shuffled_a, **pretty_options) + "\n").encode("utf-8")
        bytes_b = json.dumps(shuffled_b, **compact_options).encode("utf-8")

    if bytes_a == bytes_b:
        raise AssertionError("metadata serializations must differ")
    return bytes_a, bytes_b


def validate_semantic_identity(
    metadata_a: bytes,
    metadata_b: bytes,
    files_a: dict[str, bytes],
    files_b: dict[str, bytes],
) -> bool:
    try:
        parsed_a = json.loads(metadata_a.decode("utf-8"))
        parsed_b = json.loads(metadata_b.decode("utf-8"))
        metadata_equal = normalized_json(parsed_a) == normalized_json(parsed_b)
        files_equal = files_a.keys() == files_b.keys() and all(
            files_a[path] == files_b[path] for path in sorted(files_a)
        )
        return metadata_equal and files_equal
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return False


def zip_info(path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(filename=path, date_time=ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_STORED
    info.comment = b""
    info.extra = b""
    info.create_system = 3
    mode = EXECUTABLE_MODE if path == "src/run.py" else REGULAR_MODE
    info.external_attr = mode << 16
    return info


def build_zip(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(
        output, mode="w", compression=zipfile.ZIP_STORED, allowZip64=True
    ) as archive:
        archive.comment = b""
        for path in sorted(files):
            archive.writestr(zip_info(path), files[path])
    return output.getvalue()


def normalize_archive_path(path: str) -> str:
    path_with_slashes = path.replace("\\", "/")
    if path_with_slashes.startswith("/"):
        raise ValueError(f"absolute archive path is forbidden: {path!r}")
    components: list[str] = []
    for component in path_with_slashes.split("/"):
        if component in ("", "."):
            continue
        if component == "..":
            raise ValueError(f"parent path component is forbidden: {path!r}")
        components.append(component)
    if not components:
        raise ValueError(f"archive path normalizes to empty: {path!r}")
    return "/".join(components)


def canonicalize_zip(raw_zip: bytes) -> bytes:
    normalized_files: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(raw_zip), mode="r") as archive:
        for member in archive.infolist():
            path = normalize_archive_path(member.filename)
            if path in normalized_files:
                raise ValueError(f"duplicate normalized archive path: {path!r}")
            contents = archive.read(member)
            if path == "ro-crate-metadata.json":
                parsed = json.loads(contents.decode("utf-8"))
                contents = (
                    json.dumps(
                        normalized_json(parsed),
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                        allow_nan=False,
                    )
                    + "\n"
                ).encode("utf-8")
            normalized_files[path] = contents
    if "ro-crate-metadata.json" not in normalized_files:
        raise ValueError("archive is missing ro-crate-metadata.json")
    return build_zip(normalized_files)


def identifier(archive_bytes: bytes) -> str:
    return f"sha256:{sha256_hex(archive_bytes)}"


def write_deduplicated_canonical_zip(archive_bytes: bytes) -> Path:
    digest = sha256_hex(archive_bytes)
    destination = CANONICAL_DIRECTORY / f"{digest}.zip"
    if destination.exists():
        if destination.read_bytes() != archive_bytes:
            raise AssertionError("digest collision produced non-identical ZIP bytes")
    else:
        destination.write_bytes(archive_bytes)
    return destination


def prepare_directories() -> None:
    for directory in (
        RAW_DIRECTORY,
        CANONICAL_DIRECTORY,
        RESULTS_DIRECTORY,
        FIGURES_DIRECTORY,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    for directory in (RAW_DIRECTORY, CANONICAL_DIRECTORY):
        for old_zip in sorted(directory.glob("*.zip")):
            old_zip.unlink()


def write_pair_metrics(rows: list[dict[str, Any]]) -> None:
    destination = RESULTS_DIRECTORY / "pair_metrics.csv"
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def create_figure(raw_count: int, canonical_count: int) -> None:
    values = [100.0 * raw_count / PAIR_COUNT, 100.0 * canonical_count / PAIR_COUNT]
    labels = ["Raw ZIP pairs fragmented", "Canonical pairs preserved"]
    colors = ["#D55E00", "#0072B2"]

    figure, axis = plt.subplots(figsize=(8, 5), dpi=150)
    bars = axis.bar(labels, values, color=colors, width=0.6)
    axis.set_ylim(0, 100)
    axis.set_ylabel("Pairs (%)")
    axis.set_title("Raw versus canonical ZIP hash identity")
    axis.axhline(90, color="black", linestyle="--", linewidth=1)
    axis.text(
        0.02,
        91.5,
        "raw fragmentation threshold",
        transform=axis.get_yaxis_transform(),
        fontsize=9,
        va="bottom",
    )
    annotations = [
        f"{raw_count}/{PAIR_COUNT}",
        f"{canonical_count}/{PAIR_COUNT}\n50/50 required",
    ]
    for bar, annotation in zip(bars, annotations, strict=True):
        axis.annotate(
            annotation,
            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, -5 if bar.get_height() == 100 else 5),
            textcoords="offset points",
            ha="center",
            va="top" if bar.get_height() == 100 else "bottom",
            color="white" if bar.get_height() == 100 else "black",
            fontweight="bold",
        )
    figure.tight_layout()
    save_options = {
        "dpi": 150,
        "metadata": {"Software": "matplotlib 3.9.2"},
    }
    figure.savefig(RESULTS_DIRECTORY / "hash_identity_result.png", **save_options)
    figure.savefig(FIGURES_DIRECTORY / "hash_identity_result.png", **save_options)
    plt.close(figure)


def run_experiment() -> dict[str, Any]:
    prepare_directories()
    rows: list[dict[str, Any]] = []

    for pair_index in range(PAIR_COUNT):
        files_a = dict(make_non_metadata_files(pair_index))
        files_b = dict(make_non_metadata_files(pair_index))
        metadata = make_metadata(pair_index, files_a)
        metadata_a, metadata_b = metadata_serializations(metadata, pair_index)

        semantic_validation_passed = validate_semantic_identity(
            metadata_a, metadata_b, files_a, files_b
        )
        if not semantic_validation_passed:
            raise AssertionError(f"semantic validation failed for pair {pair_index}")

        raw_files_a = {**files_a, "ro-crate-metadata.json": metadata_a}
        raw_files_b = {**files_b, "ro-crate-metadata.json": metadata_b}
        raw_zip_a = build_zip(raw_files_a)
        raw_zip_b = build_zip(raw_files_b)

        raw_path_a = RAW_DIRECTORY / f"pair_{pair_index:02d}_A.zip"
        raw_path_b = RAW_DIRECTORY / f"pair_{pair_index:02d}_B.zip"
        raw_path_a.write_bytes(raw_zip_a)
        raw_path_b.write_bytes(raw_zip_b)

        raw_id_a = identifier(raw_zip_a)
        raw_id_b = identifier(raw_zip_b)
        canonical_zip_a = canonicalize_zip(raw_zip_a)
        canonical_zip_b = canonicalize_zip(raw_zip_b)
        canonical_id_a = identifier(canonical_zip_a)
        canonical_id_b = identifier(canonical_zip_b)
        write_deduplicated_canonical_zip(canonical_zip_a)
        write_deduplicated_canonical_zip(canonical_zip_b)

        rows.append(
            {
                "pair_index": pair_index,
                "semantic_validation_passed": semantic_validation_passed,
                "raw_id_A": raw_id_a,
                "raw_id_B": raw_id_b,
                "raw_ids_different": raw_id_a != raw_id_b,
                "canonical_id_A": canonical_id_a,
                "canonical_id_B": canonical_id_b,
                "canonical_ids_equal": canonical_id_a == canonical_id_b,
                "raw_size_A": len(raw_zip_a),
                "raw_size_B": len(raw_zip_b),
                "canonical_size_A": len(canonical_zip_a),
                "canonical_size_B": len(canonical_zip_b),
            }
        )

    semantic_validation_count = sum(
        bool(row["semantic_validation_passed"]) for row in rows
    )
    raw_fragmentation_count = sum(bool(row["raw_ids_different"]) for row in rows)
    canonical_preservation_count = sum(
        bool(row["canonical_ids_equal"]) for row in rows
    )
    unique_raw_identifiers = len(
        {row[key] for row in rows for key in ("raw_id_A", "raw_id_B")}
    )
    unique_canonical_identifiers = len(
        {
            row[key]
            for row in rows
            for key in ("canonical_id_A", "canonical_id_B")
        }
    )

    all_semantic_validations_passed = semantic_validation_count == PAIR_COUNT
    raw_fragmentation_threshold_passed = raw_fragmentation_count >= 45
    canonical_preservation_requirement_passed = (
        canonical_preservation_count == PAIR_COUNT
    )
    hypothesis_supported = (
        all_semantic_validations_passed
        and raw_fragmentation_threshold_passed
        and canonical_preservation_requirement_passed
    )
    hypothesis_decision = "supported" if hypothesis_supported else "refuted"

    aggregate_metrics = {
        "pair_count": PAIR_COUNT,
        "semantic_validation_count": semantic_validation_count,
        "semantic_validation_rate": semantic_validation_count / PAIR_COUNT,
        "raw_fragmentation_count": raw_fragmentation_count,
        "raw_fragmentation_rate": raw_fragmentation_count / PAIR_COUNT,
        "raw_fragmentation_required_count": 45,
        "raw_fragmentation_threshold": 0.90,
        "canonical_preservation_count": canonical_preservation_count,
        "canonical_preservation_rate": canonical_preservation_count / PAIR_COUNT,
        "canonical_preservation_required_count": PAIR_COUNT,
        "canonical_preservation_required_rate": 1.0,
        "unique_raw_identifiers": unique_raw_identifiers,
        "unique_canonical_identifiers": unique_canonical_identifiers,
    }
    conditions = {
        "all_semantic_validations_passed": all_semantic_validations_passed,
        "raw_fragmentation_threshold_passed": raw_fragmentation_threshold_passed,
        "canonical_preservation_requirement_passed": (
            canonical_preservation_requirement_passed
        ),
    }
    summary = {
        "aggregate_metrics": aggregate_metrics,
        "experiment_timestamp": FIXED_TIMESTAMP,
        "hypothesis": {
            "component_conditions": conditions,
            "decision": hypothesis_decision,
            "supported": hypothesis_supported,
        },
        "master_random_seed": MASTER_SEED,
        "pair_metrics": rows,
    }
    (RESULTS_DIRECTORY / "summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    write_pair_metrics(rows)

    raw_sizes = [
        int(row[key]) for row in rows for key in ("raw_size_A", "raw_size_B")
    ]
    canonical_sizes = [
        int(row[key])
        for row in rows
        for key in ("canonical_size_A", "canonical_size_B")
    ]
    flat_results = {
        "experiment_timestamp": FIXED_TIMESTAMP,
        "master_random_seed": MASTER_SEED,
        "pair_count": PAIR_COUNT,
        "variant_archive_count": 2 * PAIR_COUNT,
        "semantic_validation_count": semantic_validation_count,
        "semantic_validation_rate": semantic_validation_count / PAIR_COUNT,
        "all_semantic_validations_passed": all_semantic_validations_passed,
        "raw_fragmentation_count": raw_fragmentation_count,
        "raw_fragmentation_rate": raw_fragmentation_count / PAIR_COUNT,
        "raw_fragmentation_required_count": 45,
        "raw_fragmentation_threshold": 0.90,
        "raw_fragmentation_threshold_passed": raw_fragmentation_threshold_passed,
        "canonical_preservation_count": canonical_preservation_count,
        "canonical_preservation_rate": canonical_preservation_count / PAIR_COUNT,
        "canonical_preservation_required_count": PAIR_COUNT,
        "canonical_preservation_required_rate": 1.0,
        "canonical_preservation_requirement_passed": (
            canonical_preservation_requirement_passed
        ),
        "unique_raw_identifiers": unique_raw_identifiers,
        "unique_canonical_identifiers": unique_canonical_identifiers,
        "raw_archive_size_min_bytes": min(raw_sizes),
        "raw_archive_size_max_bytes": max(raw_sizes),
        "canonical_archive_size_min_bytes": min(canonical_sizes),
        "canonical_archive_size_max_bytes": max(canonical_sizes),
        "canonical_pair_sizes_all_equal": all(
            row["canonical_size_A"] == row["canonical_size_B"] for row in rows
        ),
        "hypothesis_supported": hypothesis_supported,
        "hypothesis_decision": hypothesis_decision,
    }
    (WORKSPACE / "results.json").write_text(
        json.dumps(
            flat_results,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    create_figure(raw_fragmentation_count, canonical_preservation_count)
    return flat_results


def main() -> int:
    try:
        results = run_experiment()
    except Exception as error:
        error_results = {
            "error": f"{type(error).__name__}: {error}",
            "experiment_timestamp": FIXED_TIMESTAMP,
            "hypothesis_decision": "not_completed",
            "hypothesis_supported": False,
        }
        (WORKSPACE / "results.json").write_text(
            json.dumps(error_results, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            "Experiment failed: "
            f"{error_results['error']}; hypothesis could not be evaluated.",
            file=sys.stderr,
        )
        raise

    print(
        "Ran 50 deterministic pairs (100 raw RO-Crate ZIP variants): "
        f"semantic validation {results['semantic_validation_count']}/50, "
        f"raw fragmentation {results['raw_fragmentation_count']}/50 "
        f"({results['raw_fragmentation_rate']:.0%}), canonical preservation "
        f"{results['canonical_preservation_count']}/50 "
        f"({results['canonical_preservation_rate']:.0%}), unique IDs "
        f"raw={results['unique_raw_identifiers']} and "
        f"canonical={results['unique_canonical_identifiers']}. "
        f"Hypothesis {results['hypothesis_decision']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
