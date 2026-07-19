#!/usr/bin/env python3
"""Run 24 deterministic Docker completion-monitor executions.

The host harness is deliberately Python-standard-library only.  It never pulls
an image and it always addresses exactly unix:///var/run/docker.sock.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import random
import shutil
import struct
import subprocess
import sys
import time
from typing import Any
import zlib


ROOT = Path(__file__).resolve().parent
FIXTURE_DIR = ROOT / "fixture"
FIGURES_DIR = ROOT / "figures"
ARTIFACTS_DIR = ROOT / "artifacts"
RESULTS_PATH = ROOT / "results.json"
FIGURE_PATH = FIGURES_DIR / "key_result.png"
DOCKER_HOST = "unix:///var/run/docker.sock"
SEED = 1729
TIME_LIMIT = 1200.000
RUN_TIMEOUT = 30.0
ORDER = tuple(item for number in range(1, 7) for item in (f"D{number}", f"C{number}"))


def monotonic() -> float:
    return time.monotonic()


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    fsync_directory(path.parent)


def atomic_json(path: Path, value: Any) -> None:
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) and not isinstance(value, (list, dict))


def write_flat_results(values: dict[str, Any]) -> None:
    if not all(isinstance(key, str) and is_scalar(value) for key, value in values.items()):
        raise TypeError("results.json must be a flat JSON object of scalar values")
    atomic_json(RESULTS_PATH, values)


def run_command(argv: list[str], env: dict[str, str], timeout: float = 30.0) -> dict[str, Any]:
    started = monotonic()
    try:
        completed = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            check=False,
        )
        return {
            "command": argv,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "timeout": False,
            "start_timestamp": started,
            "end_timestamp": monotonic(),
        }
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
        return {
            "command": argv,
            "exit_code": -1,
            "stdout": stdout,
            "stderr": stderr,
            "timeout": True,
            "start_timestamp": started,
            "end_timestamp": monotonic(),
        }
    except OSError as error:
        return {
            "command": argv,
            "exit_code": -1,
            "stdout": "",
            "stderr": f"{type(error).__name__}: {error}",
            "timeout": False,
            "start_timestamp": started,
            "end_timestamp": monotonic(),
        }


def docker_env() -> dict[str, str]:
    env = dict(os.environ)
    env["DOCKER_HOST"] = DOCKER_HOST
    env["PYTHONHASHSEED"] = str(SEED)
    # A context must never override the explicitly required endpoint.
    env.pop("DOCKER_CONTEXT", None)
    return env


def attempt_exact_socket() -> dict[str, Any]:
    """Start Docker Desktop on macOS and make only the mandated endpoint usable."""
    socket = Path("/var/run/docker.sock")
    evidence: dict[str, Any] = {
        "platform": platform.system(),
        "required_endpoint": DOCKER_HOST,
        "socket_initially_exists": socket.exists(),
        "actions": [],
    }
    if platform.system() == "Linux" and not socket.exists():
        for command in (["systemctl", "start", "docker"], ["service", "docker", "start"]):
            result = run_command(command, docker_env(), timeout=30.0)
            evidence["actions"].append(result)
            if socket.exists():
                break
    if platform.system() != "Darwin" or socket.exists():
        evidence["socket_readable"] = os.access(socket, os.R_OK) if socket.exists() else False
        evidence["socket_writable"] = os.access(socket, os.W_OK) if socket.exists() else False
        evidence["socket_finally_exists"] = socket.exists()
        return evidence

    started = run_command(["open", "-a", "Docker"], docker_env(), timeout=15.0)
    evidence["actions"].append(started)
    deadline = monotonic() + 15.0
    while monotonic() < deadline and not socket.exists():
        time.sleep(0.5)

    if not socket.exists():
        candidates = (
            Path.home() / ".docker/run/docker.sock",
            Path.home() / "Library/Containers/com.docker.docker/Data/docker.raw.sock",
        )
        active = next((candidate for candidate in candidates if candidate.exists()), None)
        if active is not None:
            try:
                socket.symlink_to(active)
                evidence["actions"].append({"created_symlink": str(socket), "target": str(active)})
            except OSError as error:
                evidence["actions"].append({"symlink_error": f"{type(error).__name__}: {error}"})
    evidence["socket_finally_exists"] = socket.exists()
    return evidence


def docker(args: list[str], env: dict[str, str], timeout: float = 30.0) -> dict[str, Any]:
    return run_command(["docker", *args], env, timeout)


def gate_commands(env: dict[str, str]) -> dict[str, dict[str, Any]]:
    # These deliberately remain three separate 30-second invocations.
    return {
        "info": docker(["info"], env, 30.0),
        "version": docker(["version"], env, 30.0),
        "ps": docker(["ps"], env, 30.0),
    }


def inspect_image(reference: str, env: dict[str, str]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    result = docker(["image", "inspect", reference], env, 30.0)
    if result["exit_code"] != 0:
        return None, result
    try:
        items = json.loads(result["stdout"])
        if len(items) != 1 or items[0].get("Os") != "linux":
            return None, result
        return items[0], result
    except (json.JSONDecodeError, TypeError, IndexError):
        return None, result


def choose_base_image(env: dict[str, str]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    preferred = ("python:3.12-slim", "python:3.12-slim-bookworm", "python:3.12-alpine")
    for reference in preferred:
        image, result = inspect_image(reference, env)
        attempts.append(result)
        if image is not None and str(image.get("Id", "")).startswith("sha256:"):
            return image, attempts

    # Only a pre-provisioned archive inside the experiment bundle may be loaded.
    archives = sorted(
        path for path in ROOT.rglob("*")
        if path.is_file() and (path.name.endswith(".oci.tar") or path.name.endswith("-python312.tar"))
    )
    for archive in archives:
        loaded = docker(["load", "--input", str(archive)], env, 120.0)
        attempts.append(loaded)
        if loaded["exit_code"] != 0:
            continue
        for reference in preferred:
            image, result = inspect_image(reference, env)
            attempts.append(result)
            if image is not None and str(image.get("Id", "")).startswith("sha256:"):
                return image, attempts
    return None, attempts


def prepare_image(run_id: str, env: dict[str, str]) -> tuple[str, str, dict[str, Any]]:
    base, image_attempts = choose_base_image(env)
    preparation: dict[str, Any] = {"image_lookup_commands": image_attempts}
    if base is None:
        preparation["error"] = "no suitable preloaded Linux Python 3.12 image or matching OCI archive"
        return "", "", preparation
    base_id = str(base["Id"])
    tag = f"completion-monitor-experiment:{run_id.lower()}"
    build = docker(
        [
            "build", "--network=none", "--pull=false",
            "--build-arg", f"BASE_IMAGE={base_id}",
            "--tag", tag, str(FIXTURE_DIR),
        ],
        env,
        180.0,
    )
    preparation["build"] = build
    if build["exit_code"] != 0:
        preparation["error"] = "fixture image build failed"
        return base_id, "", preparation
    built, inspection = inspect_image(tag, env)
    preparation["built_image_inspection"] = inspection
    if built is None or not str(built.get("Id", "")).startswith("sha256:"):
        preparation["error"] = "could not resolve built image to immutable ID"
        return base_id, "", preparation
    return base_id, str(built["Id"]), preparation


def smoke(image_id: str, env: dict[str, str]) -> dict[str, Any]:
    return docker(
        [
            "run", "--rm", "--network=none", "--init=false", "--cap-drop=ALL",
            "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev",
            "--entrypoint", "python3", image_id, "-c", "print(1729)",
        ],
        env,
        30.0,
    )


FONT = {
    " ": ("00000",) * 7,
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    "/": ("00001", "00010", "00100", "01000", "10000", "00000", "00000"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
}
FONT.update({
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
})


def png_plot(counts: list[int], infrastructure_valid: bool) -> bytes:
    width, height = 900, 560
    pixels = bytearray([255] * (width * height * 3))

    def rectangle(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        for y in range(max(0, y0), min(height, y1)):
            start = (y * width + max(0, x0)) * 3
            for x in range(max(0, x0), min(width, x1)):
                offset = start + (x - max(0, x0)) * 3
                pixels[offset:offset + 3] = bytes(color)

    def text(x: int, y: int, label: str, scale: int = 3, color: tuple[int, int, int] = (20, 25, 35)) -> None:
        cursor = x
        for character in label.upper():
            glyph = FONT.get(character, FONT[" "])
            for row, pattern in enumerate(glyph):
                for column, bit in enumerate(pattern):
                    if bit == "1":
                        rectangle(cursor + column * scale, y + row * scale,
                                  cursor + (column + 1) * scale, y + (row + 1) * scale, color)
            cursor += 6 * scale

    plot_left, plot_top, plot_right, plot_bottom = 100, 80, 850, 430
    rectangle(plot_left, plot_top, plot_left + 2, plot_bottom + 2, (30, 30, 30))
    rectangle(plot_left, plot_bottom, plot_right, plot_bottom + 2, (30, 30, 30))
    for value, label in ((0, "0.0"), (0.5, "0.5"), (1, "1.0")):
        y = round(plot_bottom - value * (plot_bottom - plot_top))
        rectangle(plot_left, y, plot_right, y + 1, (215, 220, 225))
        text(35, y - 10, label, 2)
    labels = ("NAIVE DIRTY", "AWARE DIRTY", "NAIVE CLEAN", "AWARE CLEAN")
    colors = ((65, 105, 225), (232, 126, 4), (46, 160, 90), (136, 84, 180))
    centers = (190, 375, 560, 745)
    for count, label, color, center in zip(counts, labels, colors, centers):
        bar_height = round((count / 12) * (plot_bottom - plot_top))
        rectangle(center - 55, plot_bottom - bar_height, center + 55, plot_bottom, color if infrastructure_valid else (175, 175, 175))
        text(center - 25, max(plot_top + 5, plot_bottom - bar_height - 30), f"{count}/12", 2)
        text(center - 6 * len(label), 460, label, 2)
    title = "COMPLETION AT PARENT EXIT" if infrastructure_valid else "INFRASTRUCTURE INVALID - ZERO FIXTURES"
    text(450 - 9 * len(title), 25, title, 3)

    raw = b"".join(b"\x00" + bytes(pixels[y * width * 3:(y + 1) * width * 3]) for y in range(height))
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def execute_one(
    execution_id: str,
    fixture: str,
    phase: str,
    seed: int,
    image_id: str,
    run_dir: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    output_dir = run_dir / "executions" / execution_id
    output_dir.mkdir(parents=True, exist_ok=False)
    container_name = f"completion-{run_dir.name.lower()}-{execution_id.lower()}"
    command = [
        "run", "--rm", "--name", container_name,
        "--network=none", "--init=false", "--cap-drop=ALL", "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev",
        "--mount", f"type=bind,src={output_dir},dst=/work,rw",
        "--env", f"EXPERIMENT_IMAGE_ID={image_id}", image_id,
        "--fixture", fixture, "--seed", str(seed), "--execution-id", execution_id,
    ]
    docker_result = docker(command, env, RUN_TIMEOUT)
    if docker_result["timeout"]:
        docker(["rm", "--force", container_name], env, 10.0)

    record_path = output_dir / "record.json"
    failures: list[str] = []
    record: dict[str, Any]
    if not record_path.exists():
        record = {}
        failures.append("container produced no record.json")
    else:
        try:
            record = json.loads(record_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            record = {}
            failures.append(f"invalid record.json: {error}")
    if docker_result["exit_code"] != 0:
        failures.append(f"docker run exit code {docker_result['exit_code']}")
    if docker_result["timeout"]:
        failures.append("docker run exceeded 30-second timeout")
    if len(list(output_dir.glob("record.json"))) != 1:
        failures.append("execution did not produce exactly one record")

    record.update({
        "execution_id": execution_id,
        "fixture_id": fixture,
        "phase": phase,
        "seed": seed,
        "image_id": image_id,
        "docker_start_timestamp": docker_result["start_timestamp"],
        "docker_end_timestamp": docker_result["end_timestamp"],
        "docker_exit_code": docker_result["exit_code"],
        "docker_timeout": docker_result["timeout"],
        "docker_stdout": docker_result["stdout"],
        "docker_stderr": docker_result["stderr"],
    })
    failures.extend(str(item) for item in record.get("invariant_failures", []))
    record["host_invariant_failures"] = failures
    record["valid"] = not failures
    atomic_json(record_path, record)
    return record


def validate(records: list[dict[str, Any]], elapsed: float) -> tuple[dict[str, Any], bool, str]:
    valid = [record for record in records if record.get("valid")]
    dirty = [record for record in valid if record.get("dirty")]
    clean = [record for record in valid if record.get("control")]
    dirty_naive = sum(record.get("naive_accept_at_parent_exit") is True for record in dirty)
    dirty_aware = sum(record.get("aware_accept_at_parent_exit") is True for record in dirty)
    clean_naive = sum(record.get("naive_accept_at_parent_exit") is True for record in clean)
    clean_aware = sum(record.get("aware_accept_at_parent_exit") is True for record in clean)
    safety = [float(record["aware_after_closure_seconds"]) for record in valid if record.get("aware_after_closure_seconds") is not None]
    dirty_lags = [float(record["aware_safety_lag_seconds"]) for record in dirty if record.get("aware_safety_lag_seconds") is not None]
    clean_differences = [
        abs(float(record["aware_completion_timestamp"]) - float(record["naive_completion_timestamp"]))
        for record in clean
        if record.get("aware_completion_timestamp") is not None and record.get("naive_completion_timestamp") is not None
    ]

    by_id = {record["execution_id"]: record for record in valid}
    replay_matches = 0
    compare_fields = (
        "dirty", "control", "parent_exit_code", "naive_accept_at_parent_exit",
        "aware_accept_at_parent_exit", "eventual_aware_accept",
    )
    for fixture in ORDER:
        primary = by_id.get(f"P-{fixture}")
        replay = by_id.get(f"R-{fixture}")
        if primary and replay and all(primary.get(field) == replay.get(field) for field in compare_fields):
            replay_matches += 1

    metrics = {
        "valid_executions": len(valid),
        "dirty_naive_accept_count": dirty_naive,
        "dirty_aware_accept_count": dirty_aware,
        "dirty_aware_reject_count": len(dirty) - dirty_aware,
        "clean_naive_accept_count": clean_naive,
        "clean_aware_accept_count": clean_aware,
        "replay_match_count": replay_matches,
        "minimum_aware_after_closure_seconds": min(safety) if safety else -1.0,
        "minimum_dirty_aware_lag_seconds": min(dirty_lags) if dirty_lags else -1.0,
        "maximum_clean_monitor_latency_difference_seconds": max(clean_differences) if clean_differences else -1.0,
    }
    fixture_valid = len(valid) == 24
    if not fixture_valid:
        return metrics, False, "fixture_invalid"
    supported = all((
        elapsed <= TIME_LIMIT,
        dirty_naive == 12,
        dirty_aware == 0,
        clean_naive == 12,
        clean_aware == 12,
        len(safety) == 24 and all(value >= -0.01 for value in safety),
        len(dirty_lags) == 12 and all(value > 0 for value in dirty_lags),
        len(clean_differences) == 12 and all(value <= 0.10 for value in clean_differences),
        all(record.get("aware_accepted_before_parent_exit") is False for record in valid),
        all(record.get("eventual_aware_accept") is True for record in valid),
        replay_matches == 12,
    ))
    return metrics, True, "supported" if supported else "refuted"


def gate_scalars(gates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, evidence in gates.items():
        result[f"gate_{name}_command"] = json.dumps(evidence["command"])
        result[f"gate_{name}_exit_code"] = int(evidence["exit_code"])
        result[f"gate_{name}_timeout"] = bool(evidence["timeout"])
        result[f"gate_{name}_stdout"] = evidence["stdout"]
        result[f"gate_{name}_stderr"] = evidence["stderr"]
    return result


def main() -> int:
    if sys.version_info[:2] != (3, 12):
        raise SystemExit(f"Python 3.12 is required; got {sys.version.split()[0]}")
    if os.environ.get("PYTHONHASHSEED") != str(SEED):
        raise SystemExit("run with PYTHONHASHSEED=1729")
    random.seed(SEED)
    run_id = time.strftime("%Y%m%dT%H%M%S") + f"-{os.getpid()}"
    run_dir = ARTIFACTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    env = docker_env()

    endpoint = attempt_exact_socket()
    gates = gate_commands(env)
    gates_pass = all(item["exit_code"] == 0 and not item["timeout"] for item in gates.values())
    non_root = not hasattr(os, "geteuid") or os.geteuid() != 0
    preflight: dict[str, Any] = {
        "run_id": run_id,
        "endpoint": endpoint,
        "runner_uid": os.geteuid() if hasattr(os, "geteuid") else -1,
        "runner_non_root": non_root,
        "gates": gates,
    }
    base_id = ""
    image_id = ""
    preparation: dict[str, Any] = {}
    smoke_result: dict[str, Any] = {}
    if gates_pass and non_root:
        base_id, image_id, preparation = prepare_image(run_id, env)
        if image_id:
            smoke_result = smoke(image_id, env)
    smoke_pass = bool(
        smoke_result
        and smoke_result.get("exit_code") == 0
        and smoke_result.get("timeout") is False
        and smoke_result.get("stdout") == "1729\n"
        and smoke_result.get("stderr") == ""
    )
    infrastructure_valid = gates_pass and non_root and bool(image_id) and smoke_pass
    preflight.update({
        "base_image_id": base_id,
        "fixture_image_id": image_id,
        "image_preparation": preparation,
        "smoke": smoke_result,
        "infrastructure_valid": infrastructure_valid,
    })
    atomic_json(run_dir / "preflight.json", preflight)

    if not infrastructure_valid:
        reasons: list[str] = []
        if not gates_pass:
            reasons.append("one or more exact-endpoint Docker gates failed")
        if not non_root:
            reasons.append("harness is running as root")
        if gates_pass and not image_id:
            reasons.append(str(preparation.get("error", "fixture image unavailable")))
        if image_id and not smoke_pass:
            reasons.append("smoke container did not exit 0 with exact stdout '1729\\n' and empty stderr")
        error = "; ".join(reasons)
        atomic_bytes(FIGURE_PATH, png_plot([0, 0, 0, 0], False))
        flat = {
            "error": error,
            "verdict": "infrastructure_invalid",
            "hypothesis_evaluated": False,
            "infrastructure_valid": False,
            "fixtures_scheduled": 0,
            "valid_executions": 0,
            "execution_reliability_count": 0,
            "timed_section_started": False,
            "timed_section_seconds": 0.0,
            "timed_section_pass": False,
            "dirty_naive_accept_count": 0,
            "dirty_aware_accept_count": 0,
            "dirty_aware_reject_count": 0,
            "clean_naive_accept_count": 0,
            "clean_aware_accept_count": 0,
            "replay_match_count": 0,
            "base_image_id": base_id,
            "fixture_image_id": image_id,
            "docker_host": DOCKER_HOST,
            "python_version": platform.python_version(),
            "seed": SEED,
            "figure_path": str(FIGURE_PATH.relative_to(ROOT)),
            "preflight_path": str((run_dir / "preflight.json").relative_to(ROOT)),
            "execution_records_json": "[]",
            **gate_scalars(gates),
        }
        write_flat_results(flat)
        atomic_json(run_dir / "results.json", flat)
        print(f"Ran strict preflight and scheduled 0/24 fixtures. {error}.")
        print("Hypothesis not evaluated (infrastructure_invalid); it is not classified as refuted.")
        return 0

    records: list[dict[str, Any]] = []
    timed_start = monotonic()  # immediately before the first primary docker run
    for phase, prefix in (("primary", "P"), ("replay", "R")):
        for index, fixture in enumerate(ORDER):
            execution_id = f"{prefix}-{fixture}"
            record = execute_one(
                execution_id, fixture, phase, SEED + index, image_id, run_dir, env
            )
            records.append(record)

    # Validation and both artifacts are part of the timed section.
    provisional_elapsed = monotonic() - timed_start
    metrics, evaluated, verdict = validate(records, provisional_elapsed)
    counts = [
        int(metrics["dirty_naive_accept_count"]),
        int(metrics["dirty_aware_accept_count"]),
        int(metrics["clean_naive_accept_count"]),
        int(metrics["clean_aware_accept_count"]),
    ]
    atomic_bytes(FIGURE_PATH, png_plot(counts, True))
    detailed_path = run_dir / "detailed_results.json"
    atomic_json(detailed_path, {
        "records": records,
        "aggregate_metrics": metrics,
        "preflight": preflight,
        "timed_section_start": timed_start,
        "provisional_elapsed_seconds": provisional_elapsed,
        "hypothesis_evaluated": evaluated,
        "verdict": verdict,
    })

    # The first flat write is the last timed artifact operation.  Immediately
    # after its fsync, capture the exact end timestamp; then amend only the
    # elapsed/verdict scalar metadata outside the already-stopped section.
    elapsed_placeholder = 0.0
    flat = {
        "verdict": verdict,
        "hypothesis_evaluated": evaluated,
        "infrastructure_valid": True,
        "fixtures_scheduled": 24,
        "valid_executions": int(metrics["valid_executions"]),
        "execution_reliability_count": int(metrics["valid_executions"]),
        "timed_section_started": True,
        "timed_section_seconds": elapsed_placeholder,
        "timed_section_pass": False,
        "dirty_naive_accept_count": int(metrics["dirty_naive_accept_count"]),
        "dirty_naive_accept_rate": int(metrics["dirty_naive_accept_count"]) / 12,
        "dirty_aware_accept_count": int(metrics["dirty_aware_accept_count"]),
        "dirty_aware_reject_count": int(metrics["dirty_aware_reject_count"]),
        "dirty_aware_reject_rate": int(metrics["dirty_aware_reject_count"]) / 12,
        "clean_naive_accept_count": int(metrics["clean_naive_accept_count"]),
        "clean_naive_accept_rate": int(metrics["clean_naive_accept_count"]) / 12,
        "clean_aware_accept_count": int(metrics["clean_aware_accept_count"]),
        "clean_aware_accept_rate": int(metrics["clean_aware_accept_count"]) / 12,
        "minimum_aware_after_closure_seconds": float(metrics["minimum_aware_after_closure_seconds"]),
        "minimum_dirty_aware_lag_seconds": float(metrics["minimum_dirty_aware_lag_seconds"]),
        "maximum_clean_monitor_latency_difference_seconds": float(metrics["maximum_clean_monitor_latency_difference_seconds"]),
        "replay_match_count": int(metrics["replay_match_count"]),
        "base_image_id": base_id,
        "fixture_image_id": image_id,
        "docker_host": DOCKER_HOST,
        "python_version": platform.python_version(),
        "seed": SEED,
        "figure_path": str(FIGURE_PATH.relative_to(ROOT)),
        "detailed_results_path": str(detailed_path.relative_to(ROOT)),
        "execution_records_json": json.dumps(records, separators=(",", ":"), sort_keys=True),
        **gate_scalars(gates),
    }
    write_flat_results(flat)
    timed_end = monotonic()
    actual_elapsed = timed_end - timed_start
    timed_pass = len(records) == 24 and metrics["valid_executions"] == 24 and actual_elapsed <= TIME_LIMIT
    if evaluated and not timed_pass:
        verdict = "refuted"
    flat["timed_section_seconds"] = actual_elapsed
    flat["timed_section_pass"] = timed_pass
    flat["verdict"] = verdict
    write_flat_results(flat)
    atomic_json(run_dir / "post_timing_measurement.json", {
        "timed_section_start": timed_start,
        "timed_section_end_after_results_fsync": timed_end,
        "actual_elapsed_seconds": actual_elapsed,
    })
    print(f"Ran 24 Docker executions: {metrics['valid_executions']}/24 valid in {actual_elapsed:.3f}s.")
    print(
        f"Dirty naive {metrics['dirty_naive_accept_count']}/12, dirty aware-at-exit "
        f"{metrics['dirty_aware_accept_count']}/12, clean naive {metrics['clean_naive_accept_count']}/12, "
        f"clean aware {metrics['clean_aware_accept_count']}/12; replay agreement "
        f"{metrics['replay_match_count']}/12. Verdict: {verdict}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
