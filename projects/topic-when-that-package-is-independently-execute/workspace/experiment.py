#!/usr/bin/env python3
"""Run the locked-image CSV provenance and digest reproduction experiment.

This script is deliberately fail-closed. A missing/malformed manifest, missing
container engine, missing strace, or failed parser controls yields ``invalid``;
none of those conditions is silently converted into a hypothesis refutation.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parent
RUNTIME_CACHE = ROOT / ".runtime_cache"
RUNTIME_CACHE.mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(RUNTIME_CACHE / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(RUNTIME_CACHE / "xdg"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from trace_parser import analyze_trace_set


MANIFEST_PATH = ROOT / "experiment_manifest.json"
FIGURE_PATH = ROOT / "figures" / "provenance_digest_matrix.png"
CSV_FIELDS = [
    "run",
    "target",
    "exit_status",
    "created_after_start",
    "wrote_positive_bytes",
    "write_before_read",
    "first_create_time",
    "first_write_time",
    "first_read_time",
    "file_size_bytes",
    "observed_sha256",
    "expected_sha256",
    "digest_match",
    "target_run_pass",
]
ENVIRONMENT = {
    "PYTHONHASHSEED": "0",
    "TZ": "UTC",
    "LC_ALL": "C.UTF-8",
    "LANG": "C.UTF-8",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}
STRACE_ARGS = [
    "-ff",
    "-ttt",
    "-yy",
    "-s",
    "4096",
    "-e",
    "trace=%file,read,write,pread64,pwrite64,readv,writev,close,dup,dup2,dup3,rename,renameat,renameat2",
]
IMAGE_RE = re.compile(r"^\S+@sha256:[0-9a-f]{64}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class InvalidExperiment(RuntimeError):
    pass


def run_command(
    argv: Sequence[str],
    *,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    if stdout_path is None and stderr_path is None:
        return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
    stdout_path = stdout_path or Path(os.devnull)
    stderr_path = stderr_path or Path(os.devnull)
    with stdout_path.open("w", encoding="utf-8", newline="\n") as stdout, stderr_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as stderr:
        result = subprocess.run(argv, text=True, stdout=stdout, stderr=stderr, timeout=timeout, check=False)
    return result


def validate_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise InvalidExperiment("experiment_manifest.json is missing from the workspace root")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidExperiment(f"experiment_manifest.json is unreadable or invalid JSON: {exc}") from exc
    required = {"image_digest", "command", "output_directory", "targets"}
    if not isinstance(manifest, dict) or set(manifest) != required:
        actual = sorted(manifest) if isinstance(manifest, dict) else type(manifest).__name__
        raise InvalidExperiment(f"manifest must have exactly {sorted(required)}; found {actual}")
    image = manifest["image_digest"]
    if not isinstance(image, str) or not IMAGE_RE.fullmatch(image):
        raise InvalidExperiment("image_digest must be an immutable OCI reference ending in @sha256:<64 lowercase hex>")
    command = manifest["command"]
    if not isinstance(command, list) or not command or not all(isinstance(arg, str) and arg for arg in command):
        raise InvalidExperiment("command must be a nonempty argv array of nonempty strings")
    output = manifest["output_directory"]
    if not isinstance(output, str) or not PurePosixPath(output).is_absolute():
        raise InvalidExperiment("output_directory must be an absolute POSIX path")
    output_path = PurePosixPath(output)
    if output_path.parent != PurePosixPath("/capture"):
        raise InvalidExperiment(
            "output_directory parent must be /capture so the sole writable bind also receives /capture/trace"
        )
    targets = manifest["targets"]
    if not isinstance(targets, list) or len(targets) != 3:
        raise InvalidExperiment("targets must be an array of exactly three objects")
    seen: set[str] = set()
    for index, target in enumerate(targets):
        if not isinstance(target, dict) or set(target) != {"path", "expected_sha256"}:
            raise InvalidExperiment(f"target {index} must contain exactly path and expected_sha256")
        relative = target["path"]
        digest = target["expected_sha256"]
        if not isinstance(relative, str) or not relative:
            raise InvalidExperiment(f"target {index} path must be a nonempty string")
        rel_path = PurePosixPath(relative)
        if rel_path.is_absolute() or ".." in rel_path.parts or relative in {".", ""}:
            raise InvalidExperiment(f"target {index} path escapes or does not name a file: {relative!r}")
        resolved = PurePosixPath(os.path.normpath(str(output_path / rel_path)))
        try:
            resolved.relative_to(output_path)
        except ValueError as exc:
            raise InvalidExperiment(f"target {index} escapes output_directory: {relative!r}") from exc
        if str(rel_path) in seen:
            raise InvalidExperiment(f"duplicate target path: {relative!r}")
        seen.add(str(rel_path))
        if not isinstance(digest, str) or not SHA_RE.fullmatch(digest):
            raise InvalidExperiment(f"target {index} expected_sha256 must be 64 lowercase hexadecimal characters")
    return manifest


def detect_engine() -> tuple[str | None, str, str | None]:
    diagnostics: list[str] = []
    for name in ("docker", "podman"):
        executable = shutil.which(name)
        if not executable:
            diagnostics.append(f"{name}: executable not found")
            continue
        if name == "docker":
            client = run_command([executable, "version", "--format", "{{.Client.Version}}"], timeout=20)
            probe = run_command([executable, "info", "--format", "{{.ServerVersion}}"], timeout=20)
        else:
            client = run_command([executable, "version", "--format", "{{.Client.Version}}"], timeout=20)
            probe = run_command([executable, "info", "--format", "{{.Version.Version}}"], timeout=20)
        version = (probe.stdout or client.stdout).strip()
        if probe.returncode == 0:
            return executable, version, None
        error = (probe.stderr or probe.stdout).strip().replace("\n", " ")
        diagnostics.append(f"{name}: {error}")
    return None, "unavailable", "; ".join(diagnostics)


def restricted_container_args(engine: str, capture: Path | None = None) -> list[str]:
    args = [
        engine,
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec",
    ]
    for key, value in ENVIRONMENT.items():
        args.extend(["--env", f"{key}={value}"])
    if capture is not None:
        args.extend(["--mount", f"type=bind,src={capture.resolve()},dst=/capture"])
    return args


def prepare_image(engine: str, manifest: dict[str, Any]) -> dict[str, Any]:
    image = manifest["image_digest"]
    pull = run_command([engine, "pull", image], timeout=600)
    if pull.returncode != 0:
        raise InvalidExperiment(f"immutable image pull failed: {(pull.stderr or pull.stdout).strip()}")
    inspect = run_command([engine, "image", "inspect", image], timeout=60)
    if inspect.returncode != 0:
        raise InvalidExperiment(f"image inspect failed: {inspect.stderr.strip()}")
    inspected = json.loads(inspect.stdout)[0]
    workdir = inspected.get("Config", {}).get("WorkingDir") or "/"

    def image_probe(entrypoint: str, args: list[str]) -> str:
        command = restricted_container_args(engine)
        command.extend(["--entrypoint", entrypoint, image, *args])
        result = run_command(command, timeout=120)
        if result.returncode != 0:
            raise InvalidExperiment(
                f"image prerequisite probe {entrypoint} {' '.join(args)} failed: "
                f"{(result.stderr or result.stdout).strip()}"
            )
        return (result.stdout + result.stderr).strip()

    python_version = image_probe("python", ["--version"])
    package_freeze = image_probe("python", ["-m", "pip", "freeze"])
    strace_version = image_probe("strace", ["--version"])
    expected_manifest_sha = image.rsplit("@sha256:", 1)[1]
    return {
        "resolved_image_id": inspected.get("Id", ""),
        "repo_digests": inspected.get("RepoDigests", []),
        "image_working_directory": workdir,
        "python_version": python_version,
        "installed_package_freeze": package_freeze.splitlines(),
        "strace_version": strace_version.splitlines()[0] if strace_version else "",
        # The supplied OCI object is the only permitted package archive. Its
        # manifest digest is therefore the recorded archive SHA-256.
        "package_source_archive_sha256": expected_manifest_sha,
        "package_source_archive_kind": "supplied immutable OCI manifest",
    }


def trace_paths(capture: Path, prefix: str) -> list[Path]:
    return sorted(path for path in capture.glob(prefix + "*") if path.is_file())


def run_parser_controls(engine: str, image: str, initial_cwd: str) -> dict[str, Any]:
    control_root = ROOT / "control_runs"
    if control_root.exists():
        shutil.rmtree(control_root)
    control_root.mkdir()
    control_script = ROOT / "control_program.py"
    positive_targets = [f"/capture/positive_output/seed_{seed}.csv" for seed in (101, 202, 303)]
    negative_targets = [f"/capture/negative_output/seed_{seed}.csv" for seed in (101, 202, 303)]

    positive_launch = time.time()
    positive_cmd = restricted_container_args(engine, control_root)
    positive_cmd.extend(
        [
            "--mount",
            f"type=bind,src={control_script.resolve()},dst=/control_program.py,readonly",
            "--entrypoint",
            "strace",
            image,
            *STRACE_ARGS,
            "-o",
            "/capture/positive_trace",
            "python",
            "/control_program.py",
            "positive",
            "/capture/positive_output",
        ]
    )
    positive = run_command(
        positive_cmd,
        stdout_path=control_root / "positive_stdout.txt",
        stderr_path=control_root / "positive_stderr.txt",
        timeout=180,
    )

    prepared = run_command(
        [sys.executable, str(control_script), "prepare-negative", str(control_root / "negative_output")],
        timeout=60,
    )
    if prepared.returncode != 0:
        raise InvalidExperiment("failed to prepare deterministic negative parser control")
    negative_launch = time.time()
    negative_cmd = restricted_container_args(engine, control_root)
    negative_cmd.extend(
        [
            "--mount",
            f"type=bind,src={control_script.resolve()},dst=/control_program.py,readonly",
            "--entrypoint",
            "strace",
            image,
            *STRACE_ARGS,
            "-o",
            "/capture/negative_trace",
            "python",
            "/control_program.py",
            "negative",
            "/capture/negative_output",
        ]
    )
    negative = run_command(
        negative_cmd,
        stdout_path=control_root / "negative_stdout.txt",
        stderr_path=control_root / "negative_stderr.txt",
        timeout=180,
    )
    if positive.returncode != 0 or negative.returncode != 0:
        raise InvalidExperiment(
            f"strace parser controls failed to execute (positive={positive.returncode}, negative={negative.returncode})"
        )
    positive_traces = trace_paths(control_root, "positive_trace")
    negative_traces = trace_paths(control_root, "negative_trace")
    if not positive_traces or not negative_traces:
        raise InvalidExperiment("strace produced no per-process parser-control traces")
    positive_result = analyze_trace_set(
        positive_traces,
        positive_targets,
        positive_launch,
        initial_cwd=initial_cwd,
    )
    negative_result = analyze_trace_set(
        negative_traces,
        negative_targets,
        negative_launch,
        initial_cwd=initial_cwd,
        initially_absent={target: False for target in negative_targets},
    )
    positive_ok = all(
        item.created_after_start and item.wrote_positive_bytes and item.write_before_read
        for item in positive_result.values()
    )
    negative_ok = all(
        not item.created_after_start and item.wrote_positive_bytes and not item.write_before_read
        for item in negative_result.values()
    )
    details = {
        "positive": {key: asdict(value) for key, value in positive_result.items()},
        "negative": {key: asdict(value) for key, value in negative_result.items()},
        "positive_ok": positive_ok,
        "negative_ok": negative_ok,
    }
    (control_root / "control_results.json").write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
    if not positive_ok or not negative_ok:
        raise InvalidExperiment("parser-control assertions failed; see control_runs/control_results.json")
    return details


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run_package_once(
    engine: str,
    manifest: dict[str, Any],
    run_index: int,
    initial_cwd: str,
) -> tuple[list[dict[str, Any]], int]:
    runs_root = ROOT / "runs"
    runs_root.mkdir(exist_ok=True)
    run_root = runs_root / f"run_{run_index}"
    if run_root.exists():
        shutil.rmtree(run_root)
    capture = run_root / "capture"
    capture.mkdir(parents=True)
    if list(run_root.iterdir()) != [capture] or list(capture.iterdir()):
        raise InvalidExperiment(f"run_{run_index} did not begin with only an empty capture directory")
    output_name = PurePosixPath(manifest["output_directory"]).name
    host_output = capture / output_name
    if os.path.lexists(host_output):
        raise InvalidExperiment(f"run_{run_index} output location unexpectedly exists before launch")

    create_args = restricted_container_args(engine, capture)
    create_args[1] = "create"
    create_args.remove("--rm")
    create_args.extend(
        [
            "--entrypoint",
            "strace",
            manifest["image_digest"],
            *STRACE_ARGS,
            "-o",
            "/capture/trace",
            *manifest["command"],
        ]
    )
    created = run_command(create_args, timeout=120)
    if created.returncode != 0:
        raise InvalidExperiment(f"container creation failed before run {run_index}: {created.stderr.strip()}")
    container_id = created.stdout.strip()
    launch_monotonic_ns = time.monotonic_ns()
    launch_epoch = time.time()
    start_epoch = time.time()
    start_result = run_command(
        [engine, "start", "--attach", container_id],
        stdout_path=capture / "stdout.txt",
        stderr_path=capture / "stderr.txt",
        timeout=900,
    )
    end_epoch = time.time()
    inspect = run_command([engine, "inspect", "--format", "{{.State.ExitCode}}", container_id], timeout=30)
    if inspect.returncode == 0 and inspect.stdout.strip().lstrip("-").isdigit():
        exit_status = int(inspect.stdout.strip())
    else:
        exit_status = start_result.returncode
    run_metadata = {
        "run": run_index,
        "container_id": container_id,
        "launch_monotonic_ns": launch_monotonic_ns,
        "launch_epoch": launch_epoch,
        "start_epoch": start_epoch,
        "end_epoch": end_epoch,
        "exit_status": exit_status,
        "docker_attach_status": start_result.returncode,
    }
    (capture / "run_metadata.json").write_text(json.dumps(run_metadata, indent=2) + "\n", encoding="utf-8")
    run_command([engine, "rm", container_id], timeout=30)

    traces = trace_paths(capture, "trace")
    container_targets = [
        str(PurePosixPath(manifest["output_directory"]) / target["path"])
        for target in manifest["targets"]
    ]
    provenance = (
        analyze_trace_set(traces, container_targets, launch_epoch, initial_cwd=initial_cwd)
        if traces
        else {}
    )
    rows: list[dict[str, Any]] = []
    output_directory_valid = host_output.is_dir() and not host_output.is_symlink()
    for target_spec, container_target in zip(manifest["targets"], container_targets, strict=True):
        relative = PurePosixPath(target_spec["path"])
        host_target = host_output.joinpath(*relative.parts)
        regular_non_symlink = False
        observed = ""
        size: int | str = ""
        if os.path.lexists(host_target):
            regular_non_symlink = (
                output_directory_valid and host_target.is_file() and not host_target.is_symlink()
            )
            if regular_non_symlink:
                observed = sha256_file(host_target)
                size = host_target.stat().st_size
        item = provenance.get(container_target)
        created_after = bool(item and item.created_after_start)
        wrote = bool(item and item.wrote_positive_bytes)
        before_read = bool(item and item.write_before_read)
        digest_match = observed == target_spec["expected_sha256"]
        passed = (
            exit_status == 0
            and created_after
            and wrote
            and before_read
            and digest_match
            and regular_non_symlink
        )
        rows.append(
            {
                "run": run_index,
                "target": target_spec["path"],
                "exit_status": exit_status,
                "created_after_start": created_after,
                "wrote_positive_bytes": wrote,
                "write_before_read": before_read,
                "first_create_time": item.first_create_time if item else "",
                "first_write_time": item.first_write_time if item else "",
                "first_read_time": item.first_read_time if item and item.first_read_time is not None else "",
                "file_size_bytes": size,
                "observed_sha256": observed,
                "expected_sha256": target_spec["expected_sha256"],
                "digest_match": digest_match,
                "target_run_pass": passed,
            }
        )
    return rows, exit_status


def write_csv(rows: list[dict[str, Any]]) -> None:
    with (ROOT / "results.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def make_matrix(rows: list[dict[str, Any]], targets: list[str] | None, decision: str, error: str = "") -> None:
    FIGURE_PATH.parent.mkdir(exist_ok=True)
    fig, axis = plt.subplots(figsize=(11.5, 8.0))
    if targets and len(rows) == 12:
        matrix = np.array(
            [[1 if next(row for row in rows if row["run"] == run and row["target"] == target)["target_run_pass"] else 0
              for target in targets]
             for run in range(1, 5)]
        )
        axis.imshow(matrix, cmap=matplotlib.colors.ListedColormap(["#d9534f", "#4caf50"]), vmin=0, vmax=1)
        for run in range(1, 5):
            for column, target in enumerate(targets):
                row = next(item for item in rows if item["run"] == run and item["target"] == target)
                annotation = "C/W/R/H\n{}/{}/{}/{}".format(
                    int(row["created_after_start"]),
                    int(row["wrote_positive_bytes"]),
                    int(row["write_before_read"]),
                    int(row["digest_match"]),
                )
                axis.text(column, run - 1, annotation, ha="center", va="center", color="white", fontweight="bold")
        axis.set_xticks(range(3), targets, rotation=20, ha="right")
        axis.set_yticks(range(4), [f"Run {run}" for run in range(1, 5)])
    else:
        matrix = np.full((4, 3), 0.5)
        axis.imshow(matrix, cmap=matplotlib.colors.ListedColormap(["#9e9e9e"]), vmin=0, vmax=1)
        for row in range(4):
            for column in range(3):
                axis.text(column, row, "C/W/R/H\nN/A", ha="center", va="center", color="white", fontweight="bold")
        axis.set_xticks(range(3), ["target unavailable 1", "target unavailable 2", "target unavailable 3"], rotation=15)
        axis.set_yticks(range(4), [f"Run {run}" for run in range(1, 5)])
        axis.text(
            1,
            4.05,
            f"Decision: {decision.upper()} — prerequisites unavailable; see summary.json",
            ha="center",
            va="top",
            fontsize=10,
        )
    axis.set_xlabel("Target CSV")
    axis.set_ylabel("Fresh container execution")
    axis.set_title("Fresh-environment provenance and SHA-256 reproduction: 4 runs x 3 CSVs", pad=18)
    fig.tight_layout()
    fig.savefig(FIGURE_PATH, dpi=180, bbox_inches="tight")
    plt.close(fig)


def calculate_metrics(rows: list[dict[str, Any]], exits: list[int], targets: list[str]) -> dict[str, Any]:
    total_expected = 12
    passing = sum(bool(row["target_run_pass"]) for row in rows)
    created = sum(bool(row["created_after_start"]) for row in rows)
    wrote = sum(bool(row["wrote_positive_bytes"]) for row in rows)
    before = sum(bool(row["write_before_read"]) for row in rows)
    digest = sum(bool(row["digest_match"]) for row in rows)
    zero_exits = sum(status == 0 for status in exits)
    distinct = {
        target: len({row["observed_sha256"] for row in rows if row["target"] == target and row["observed_sha256"]})
        for target in targets
    }
    return {
        "target_run_combinations_expected": total_expected,
        "target_run_combinations_observed": len(rows),
        "target_run_pass_count": passing,
        "target_run_pass_rate": passing / total_expected,
        "creation_provenance_count": created,
        "creation_provenance_rate": created / total_expected,
        "positive_write_count": wrote,
        "positive_write_rate": wrote / total_expected,
        "write_before_read_count": before,
        "write_before_read_rate": before / total_expected,
        "digest_match_count": digest,
        "digest_reproduction_rate": digest / total_expected,
        "package_executions_observed": len(exits),
        "zero_exit_execution_count": zero_exits,
        "execution_success_rate": zero_exits / 4,
        "cross_run_consistency": distinct,
    }


def flat_results(metrics: dict[str, Any], decision: str, error: str, parser_tests: bool, controls: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "decision": decision,
        "experiment_valid": decision != "invalid",
        "hypothesis_supported": decision == "supported",
        "error": error,
        "parser_unit_tests_passed": parser_tests,
        "parser_controls_passed": controls,
    }
    for key, value in metrics.items():
        if key != "cross_run_consistency":
            result[key] = value
    for index, (target, count) in enumerate(metrics.get("cross_run_consistency", {}).items(), 1):
        result[f"target_{index}_path"] = target
        result[f"target_{index}_distinct_observed_sha256"] = count
    return result


def main() -> int:
    started = time.time()
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    exits: list[int] = []
    manifest: dict[str, Any] | None = None
    parser_tests_passed = False
    parser_controls_passed = False
    engine, engine_version, engine_error = detect_engine()

    tests = run_command([sys.executable, "-m", "unittest", "-v", "test_trace_parser.py"], timeout=120)
    (ROOT / "parser_unit_tests.txt").write_text(
        tests.stdout + tests.stderr, encoding="utf-8"
    )
    parser_tests_passed = tests.returncode == 0
    if not parser_tests_passed:
        errors.append("trace parser unit tests failed")

    try:
        manifest = validate_manifest(MANIFEST_PATH)
    except InvalidExperiment as exc:
        errors.append(str(exc))
    if engine is None:
        errors.append(f"no usable Linux container engine: {engine_error}")

    environment_record: dict[str, Any] = {
        "host_architecture": platform.machine(),
        "host_platform": platform.platform(),
        "host_python": sys.version,
        "container_engine": engine or "unavailable",
        "container_engine_version": engine_version,
        "manifest": manifest,
        "started_epoch": started,
    }

    if not errors and manifest is not None and engine is not None:
        try:
            prepared = prepare_image(engine, manifest)
            environment_record.update(prepared)
            controls = run_parser_controls(engine, manifest["image_digest"], prepared["image_working_directory"])
            parser_controls_passed = controls["positive_ok"] and controls["negative_ok"]
            if not parser_controls_passed:
                raise InvalidExperiment("parser controls did not meet all required assertions")
        except InvalidExperiment as exc:
            errors.append(str(exc))

    if not errors and manifest is not None and engine is not None:
        for run_index in range(1, 5):
            try:
                run_rows, exit_status = run_package_once(
                    engine,
                    manifest,
                    run_index,
                    environment_record["image_working_directory"],
                )
            except InvalidExperiment as exc:
                # Failure before the traced command begins makes the experiment
                # invalid. A command that began and exited nonzero is returned
                # normally and therefore refutes instead.
                errors.append(str(exc))
                break
            rows.extend(run_rows)
            exits.append(exit_status)

    targets = [target["path"] for target in manifest["targets"]] if manifest else []
    metrics = calculate_metrics(rows, exits, targets)
    cross_consistent = bool(targets) and all(
        value == 1 for value in metrics["cross_run_consistency"].values()
    )
    if errors:
        decision = "invalid"
    elif (
        len(rows) == 12
        and metrics["target_run_pass_count"] == 12
        and len(exits) == 4
        and metrics["zero_exit_execution_count"] == 4
        and cross_consistent
    ):
        decision = "supported"
    else:
        decision = "refuted"
    error_text = " | ".join(errors)
    environment_record["ended_epoch"] = time.time()
    environment_record["duration_seconds"] = environment_record["ended_epoch"] - started
    (ROOT / "environment.json").write_text(json.dumps(environment_record, indent=2) + "\n", encoding="utf-8")
    write_csv(rows)
    summary = {
        "decision": decision,
        "error": error_text or None,
        "counts_and_rates": metrics,
        "parser_unit_tests_passed": parser_tests_passed,
        "parser_controls_passed": parser_controls_passed,
        "manifest_valid": manifest is not None,
        "environment_path": "environment.json",
        "figure_path": str(FIGURE_PATH.relative_to(ROOT)),
    }
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    results = flat_results(metrics, decision, error_text, parser_tests_passed, parser_controls_passed)
    (ROOT / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    make_matrix(rows, targets if len(targets) == 3 else None, decision, error_text)

    print(
        "Experiment: locked-image CSV provenance and SHA-256 reproduction; "
        f"executed {len(exits)}/4 package runs and observed {len(rows)}/12 target-runs."
    )
    print(
        f"Pass={metrics['target_run_pass_count']}/12, creation={metrics['creation_provenance_rate']:.3f}, "
        f"write={metrics['positive_write_rate']:.3f}, write-before-read={metrics['write_before_read_rate']:.3f}, "
        f"digest={metrics['digest_reproduction_rate']:.3f}, execution={metrics['execution_success_rate']:.3f}."
    )
    print(f"Decision: {decision.upper()}." + (f" Reason: {error_text}" if error_text else ""))
    return 0 if decision in {"supported", "refuted", "invalid"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
