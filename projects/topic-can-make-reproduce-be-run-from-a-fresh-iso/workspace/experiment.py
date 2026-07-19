#!/usr/bin/env python3
"""Run the fresh-checkout ``make reproduce`` provenance experiment.

The timed section is deliberately entered only after Docker, the locked offline
image archive, and the synthetic release repository have passed preflight.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import traceback
from typing import Any


ROOT = Path(__file__).resolve().parent
PREFLIGHT = ROOT / "preflight"
IMAGE_ARCHIVE = ROOT / "image" / "experiment-image.tar"
IMAGE_LOCK = ROOT / "image.lock.json"
SOURCE = ROOT / "artifact-source"
BARE = ROOT / "artifact-release.git"
EVIDENCE = ROOT / "evidence"
FIGURES = ROOT / "figures"
EXPECTED = ("histogram.bin", "samples.csv", "summary.json")
SHA256_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
RUNS = 6
TIME_LIMIT_SECONDS = 1200.0


REPRODUCE_PY = r'''#!/usr/bin/env python3
"""Generate the released deterministic synthetic artifact."""

import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import sys

SEED = 20250308
N = 10000


def main():
    output = Path("generated")
    if output.exists() or output.is_symlink():
        if output.is_dir() and not output.is_symlink():
            shutil.rmtree(output)
        else:
            output.unlink()
    output.mkdir()
    rng = random.Random(SEED)
    rows = []
    counts = [0] * 256
    sum_x = 0
    sum_y = 0
    for i in range(N):
        x = rng.randrange(0, 1000000)
        y = (1103515245 * x + 12345 + i) % 2147483648
        rows.append(f"{i},{x},{y}\n")
        counts[x % 256] += 1
        sum_x += x
        sum_y += y
    samples = ("i,x,y\n" + "".join(rows)).encode("utf-8")
    (output / "samples.csv").write_bytes(samples)
    summary = {
        "n": N,
        "samples_sha256": hashlib.sha256(samples).hexdigest(),
        "sum_x": sum_x,
        "sum_y": sum_y,
    }
    (output / "summary.json").write_bytes(
        (json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    )
    (output / "histogram.bin").write_bytes(struct.pack("<256I", *counts))
    sys.stdout.write("generated 3 files from 10000 records\n")
    sys.stderr.write("seed=20250308\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


BUILD_REFERENCES_PY = r'''#!/usr/bin/env python3
"""Independently build the three released reference files."""

import hashlib
import json
from pathlib import Path
import random
import shutil
import struct

SEED = 20250308
COUNT = 10000


def main():
    destination = Path("reference")
    if destination.exists() or destination.is_symlink():
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    destination.mkdir()
    generator = random.Random(SEED)
    csv_lines = ["i,x,y\n"]
    buckets = [0 for _ in range(256)]
    total_x = 0
    total_y = 0
    for index in range(COUNT):
        value_x = generator.randrange(0, 1000000)
        value_y = (1103515245 * value_x + 12345 + index) % 2147483648
        csv_lines.append("{},{},{}\n".format(index, value_x, value_y))
        buckets[value_x % 256] += 1
        total_x += value_x
        total_y += value_y
    csv_payload = "".join(csv_lines).encode("utf-8")
    (destination / "samples.csv").write_bytes(csv_payload)
    manifest = {
        "n": COUNT,
        "samples_sha256": hashlib.sha256(csv_payload).hexdigest(),
        "sum_x": total_x,
        "sum_y": total_y,
    }
    (destination / "summary.json").write_bytes(
        (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    )
    (destination / "histogram.bin").write_bytes(struct.pack("<" + "I" * 256, *buckets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


MAKEFILE = """.PHONY: reproduce\nreproduce:\n\t@rm -rf generated\n\t@python3 reproduce.py\n"""


class InfrastructureError(RuntimeError):
    """A condition which requires BROKEN rather than REFUTED."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


COMMAND_LOG: list[dict[str, Any]] = []
COMMAND_DEADLINE_MONOTONIC: float | None = None


def canonical_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    log: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    if timeout is None and COMMAND_DEADLINE_MONOTONIC is not None:
        timeout = max(0.01, COMMAND_DEADLINE_MONOTONIC - time.monotonic())
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        result = subprocess.CompletedProcess(argv, 124, exc.stdout or b"", exc.stderr or b"timeout\n")
    except OSError as exc:
        result = subprocess.CompletedProcess(argv, 127, b"", (str(exc) + "\n").encode("utf-8", "replace"))
    if log:
        COMMAND_LOG.append(
            {
                "argv": argv,
                "cwd": str(cwd or ROOT),
                "exit_status": result.returncode,
                "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
                "stdout_bytes": len(result.stdout),
                "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
                "stderr_bytes": len(result.stderr),
            }
        )
    return result


def require(result: subprocess.CompletedProcess[bytes], status: str, label: str) -> bytes:
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise InfrastructureError(status, f"{label} failed with exit status {result.returncode}: {detail}")
    return result.stdout


def save_streams(prefix: str, result: subprocess.CompletedProcess[bytes]) -> None:
    PREFLIGHT.mkdir(parents=True, exist_ok=True)
    (PREFLIGHT / f"{prefix}.stdout.log").write_bytes(result.stdout)
    (PREFLIGHT / f"{prefix}.stderr.log").write_bytes(result.stderr)


def repair_cli_plugins(report: dict[str, Any]) -> None:
    config = Path(os.environ.get("DOCKER_CONFIG", str(Path.home() / ".docker")))
    repairs: list[dict[str, Any]] = []
    for name in ("docker-dev", "docker-feedback"):
        entry = config / "cli-plugins" / name
        item: dict[str, Any] = {"path": str(entry), "action": "none"}
        dangling = entry.is_symlink() and not entry.exists()
        non_executable = entry.exists() and not os.access(entry, os.X_OK)
        if dangling or non_executable:
            destination = entry.with_name(entry.name + ".disabled")
            try:
                if destination.exists() or destination.is_symlink():
                    item["action"] = "not-renamed-destination-exists"
                else:
                    entry.rename(destination)
                    item["action"] = "renamed-disabled"
            except OSError as exc:
                item["action"] = "rename-failed"
                item["error"] = str(exc)
        repairs.append(item)
    report["cli_plugin_repairs"] = repairs


def docker_daemon_preflight(report: dict[str, Any]) -> None:
    initial = run(["docker", "info"])
    save_streams("docker-info-initial", initial)
    report["docker_info_initial_exit_status"] = initial.returncode
    if initial.returncode != 0:
        if platform.system() == "Darwin":
            recovery = run(["open", "-a", "Docker"])
            save_streams("docker-recovery", recovery)
        elif platform.system() == "Linux" and Path("/run/systemd/system").exists():
            recovery = run(["sudo", "-n", "systemctl", "start", "docker"])
            save_streams("docker-recovery", recovery)
        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            time.sleep(min(2.0, max(0.0, deadline - time.monotonic())))
            poll = run(["docker", "info"], log=False)
            if poll.returncode == 0:
                break
    repair_cli_plugins(report)
    final = run(["docker", "info"])
    save_streams("docker-info", final)
    report["docker_info_exit_status"] = final.returncode
    if final.returncode != 0:
        raise InfrastructureError(
            "BROKEN_DOCKER_DAEMON",
            "docker info remained unsuccessful after the bounded recovery poll",
        )
    version = run(["docker", "version"])
    ps = run(["docker", "ps"])
    save_streams("docker-version", version)
    save_streams("docker-ps", ps)
    if version.returncode != 0 or ps.returncode != 0:
        raise InfrastructureError(
            "BROKEN_DOCKER_PERMISSION",
            f"noninteractive Docker access failed (version={version.returncode}, ps={ps.returncode})",
        )


def load_lock() -> dict[str, str]:
    if not IMAGE_ARCHIVE.is_file() or IMAGE_ARCHIVE.is_symlink():
        raise InfrastructureError("BROKEN_IMAGE_PREFLIGHT", f"supplied OCI archive missing: {IMAGE_ARCHIVE}")
    try:
        raw = json.loads(IMAGE_LOCK.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InfrastructureError("BROKEN_IMAGE_PREFLIGHT", f"cannot parse image lock: {exc}") from exc
    needed = ("archive_sha256", "image_id", "image_reference")
    if not all(isinstance(raw.get(key), str) for key in needed):
        raise InfrastructureError("BROKEN_IMAGE_PREFLIGHT", f"image lock requires string keys {needed}")
    if not HEX64.fullmatch(raw["archive_sha256"]) or not SHA256_ID.fullmatch(raw["image_id"]):
        raise InfrastructureError("BROKEN_IMAGE_PREFLIGHT", "image lock contains malformed SHA-256 values")
    return {key: raw[key] for key in needed}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def image_preflight(report: dict[str, Any]) -> dict[str, str]:
    lock = load_lock()
    archive_hash = file_sha256(IMAGE_ARCHIVE)
    report["archive_sha256"] = archive_hash
    report["locked_archive_sha256"] = lock["archive_sha256"]
    if archive_hash != lock["archive_sha256"]:
        raise InfrastructureError("BROKEN_IMAGE_PREFLIGHT", "OCI archive SHA-256 does not equal image.lock.json")
    inspect = run(["docker", "image", "inspect", lock["image_id"]])
    if inspect.returncode != 0:
        loaded = run(["docker", "load", "--input", str(IMAGE_ARCHIVE)])
        save_streams("docker-load", loaded)
        require(loaded, "BROKEN_IMAGE_PREFLIGHT", "offline docker load")
        inspect = run(["docker", "image", "inspect", lock["image_id"]])
    save_streams("image-inspect", inspect)
    raw = require(inspect, "BROKEN_IMAGE_PREFLIGHT", "locked image inspection")
    try:
        image = json.loads(raw)[0]
        actual_id = image["Id"]
        actual_arch = image["Architecture"]
        actual_os = image["Os"]
    except (ValueError, IndexError, KeyError, TypeError) as exc:
        raise InfrastructureError("BROKEN_IMAGE_PREFLIGHT", f"invalid image inspection JSON: {exc}") from exc
    ref_inspect = run(["docker", "image", "inspect", lock["image_reference"], "--format", "{{.Id}}"])
    ref_id = require(ref_inspect, "BROKEN_IMAGE_PREFLIGHT", "locked image reference inspection").decode("ascii", "strict").strip()
    if actual_id != lock["image_id"] or ref_id != lock["image_id"]:
        raise InfrastructureError("BROKEN_IMAGE_PREFLIGHT", "loaded image/reference ID differs from lock")
    machine = platform.machine().lower()
    expected_arch = "arm64" if machine in ("arm64", "aarch64") else machine
    if actual_os != "linux" or actual_arch != expected_arch:
        raise InfrastructureError(
            "BROKEN_IMAGE_PREFLIGHT",
            f"image platform linux/{actual_arch} does not equal runner linux/{expected_arch}",
        )
    smoke = run(
        [
            "docker", "run", "--rm", "--network", "none", lock["image_reference"],
            "sh", "-c", "python3 --version && git --version && make --version",
        ]
    )
    save_streams("smoke-test", smoke)
    require(smoke, "BROKEN_IMAGE_PREFLIGHT", "network-disabled image smoke test")
    report["image_id"] = actual_id
    report["image_reference"] = lock["image_reference"]
    report["image_platform"] = f"{actual_os}/{actual_arch}"
    return lock


def inventory(directory: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError(f"not a regular directory: {directory}")
    files: list[Path] = []
    for entry in directory.rglob("*"):
        if entry.is_symlink() or not entry.is_file():
            raise ValueError(f"non-regular inventory entry: {entry}")
        files.append(entry)
    relative = sorted(path.relative_to(directory).as_posix() for path in files)
    if tuple(relative) != EXPECTED:
        raise ValueError(f"inventory {relative!r} differs from {list(EXPECTED)!r}")
    by_name = {path.relative_to(directory).as_posix(): path for path in files}
    items = [{"path": name, "size": by_name[name].stat().st_size} for name in relative]
    hashes = {name: file_sha256(by_name[name]) for name in relative}
    return items, hashes


def prepare_artifact_repository() -> str:
    for target in (SOURCE, BARE):
        if target.exists() or target.is_symlink():
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
    SOURCE.mkdir()
    (SOURCE / "Makefile").write_text(MAKEFILE, encoding="utf-8", newline="\n")
    (SOURCE / "reproduce.py").write_text(REPRODUCE_PY, encoding="utf-8", newline="\n")
    (SOURCE / "build_references.py").write_text(BUILD_REFERENCES_PY, encoding="utf-8", newline="\n")
    (SOURCE / "README.md").write_text(
        "# Synthetic reproducibility artifact\n\nRun `make reproduce` with Python 3.12.\n",
        encoding="utf-8",
        newline="\n",
    )
    built = run([sys.executable, "build_references.py"], cwd=SOURCE)
    require(built, "BROKEN_IMAGE_PREFLIGHT", "independent reference construction")
    inventory(SOURCE / "reference")
    require(run(["git", "init", "--quiet"], cwd=SOURCE), "BROKEN_IMAGE_PREFLIGHT", "git init")
    require(
        run(["git", "add", "Makefile", "reproduce.py", "build_references.py", "README.md", "reference"], cwd=SOURCE),
        "BROKEN_IMAGE_PREFLIGHT",
        "git add artifact",
    )
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Reproducibility Experiment",
            "GIT_AUTHOR_EMAIL": "experiment@example.invalid",
            "GIT_AUTHOR_DATE": "2025-03-08T00:00:00Z",
            "GIT_COMMITTER_NAME": "Reproducibility Experiment",
            "GIT_COMMITTER_EMAIL": "experiment@example.invalid",
            "GIT_COMMITTER_DATE": "2025-03-08T00:00:00Z",
        }
    )
    require(run(["git", "commit", "--quiet", "-m", "Release deterministic artifact"], cwd=SOURCE, env=env), "BROKEN_IMAGE_PREFLIGHT", "git commit")
    revision = require(run(["git", "rev-parse", "HEAD"], cwd=SOURCE), "BROKEN_IMAGE_PREFLIGHT", "revision resolution").decode("ascii").strip()
    if not HEX40.fullmatch(revision):
        raise InfrastructureError("BROKEN_IMAGE_PREFLIGHT", f"invalid artifact revision {revision!r}")
    require(run(["git", "clone", "--quiet", "--bare", "--no-local", str(SOURCE), str(BARE)]), "BROKEN_IMAGE_PREFLIGHT", "bare clone")
    canonical_json(
        ROOT / "experiment_manifest.json",
        {"artifact_revision": revision, "expected_outputs": list(EXPECTED), "seed": 20250308},
    )
    return revision


def clean_run_outputs() -> None:
    for target in (EVIDENCE, FIGURES):
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
    for pattern in ("primary-[0-9][0-9]", "replay-[0-9][0-9]"):
        for target in ROOT.glob(pattern):
            if target.is_dir():
                shutil.rmtree(target)
    for target in (ROOT / "verification.json", ROOT / "verification_summary.png"):
        if target.exists():
            target.unlink()


def reset_previous_execution() -> None:
    """Remove only artifacts owned by prior executions of this harness."""
    directories = (PREFLIGHT, EVIDENCE, FIGURES, SOURCE, BARE, ROOT / "results")
    for target in directories:
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        elif target.exists() or target.is_symlink():
            target.unlink()
    for pattern in ("primary-[0-9][0-9]", "replay-[0-9][0-9]"):
        for target in ROOT.glob(pattern):
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
    files = (
        "results.json", "verification.json", "verification_summary.png",
        "timing.json", "experiment_manifest.json", "command_ledger.json",
        "experiment_error.log", "preflight.json", "verify.stdout.log",
        "verify.stderr.log",
    )
    for name in files:
        target = ROOT / name
        if target.exists() or target.is_symlink():
            target.unlink()


def resolve_interpreter(image_reference: str) -> str:
    probe = run(
        [
            "docker", "run", "--rm", "--network", "none", image_reference,
            "python3", "-c", "import os,sys; print(os.path.realpath(sys.executable))",
        ]
    )
    require(probe, "BROKEN_EXECUTION", "interpreter probe")
    try:
        lines = probe.stdout.decode("utf-8", "strict").splitlines()
    except UnicodeDecodeError as exc:
        raise InfrastructureError("BROKEN_EXECUTION", f"interpreter probe was not UTF-8: {exc}") from exc
    if len(lines) != 1 or not lines[0].startswith("/"):
        raise InfrastructureError("BROKEN_EXECUTION", f"interpreter probe returned {lines!r}")
    return lines[0]


def clone_checkout(kind: str, number: int, revision: str) -> Path:
    run_root = ROOT / f"{kind}-{number:02d}"
    run_root.mkdir()
    checkout = run_root / "checkout"
    require(run(["git", "clone", "--quiet", "--no-local", str(BARE), str(checkout)]), "BROKEN_EXECUTION", f"{kind} clone")
    require(run(["git", "checkout", "--quiet", "--detach", revision], cwd=checkout), "BROKEN_EXECUTION", f"{kind} detach")
    status = require(run(["git", "status", "--porcelain"], cwd=checkout), "BROKEN_EXECUTION", f"{kind} clean check")
    if status != b"":
        raise InfrastructureError("BROKEN_EXECUTION", f"{kind}-{number:02d} checkout was dirty")
    return checkout


def execute_one(kind: str, number: int, revision: str, lock: dict[str, str]) -> dict[str, Any]:
    checkout = clone_checkout(kind, number, revision)
    interpreter = resolve_interpreter(lock["image_reference"])
    evidence = EVIDENCE / f"{kind}-{number:02d}"
    evidence.mkdir(parents=True)
    name = f"make-reproduce-{kind}-{number:02d}-{os.getpid()}"
    create_argv = [
        "docker", "create", "--name", name,
        "--network", "none", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--read-only",
        "--tmpfs", "/tmp:rw,nosuid,nodev,noexec",
        "--mount", f"type=bind,src={checkout.resolve()},dst=/work,rw",
        "--workdir", "/work", lock["image_reference"], "make", "reproduce",
    ]
    created = run(create_argv)
    container_id = require(created, "BROKEN_EXECUTION", f"{kind} docker create").decode("ascii", "strict").strip()
    if not container_id:
        raise InfrastructureError("BROKEN_EXECUTION", "docker create returned an empty container ID")
    inspected: dict[str, Any] | None = None
    try:
        started = run(["docker", "start", "--attach", container_id])
        (evidence / "stdout.log").write_bytes(started.stdout)
        (evidence / "stderr.log").write_bytes(started.stderr)
        exit_raw = require(
            run(["docker", "inspect", "--format", "{{.State.ExitCode}}", container_id]),
            "BROKEN_EXECUTION",
            f"{kind} exit inspection",
        ).decode("ascii", "strict").strip()
        try:
            exit_status = int(exit_raw)
        except ValueError as exc:
            raise InfrastructureError("BROKEN_EXECUTION", f"invalid container exit status {exit_raw!r}") from exc
        inspect_raw = require(run(["docker", "inspect", container_id]), "BROKEN_EXECUTION", f"{kind} config inspection")
        inspected = json.loads(inspect_raw)[0]
        command_args = inspected["Config"]["Cmd"]
        image_id = inspected["Image"]
    finally:
        removed = run(["docker", "rm", container_id])
        if removed.returncode != 0:
            COMMAND_LOG.append({"warning": f"failed to remove container {container_id}"})
    if inspected is None:
        raise InfrastructureError("BROKEN_EXECUTION", f"could not inspect {kind} container")
    try:
        generated_inventory, generated_hashes = inventory(checkout / "generated")
        reference_inventory, reference_hashes = inventory(checkout / "reference")
    except ValueError as exc:
        # A completed, malformed execution is experimental evidence, not missing infrastructure.
        generated_inventory, generated_hashes = [], {}
        reference_inventory, reference_hashes = [], {}
        COMMAND_LOG.append({"warning": str(exc)})
    comparisons: dict[str, dict[str, Any]] = {}
    for output in EXPECTED:
        generated_path = checkout / "generated" / output
        reference_path = checkout / "reference" / output
        generated_hash = generated_hashes.get(output)
        reference_hash = reference_hashes.get(output)
        byte_equal = (
            generated_path.is_file()
            and not generated_path.is_symlink()
            and reference_path.is_file()
            and not reference_path.is_symlink()
            and generated_path.read_bytes() == reference_path.read_bytes()
        )
        comparisons[output] = {
            "generated_sha256": generated_hash,
            "reference_sha256": reference_hash,
            "byte_equal": byte_equal,
            "hash_equal": generated_hash is not None and generated_hash == reference_hash,
        }
    record = {
        "schema_version": 1,
        "run_kind": kind,
        "run_number": number,
        "checkout_revision": revision,
        "image_reference": lock["image_reference"],
        "image_id": image_id,
        "container_id": container_id,
        "interpreter_path": interpreter,
        "literal_command": "make reproduce",
        "container_command_args": command_args,
        "exit_status": exit_status,
        "stdout": {"sha256": hashlib.sha256(started.stdout).hexdigest(), "bytes": len(started.stdout)},
        "stderr": {"sha256": hashlib.sha256(started.stderr).hexdigest(), "bytes": len(started.stderr)},
        "generated_inventory": generated_inventory,
        "generated_sha256": generated_hashes,
        "reference_inventory": reference_inventory,
        "reference_sha256": reference_hashes,
        "comparisons": comparisons,
    }
    canonical_json(evidence / "record.json", record)
    return record


def flat_broken(
    status: str,
    message: str,
    elapsed: float,
    attempted: int,
    completed: int,
    successful: int,
) -> dict[str, Any]:
    return {
        "classification": "BROKEN",
        "preflight_status": status,
        "error": message,
        "artifact_seed": 20250308,
        "primary_runs_attempted": min(attempted, RUNS),
        "primary_runs_completed": min(completed, RUNS),
        "replay_runs_attempted": max(0, attempted - RUNS),
        "replay_runs_completed": max(0, completed - RUNS),
        "successful_executions": successful,
        "total_executions_required": 12,
        "execution_completion_rate": successful / 12,
        "evidence_checks_attempted": 0,
        "evidence_checks_passed": 0,
        "evidence_verification_rate": 0.0,
        "replay_byte_comparisons_attempted": 0,
        "replay_byte_comparisons_passed": 0,
        "replay_byte_agreement": 0.0,
        "reference_byte_comparisons_attempted": 0,
        "reference_byte_comparisons_passed": 0,
        "released_reference_agreement": 0.0,
        "stream_separation_integrity": False,
        "timed_elapsed_seconds": round(elapsed, 6),
        "timed_limit_seconds": 1200,
        "timed_within_limit": elapsed <= TIME_LIMIT_SECONDS,
        "png_exists_nonempty": False,
    }


def main() -> int:
    global COMMAND_DEADLINE_MONOTONIC
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-daemon-wait", action="store_true", help="development only; do not use for a protocol run")
    args = parser.parse_args()
    if args.skip_daemon_wait:
        os.environ["REPRODUCE_SKIP_DAEMON_WAIT"] = "1"
    reset_previous_execution()
    PREFLIGHT.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    preflight_report: dict[str, Any] = {"status": "STARTED"}
    timed_start: float | None = None
    attempted = 0
    completed = 0
    successful = 0
    try:
        if os.environ.get("REPRODUCE_SKIP_DAEMON_WAIT") == "1":
            repair_cli_plugins(preflight_report)
            final = run(["docker", "info"])
            save_streams("docker-info", final)
            if final.returncode != 0:
                raise InfrastructureError("BROKEN_DOCKER_DAEMON", "docker info unsuccessful (development no-wait mode)")
        else:
            docker_daemon_preflight(preflight_report)
        lock = image_preflight(preflight_report)
        revision = prepare_artifact_repository()
        preflight_report.update({"status": "PASSED", "artifact_revision": revision})
        canonical_json(PREFLIGHT / "report.json", preflight_report)
        clean_run_outputs()
        timed_start = time.time()
        COMMAND_DEADLINE_MONOTONIC = time.monotonic() + TIME_LIMIT_SECONDS
        canonical_json(ROOT / "timing.json", {"timed_start_unix_seconds": timed_start, "limit_seconds": 1200})
        for kind in ("primary", "replay"):
            for number in range(1, RUNS + 1):
                if time.monotonic() >= COMMAND_DEADLINE_MONOTONIC:
                    raise InfrastructureError("BROKEN_TIMEOUT", "20-minute timed section expired during executions")
                attempted += 1
                record = execute_one(kind, number, revision, lock)
                completed += 1
                successful += int(type(record.get("exit_status")) is int and record["exit_status"] == 0)
        verifier = run([sys.executable, str(ROOT / "verify.py")], cwd=ROOT)
        (ROOT / "verify.stdout.log").write_bytes(verifier.stdout)
        (ROOT / "verify.stderr.log").write_bytes(verifier.stderr)
        if verifier.returncode != 0 or not (ROOT / "results.json").is_file():
            raise InfrastructureError("BROKEN_VERIFIER", f"verifier failed with exit status {verifier.returncode}")
        final = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))
        print(
            f"Ran {completed}/12 isolated make reproduce executions; "
            f"evidence {final['evidence_checks_passed']}/66, replay bytes "
            f"{final['replay_byte_comparisons_passed']}/18, references "
            f"{final['reference_byte_comparisons_passed']}/18; {final['classification']}."
        )
        return 0 if final["classification"] == "SUPPORTED" else 1
    except InfrastructureError as exc:
        elapsed = 0.0 if timed_start is None else time.time() - timed_start
        preflight_report.update({"status": exc.status, "error": str(exc)})
        canonical_json(PREFLIGHT / "report.json", preflight_report)
        canonical_json(ROOT / "command_ledger.json", COMMAND_LOG)
        result = flat_broken(exc.status, str(exc), elapsed, attempted, completed, successful)
        canonical_json(ROOT / "results.json", result)
        print(
            f"Ran {completed}/12 isolated make reproduce executions; "
            f"infrastructure status {exc.status}; BROKEN: {exc}"
        )
        return 2
    except Exception as exc:  # preserve unexpected failures as BROKEN evidence
        elapsed = 0.0 if timed_start is None else time.time() - timed_start
        message = f"unexpected harness failure: {exc}"
        preflight_report.update({"status": "BROKEN_HARNESS", "error": message})
        canonical_json(PREFLIGHT / "report.json", preflight_report)
        (ROOT / "experiment_error.log").write_text(traceback.format_exc(), encoding="utf-8")
        canonical_json(ROOT / "command_ledger.json", COMMAND_LOG)
        canonical_json(
            ROOT / "results.json",
            flat_broken("BROKEN_HARNESS", message, elapsed, attempted, completed, successful),
        )
        print(f"Ran {completed}/12 isolated make reproduce executions; BROKEN: {message}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
