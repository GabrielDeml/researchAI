#!/usr/bin/env python3
"""Deterministic relative-path interpretation experiment.

The experiment generates 24 synthetic packages, runs two deliberately different
relative-path interpreters on fresh copies, replaces prose instructions with
absolute execution manifests, and repeats the paired runs.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# Keep matplotlib/font caches inside the reproducible writable workspace.
_WORKSPACE = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(_WORKSPACE / ".matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(_WORKSPACE / ".cache"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


GLOBAL_SEED = 20250308
ROW_COUNT = 64
TIMEOUT_SECONDS = 10
RUNNER_A = "package-relative"
RUNNER_B = "workspace-relative"
ROOT = Path(__file__).resolve().parent
BENCHMARK_ROOT = ROOT / "benchmark"
BASE_ROOT = BENCHMARK_ROOT / "base"
RUNS_ROOT = BENCHMARK_ROOT / "runs"
FIGURES_ROOT = ROOT / "figures"
PYTHON = Path(sys.executable).resolve()

CATEGORY_IDS = {
    "wd": [f"wd{i:02d}" for i in range(1, 9)],
    "input": [f"input{i:02d}" for i in range(1, 9)],
    "output": [f"output{i:02d}" for i in range(1, 9)],
}
PACKAGE_IDS = [package_id for ids in CATEGORY_IDS.values() for package_id in ids]

INSTRUCTIONS = {
    "wd": "Run task.py from the supplied experiment files; it reads data/input.csv and writes results/artifact.json.",
    "input": "Run package/task.py using data as the input root and write the result to the OUTPUT_ARTIFACT path supplied by the runner.",
    "output": "Run package/task.py with the supplied INPUT_FILE and place the result in results.",
}


TASK_TEMPLATE = r'''#!/usr/bin/env python3
import argparse
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

PACKAGE_ID = __PACKAGE_ID__
MODE = __MODE__


def parse_paths():
    parser = argparse.ArgumentParser()
    if MODE == "wd":
        args = parser.parse_args()
        return Path("data/input.csv"), Path("results/artifact.json")
    if MODE == "input":
        parser.add_argument("--input-root", required=True)
        parser.add_argument("--output", required=True)
        args = parser.parse_args()
        return Path(args.input_root) / "input.csv", Path(args.output)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    return Path(args.input), Path(args.output_dir) / "artifact.json"


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=".artifact-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def main():
    try:
        input_path, output_path = parse_paths()
        input_bytes = input_path.read_bytes()
        text = input_bytes.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if reader.fieldnames != ["id", "value"]:
            raise ValueError("input must have exactly the id,value columns")
        rows = [(int(row["id"]), int(row["value"])) for row in reader]
        if len(rows) != 64 or [row_id for row_id, _ in rows] != list(range(64)):
            raise ValueError("input must contain IDs 0 through 63 exactly once in order")
        values = [value for _, value in rows]
        record = {
            "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
            "max_value": max(values),
            "min_value": min(values),
            "package_id": PACKAGE_ID,
            "row_count": len(rows),
            "sum_value": sum(values),
            "weighted_sum": sum((row_id + 1) * value for row_id, value in rows),
        }
        payload = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        atomic_write(output_path, payload)
        return 0
    except Exception as exc:
        print(f"task error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
'''


@dataclass(frozen=True)
class ExecutionSpec:
    cwd: Path
    script: Path
    input_file: Path
    output_parent: Path
    argv: list[str]


def category_for(package_id: str) -> str:
    if package_id.startswith("wd"):
        return "wd"
    if package_id.startswith("input"):
        return "input"
    return "output"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, values: Iterable[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["id", "value"])
        for row_id, value in enumerate(values):
            writer.writerow([row_id, value])


def generate_base_packages() -> None:
    if BENCHMARK_ROOT.exists():
        shutil.rmtree(BENCHMARK_ROOT)
    BASE_ROOT.mkdir(parents=True)

    for package_index, package_id in enumerate(PACKAGE_IDS, start=1):
        category = category_for(package_id)
        sandbox = BASE_ROOT / package_id
        package = sandbox / "package"
        package.mkdir(parents=True)

        rng = random.Random(GLOBAL_SEED + package_index)
        values = [rng.randint(-10000, 10000) for _ in range(ROW_COUNT)]
        write_csv(package / "data" / "input.csv", values)

        within_category = int(package_id[-2:])
        needs_workspace_input = (
            category == "wd" and within_category >= 5
        ) or (
            category == "input" and within_category <= 4
        )
        if needs_workspace_input:
            transformed = [value + 100000 + package_index for value in values]
            write_csv(sandbox / "data" / "input.csv", transformed)

        task_source = TASK_TEMPLATE.replace(
            "__PACKAGE_ID__", repr(package_id)
        ).replace("__MODE__", repr(category))
        (package / "task.py").write_text(task_source, encoding="utf-8", newline="\n")
        (package / "instruction.txt").write_text(
            INSTRUCTIONS[category], encoding="utf-8", newline="\n"
        )


def ambiguous_spec(sandbox: Path, package_id: str, runner: str) -> ExecutionSpec:
    category = category_for(package_id)
    package = sandbox / "package"
    script = package / "task.py"
    package_relative = runner == RUNNER_A
    cwd = package if package_relative else sandbox

    if category == "wd":
        input_file = cwd / "data" / "input.csv"
        output_parent = cwd / "results"
        argv = [str(PYTHON), str(script)]
    elif category == "input":
        input_root = (package if package_relative else sandbox) / "data"
        output_artifact = sandbox / "outputs" / "artifact.json"
        input_file = input_root / "input.csv"
        output_parent = output_artifact.parent
        argv = [
            str(PYTHON),
            str(script),
            "--input-root",
            str(input_root),
            "--output",
            str(output_artifact),
        ]
    else:
        input_file = package / "data" / "input.csv"
        output_parent = (package if package_relative else sandbox) / "results"
        argv = [
            str(PYTHON),
            str(script),
            "--input",
            str(input_file),
            "--output-dir",
            str(output_parent),
        ]
    return ExecutionSpec(cwd, script, input_file, output_parent, argv)


def canonical_protocol(sandbox: Path, package_id: str) -> dict[str, Any]:
    category = category_for(package_id)
    package = sandbox / "package"
    script = (package / "task.py").resolve()
    cwd = package.resolve()

    if category == "wd":
        input_file = (package / "data" / "input.csv").resolve()
        output_artifact = (package / "results" / "artifact.json").resolve()
        argv = [str(PYTHON), str(script)]
        roles = {
            "input_file": str(input_file),
            "output_artifact": str(output_artifact),
        }
    elif category == "input":
        input_root = (package / "data").resolve()
        output_artifact = (sandbox / "outputs" / "artifact.json").resolve()
        argv = [
            str(PYTHON),
            str(script),
            "--input-root",
            str(input_root),
            "--output",
            str(output_artifact),
        ]
        roles = {
            "input_root": str(input_root),
            "output_artifact": str(output_artifact),
        }
    else:
        input_file = (package / "data" / "input.csv").resolve()
        output_dir = (package / "results").resolve()
        argv = [
            str(PYTHON),
            str(script),
            "--input",
            str(input_file),
            "--output-dir",
            str(output_dir),
        ]
        roles = {"input_file": str(input_file), "output_dir": str(output_dir)}

    return {
        "schema_version": 1,
        "cwd": str(cwd),
        "argv": argv,
        "roles": roles,
    }


def materialize_canonical_protocol(sandbox: Path, package_id: str) -> None:
    package = sandbox / "package"
    (package / "instruction.txt").unlink()
    protocol = canonical_protocol(sandbox, package_id)
    (package / "protocol.json").write_text(
        json.dumps(protocol, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def canonical_spec(sandbox: Path, package_id: str) -> ExecutionSpec:
    protocol_path = sandbox / "package" / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol.get("schema_version") != 1:
        raise ValueError(f"invalid schema version in {protocol_path}")
    cwd = Path(protocol["cwd"])
    argv = protocol["argv"]
    roles = protocol["roles"]
    if not isinstance(argv, list) or len(argv) < 2 or not all(
        isinstance(item, str) for item in argv
    ):
        raise ValueError(f"invalid argv in {protocol_path}")
    if not cwd.is_absolute() or not all(Path(item).is_absolute() for item in argv[:2]):
        raise ValueError(f"cwd, executable, and script must be absolute in {protocol_path}")
    if Path(argv[0]) != PYTHON:
        raise ValueError(f"argv must begin with the active absolute sys.executable in {protocol_path}")
    if not isinstance(roles, dict) or not roles or not all(
        isinstance(value, str) and Path(value).is_absolute() for value in roles.values()
    ):
        raise ValueError(f"all role paths must be absolute in {protocol_path}")

    category = category_for(package_id)
    if category == "input":
        input_file = Path(roles["input_root"]) / "input.csv"
        output_parent = Path(roles["output_artifact"]).parent
    elif category == "output":
        input_file = Path(roles["input_file"])
        output_parent = Path(roles["output_dir"])
    else:
        input_file = Path(roles["input_file"])
        output_parent = Path(roles["output_artifact"]).parent
    return ExecutionSpec(cwd, Path(argv[1]), input_file, output_parent, argv)


def artifact_manifest(sandbox: Path) -> list[dict[str, Any]]:
    manifest = []
    for path in sorted(sandbox.rglob("artifact.json")):
        if not path.is_file():
            continue
        manifest.append(
            {
                "path": path.relative_to(sandbox).as_posix(),
                "byte_count": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return manifest


def preflight(spec: ExecutionSpec) -> str | None:
    if not spec.cwd.exists() or not spec.cwd.is_dir():
        return "MISSING_CWD"
    if not spec.script.exists() or not spec.script.is_file():
        return "MISSING_SCRIPT"
    if not spec.input_file.exists() or not spec.input_file.is_file():
        return "MISSING_INPUT"
    try:
        spec.output_parent.mkdir(parents=True, exist_ok=True)
        if not spec.output_parent.is_dir():
            raise NotADirectoryError(spec.output_parent)
    except OSError:
        return "OUTPUT_PARENT_ERROR"
    return None


def execute(sandbox: Path, spec: ExecutionSpec) -> dict[str, Any]:
    error_code = preflight(spec)
    if error_code is not None:
        return {
            "status": "PREFLIGHT_ERROR",
            "error_code": error_code,
            "exit_code": None,
            "artifact_manifest": artifact_manifest(sandbox),
        }

    child_env = os.environ.copy()
    child_env.update({"PYTHONHASHSEED": "0", "LC_ALL": "C", "TZ": "UTC"})
    try:
        completed = subprocess.run(
            spec.argv,
            cwd=spec.cwd,
            env=child_env,
            shell=False,
            timeout=TIMEOUT_SECONDS,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
        status = "SUCCESS" if completed.returncode == 0 else "RUNTIME_ERROR"
        exit_code = completed.returncode
    except subprocess.TimeoutExpired:
        status = "TIMEOUT"
        exit_code = None
    return {
        "status": status,
        "error_code": None,
        "exit_code": exit_code,
        "artifact_manifest": artifact_manifest(sandbox),
    }


def run_one(mode: str, runner: str, package_id: str) -> dict[str, Any]:
    destination = RUNS_ROOT / mode / runner / package_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(BASE_ROOT / package_id, destination)
    if mode == "canonical":
        materialize_canonical_protocol(destination, package_id)
        spec = canonical_spec(destination, package_id)
    else:
        spec = ambiguous_spec(destination, package_id, runner)
    return execute(destination, spec)


def manifest_signature(outcome: dict[str, Any]) -> list[tuple[str, int, str]]:
    return [
        (entry["path"], entry["byte_count"], entry["sha256"])
        for entry in outcome["artifact_manifest"]
    ]


def hash_signature(outcome: dict[str, Any]) -> list[str]:
    return [entry["sha256"] for entry in outcome["artifact_manifest"]]


def first_artifact_value(outcome: dict[str, Any], field: str) -> Any:
    manifest = outcome["artifact_manifest"]
    return manifest[0][field] if manifest else ""


def build_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for mode in ("ambiguous", "canonical"):
        for package_id in PACKAGE_IDS:
            outcome_a = run_one(mode, RUNNER_A, package_id)
            outcome_b = run_one(mode, RUNNER_B, package_id)
            both_success = outcome_a["status"] == outcome_b["status"] == "SUCCESS"
            both_have_artifacts = bool(outcome_a["artifact_manifest"]) and bool(
                outcome_b["artifact_manifest"]
            )
            rows.append(
                {
                    "mode": mode,
                    "package_id": package_id,
                    "category": category_for(package_id),
                    "runner_a_outcome": outcome_a,
                    "runner_b_outcome": outcome_b,
                    "outcome_disagreement": outcome_a != outcome_b,
                    "preflight_disagreement": (
                        outcome_a["status"], outcome_a["error_code"]
                    )
                    != (outcome_b["status"], outcome_b["error_code"]),
                    "artifact_manifest_disagreement": both_success
                    and manifest_signature(outcome_a) != manifest_signature(outcome_b),
                    "artifact_hash_disagreement": both_have_artifacts
                    and hash_signature(outcome_a) != hash_signature(outcome_b),
                    "both_success": both_success,
                    "artifact_hash_agreement": both_have_artifacts
                    and hash_signature(outcome_a) == hash_signature(outcome_b),
                }
            )
    return rows


def selected(rows: list[dict[str, Any]], mode: str, category: str) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row["mode"] == mode
        and (category == "all" or row["category"] == category)
    ]


def compute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "global_seed": GLOBAL_SEED,
        "package_count": len(PACKAGE_IDS),
        "rows_per_input": ROW_COUNT,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }
    boolean_metrics = (
        "outcome_disagreement",
        "preflight_disagreement",
        "artifact_manifest_disagreement",
        "artifact_hash_disagreement",
        "both_success",
        "artifact_hash_agreement",
    )
    for mode in ("ambiguous", "canonical"):
        for category in ("wd", "input", "output", "all"):
            group = selected(rows, mode, category)
            for field in boolean_metrics:
                count = sum(bool(row[field]) for row in group)
                metrics[f"{mode}_{category}_{field}_count"] = count
                metrics[f"{mode}_{category}_{field}_rate"] = count / len(group)

    ambiguous = selected(rows, "ambiguous", "all")
    canonical = selected(rows, "canonical", "all")
    metrics.update(
        {
            "ambiguous_outcome_disagreement_count": sum(
                row["outcome_disagreement"] for row in ambiguous
            ),
            "ambiguous_disagreement_rate": sum(
                row["outcome_disagreement"] for row in ambiguous
            )
            / len(ambiguous),
            "preflight_disagreement_count": sum(
                row["preflight_disagreement"] for row in ambiguous
            ),
            "artifact_manifest_disagreement_count": sum(
                row["artifact_manifest_disagreement"] for row in ambiguous
            ),
            "artifact_hash_disagreement_count": sum(
                row["artifact_hash_disagreement"] for row in ambiguous
            ),
            "canonical_success_count": sum(row["both_success"] for row in canonical),
            "canonical_outcome_agreement_count": sum(
                not row["outcome_disagreement"] for row in canonical
            ),
            "canonical_artifact_hash_agreement_count": sum(
                row["artifact_hash_agreement"] for row in canonical
            ),
        }
    )
    supported = (
        metrics["ambiguous_outcome_disagreement_count"] >= 18
        and metrics["canonical_success_count"] == 24
        and metrics["canonical_outcome_agreement_count"] == 24
        and metrics["canonical_artifact_hash_agreement_count"] == 24
    )
    metrics["hypothesis_supported"] = supported
    metrics["hypothesis_result"] = "SUPPORTED" if supported else "REFUTED"
    return metrics


def write_results_csv(rows: list[dict[str, Any]]) -> None:
    fields = [
        "mode",
        "package_id",
        "category",
        "outcome_disagreement",
        "preflight_disagreement",
        "artifact_manifest_disagreement",
        "artifact_hash_disagreement",
        "both_success",
        "artifact_hash_agreement",
        "runner_a_status",
        "runner_a_error_code",
        "runner_a_exit_code",
        "runner_a_artifact_path",
        "runner_a_artifact_byte_count",
        "runner_a_artifact_sha256",
        "runner_b_status",
        "runner_b_error_code",
        "runner_b_exit_code",
        "runner_b_artifact_path",
        "runner_b_artifact_byte_count",
        "runner_b_artifact_sha256",
        "runner_a_outcome",
        "runner_b_outcome",
    ]
    with (ROOT / "results.csv").open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            a = row["runner_a_outcome"]
            b = row["runner_b_outcome"]
            writer.writerow(
                {
                    "mode": row["mode"],
                    "package_id": row["package_id"],
                    "category": row["category"],
                    "outcome_disagreement": row["outcome_disagreement"],
                    "preflight_disagreement": row["preflight_disagreement"],
                    "artifact_manifest_disagreement": row[
                        "artifact_manifest_disagreement"
                    ],
                    "artifact_hash_disagreement": row["artifact_hash_disagreement"],
                    "both_success": row["both_success"],
                    "artifact_hash_agreement": row["artifact_hash_agreement"],
                    "runner_a_status": a["status"],
                    "runner_a_error_code": a["error_code"],
                    "runner_a_exit_code": a["exit_code"],
                    "runner_a_artifact_path": first_artifact_value(a, "path"),
                    "runner_a_artifact_byte_count": first_artifact_value(
                        a, "byte_count"
                    ),
                    "runner_a_artifact_sha256": first_artifact_value(a, "sha256"),
                    "runner_b_status": b["status"],
                    "runner_b_error_code": b["error_code"],
                    "runner_b_exit_code": b["exit_code"],
                    "runner_b_artifact_path": first_artifact_value(b, "path"),
                    "runner_b_artifact_byte_count": first_artifact_value(
                        b, "byte_count"
                    ),
                    "runner_b_artifact_sha256": first_artifact_value(b, "sha256"),
                    "runner_a_outcome": json.dumps(
                        a, sort_keys=True, separators=(",", ":")
                    ),
                    "runner_b_outcome": json.dumps(
                        b, sort_keys=True, separators=(",", ":")
                    ),
                }
            )


def write_results_json(rows: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    # The workspace contract requires a flat object of scalar values. Preserve a
    # complete scalar JSON representation of each package/mode row alongside the
    # flattened metrics, while results.csv provides conventional tabular rows.
    flat: dict[str, Any] = dict(metrics)
    for row in rows:
        row_key = f"row_{row['mode']}_{row['package_id']}"
        flat[row_key] = json.dumps(row, sort_keys=True, separators=(",", ":"))
    if not all(isinstance(value, (str, int, float, bool)) for value in flat.values()):
        raise TypeError("results.json must contain scalar values only")
    (ROOT / "results.json").write_text(
        json.dumps(flat, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (BENCHMARK_ROOT / "results_detailed.json").write_text(
        json.dumps(rows, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def make_figure(rows: list[dict[str, Any]]) -> None:
    FIGURES_ROOT.mkdir(parents=True, exist_ok=True)
    categories = ["wd", "input", "output", "all"]
    ambiguous_counts = [
        sum(row["outcome_disagreement"] for row in selected(rows, "ambiguous", cat))
        for cat in categories
    ]
    canonical_counts = [
        sum(row["outcome_disagreement"] for row in selected(rows, "canonical", cat))
        for cat in categories
    ]
    totals = [len(selected(rows, "ambiguous", cat)) for cat in categories]
    ambiguous_rates = [count / total for count, total in zip(ambiguous_counts, totals)]
    canonical_rates = [count / total for count, total in zip(canonical_counts, totals)]

    positions = list(range(len(categories)))
    width = 0.36
    fig, ax = plt.subplots(figsize=(9, 5.4))
    bars_ambiguous = ax.bar(
        [position - width / 2 for position in positions],
        ambiguous_rates,
        width,
        label="Ambiguous prose",
        color="#d95f02",
    )
    bars_canonical = ax.bar(
        [position + width / 2 for position in positions],
        canonical_rates,
        width,
        label="Canonical protocol",
        color="#1b9e77",
    )
    ax.axhline(0.75, color="#555555", linestyle="--", linewidth=1.2, label="18/24 threshold")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Outcome disagreement rate")
    ax.set_xlabel("Package category")
    ax.set_title("Runner disagreement before and after absolute-path canonicalization")
    ax.set_xticks(positions, ["Working directory", "Input root", "Output", "All packages"])
    ax.legend(loc="center right")
    ax.grid(axis="y", alpha=0.25)

    for bars, counts in (
        (bars_ambiguous, ambiguous_counts),
        (bars_canonical, canonical_counts),
    ):
        for bar, count, total in zip(bars, counts, totals):
            high_bar = bar.get_height() >= 0.95
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() - 0.03 if high_bar else bar.get_height() + 0.025,
                f"{count}/{total}",
                ha="center",
                va="top" if high_bar else "bottom",
                fontsize=9,
                color="white" if high_bar else "black",
                fontweight="bold" if high_bar else "normal",
            )
    fig.tight_layout()
    fig.savefig(FIGURES_ROOT / "disagreement_rates.png", dpi=160)
    plt.close(fig)


def validate_outputs(rows: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    if len(rows) != 48:
        raise AssertionError(f"expected 48 package/mode rows, got {len(rows)}")
    if metrics["ambiguous_outcome_disagreement_count"] != 24:
        raise AssertionError("fixture invariant failed: ambiguous disagreement should be 24")
    canonical = selected(rows, "canonical", "all")
    for row in canonical:
        for runner_key in ("runner_a_outcome", "runner_b_outcome"):
            outcome = row[runner_key]
            if outcome["status"] != "SUCCESS" or len(outcome["artifact_manifest"]) != 1:
                raise AssertionError(
                    f"canonical run did not yield exactly one successful artifact: "
                    f"{row['package_id']} {runner_key}"
                )
    if not metrics["hypothesis_supported"]:
        raise AssertionError("deterministic fixtures unexpectedly refuted the hypothesis")


def main() -> int:
    random.seed(GLOBAL_SEED)
    generate_base_packages()
    rows = build_rows()
    metrics = compute_metrics(rows)
    write_results_csv(rows)
    write_results_json(rows, metrics)
    make_figure(rows)
    validate_outputs(rows, metrics)

    print("Ran 24 deterministic packages in ambiguous and canonical modes with two independent fixed runners.")
    print(
        "Ambiguous outcome disagreements: "
        f"{metrics['ambiguous_outcome_disagreement_count']}/24 "
        f"({metrics['ambiguous_disagreement_rate']:.1%}); "
        f"preflight={metrics['preflight_disagreement_count']}, "
        f"artifact-manifest={metrics['artifact_manifest_disagreement_count']}, "
        f"artifact-hash={metrics['artifact_hash_disagreement_count']}."
    )
    print(
        "Canonical paired successes/outcome agreements/artifact-hash agreements: "
        f"{metrics['canonical_success_count']}/24, "
        f"{metrics['canonical_outcome_agreement_count']}/24, "
        f"{metrics['canonical_artifact_hash_agreement_count']}/24."
    )
    print(f"Hypothesis: {metrics['hypothesis_result']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
