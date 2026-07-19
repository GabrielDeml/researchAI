#!/usr/bin/env python3
"""Independent verifier for captured make-reproduce evidence.

This file intentionally imports no experiment, generator, builder, or harness
module.  It uses only the Python standard library and evidence on disk.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import time
from typing import Any, Callable
import zlib


ROOT = Path(__file__).resolve().parent
EXPECTED = ("histogram.bin", "samples.csv", "summary.json")
RUNS = 6
EVIDENCE_REQUIRED = 66
REPLAY_REQUIRED = 18
REFERENCE_REQUIRED = 18


def canonical_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def invoke(argv: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except OSError as exc:
        return subprocess.CompletedProcess(argv, 127, b"", (str(exc) + "\n").encode())


def require_command(argv: list[str], cwd: Path | None = None) -> bytes:
    result = invoke(argv, cwd)
    if result.returncode != 0:
        raise AssertionError(
            f"command {argv!r} exited {result.returncode}: "
            f"{result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return result.stdout


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} is not a JSON object")
    return value


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def strict_inventory(directory: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    assert_true(directory.is_dir() and not directory.is_symlink(), f"invalid directory {directory}")
    paths: list[Path] = []
    for entry in directory.rglob("*"):
        assert_true(entry.is_file() and not entry.is_symlink(), f"non-regular entry {entry}")
        paths.append(entry)
    names = sorted(path.relative_to(directory).as_posix() for path in paths)
    assert_true(tuple(names) == EXPECTED, f"unexpected inventory {names!r}")
    lookup = {path.relative_to(directory).as_posix(): path for path in paths}
    inventory = [{"path": name, "size": lookup[name].stat().st_size} for name in names]
    hashes = {name: sha256(lookup[name]) for name in names}
    return inventory, hashes


def fresh_interpreter(image_reference: str) -> str:
    raw = require_command(
        [
            "docker", "run", "--rm", "--network", "none", image_reference,
            "python3", "-c", "import os,sys; print(os.path.realpath(sys.executable))",
        ]
    )
    lines = raw.decode("utf-8", "strict").splitlines()
    assert_true(len(lines) == 1 and lines[0].startswith("/"), f"invalid interpreter probe {lines!r}")
    return lines[0]


def evaluate_category(
    run_number: int,
    category: int,
    name: str,
    check: Callable[[], None],
    failures: list[dict[str, Any]],
) -> bool:
    try:
        check()
        return True
    except Exception as exc:
        failures.append(
            {
                "run_number": run_number,
                "category": category,
                "name": name,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        return False


FONT: dict[str, tuple[str, ...]] = {
    " ": ("00000",) * 7,
    "/": ("00001", "00010", "00100", "01000", "10000", "00000", "00000"),
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
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
}


def png_chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def draw_text(
    pixels: bytearray,
    width: int,
    x: int,
    y: int,
    value: str,
    scale: int,
    color: tuple[int, int, int],
) -> None:
    for character in value.upper():
        glyph = FONT.get(character, FONT[" "])
        for row, bits in enumerate(glyph):
            for column, bit in enumerate(bits):
                if bit == "1":
                    for dy in range(scale):
                        for dx in range(scale):
                            offset = ((y + row * scale + dy) * width + x + column * scale + dx) * 3
                            pixels[offset:offset + 3] = bytes(color)
        x += 6 * scale


def write_summary_png(path: Path, evidence_passed: int, replay_passed: int) -> None:
    width, height = 1200, 700
    white = (255, 255, 255)
    navy = (35, 74, 118)
    green = (47, 158, 68)
    gray = (220, 225, 230)
    black = (20, 24, 28)
    pixels = bytearray(bytes(white) * width * height)
    baseline, top = 560, 90
    bar_width = 260
    locations = ((250, evidence_passed, 66, navy), (690, replay_passed, 18, green))
    for x, passed, required, color in locations:
        for yy in range(top, baseline):
            for xx in range(x, x + bar_width):
                offset = (yy * width + xx) * 3
                pixels[offset:offset + 3] = bytes(gray)
        fill = round((baseline - top) * min(max(passed, 0), required) / required)
        for yy in range(baseline - fill, baseline):
            for xx in range(x, x + bar_width):
                offset = (yy * width + xx) * 3
                pixels[offset:offset + 3] = bytes(color)
        annotation = f"{passed}/{required}"
        text_width = len(annotation) * 6 * 5
        draw_text(pixels, width, x + (bar_width - text_width) // 2, 40, annotation, 5, black)
    draw_text(pixels, width, 239, 595, "Evidence fields", 3, black)
    draw_text(pixels, width, 720, 595, "Replay bytes", 3, black)
    scanlines = bytearray()
    stride = width * 3
    for y in range(height):
        scanlines.append(0)
        scanlines.extend(pixels[y * stride:(y + 1) * stride])
    description = b"Evidence fields and Replay bytes verification summary"
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + png_chunk(b"tEXt", b"Description\x00" + description)
        + png_chunk(b"IDAT", zlib.compress(bytes(scanlines), 9))
        + png_chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def main() -> int:
    verification_start = time.time()
    lock = load_json(ROOT / "image.lock.json")
    manifest = load_json(ROOT / "experiment_manifest.json")
    timing = load_json(ROOT / "timing.json")
    revision = manifest["artifact_revision"]
    image_reference = lock["image_reference"]
    image_id = lock["image_id"]
    inspected_id = require_command(
        ["docker", "image", "inspect", image_reference, "--format", "{{.Id}}"]
    ).decode("ascii", "strict").strip()
    failures: list[dict[str, Any]] = []
    passed_categories = 0
    replay_bytes_passed = 0
    reference_bytes_passed = 0
    successful_executions = 0
    all_streams_integral = True

    for number in range(1, RUNS + 1):
        p_dir = ROOT / f"primary-{number:02d}" / "checkout"
        r_dir = ROOT / f"replay-{number:02d}" / "checkout"
        p_evidence = ROOT / "evidence" / f"primary-{number:02d}"
        r_evidence = ROOT / "evidence" / f"replay-{number:02d}"
        primary = load_json(p_evidence / "record.json")
        replay = load_json(r_evidence / "record.json")
        if type(primary.get("exit_status")) is int and primary["exit_status"] == 0:
            successful_executions += 1
        if type(replay.get("exit_status")) is int and replay["exit_status"] == 0:
            successful_executions += 1
        fresh_path_error: Exception | None = None
        try:
            resolved_now = fresh_interpreter(image_reference)
        except Exception as exc:
            resolved_now = ""
            fresh_path_error = exc

        def category_1() -> None:
            p_head = require_command(["git", "rev-parse", "HEAD"], p_dir).decode("ascii").strip()
            r_head = require_command(["git", "rev-parse", "HEAD"], r_dir).decode("ascii").strip()
            assert_true(primary.get("checkout_revision") == revision == p_head, "primary revision mismatch")
            assert_true(replay.get("checkout_revision") == revision == r_head, "replay revision mismatch")

        def category_2() -> None:
            assert_true(primary.get("image_reference") == image_reference, "primary image reference mismatch")
            assert_true(replay.get("image_reference") == image_reference, "replay image reference mismatch")
            assert_true(primary.get("image_id") == image_id == inspected_id, "primary/current image ID mismatch")
            assert_true(replay.get("image_id") == image_id == inspected_id, "replay/current image ID mismatch")

        def category_3() -> None:
            if fresh_path_error is not None:
                raise fresh_path_error
            path = primary.get("interpreter_path")
            assert_true(isinstance(path, str) and path.startswith("/"), "primary interpreter is not absolute")
            assert_true(path == resolved_now == replay.get("interpreter_path"), "interpreter paths mismatch")

        def category_4() -> None:
            assert_true(primary.get("literal_command") == "make reproduce", "primary literal command mismatch")
            assert_true(replay.get("literal_command") == "make reproduce", "replay literal command mismatch")
            assert_true(primary.get("container_command_args") == ["make", "reproduce"], "primary container args mismatch")
            assert_true(replay.get("container_command_args") == ["make", "reproduce"], "replay container args mismatch")

        def category_5() -> None:
            assert_true(type(primary.get("exit_status")) is int and primary["exit_status"] == 0, "primary exit not integer zero")
            assert_true(type(replay.get("exit_status")) is int and replay["exit_status"] == 0, "replay exit not integer zero")

        def check_stream(name: str) -> None:
            nonlocal all_streams_integral
            p_path = p_evidence / f"{name}.log"
            r_path = r_evidence / f"{name}.log"
            p_bytes = p_path.read_bytes()
            r_bytes = r_path.read_bytes()
            p_record = primary.get(name)
            r_record = replay.get(name)
            valid = (
                isinstance(p_record, dict)
                and isinstance(r_record, dict)
                and p_record.get("bytes") == len(p_bytes)
                and p_record.get("sha256") == hashlib.sha256(p_bytes).hexdigest()
                and r_record.get("bytes") == len(r_bytes)
                and r_record.get("sha256") == hashlib.sha256(r_bytes).hexdigest()
                and p_record.get("sha256") == r_record.get("sha256")
            )
            if not valid:
                all_streams_integral = False
            assert_true(valid, f"{name} record/replay mismatch")

        def category_6() -> None:
            check_stream("stdout")

        def category_7() -> None:
            check_stream("stderr")

        def category_8() -> None:
            p_inventory, _ = strict_inventory(p_dir / "generated")
            r_inventory, _ = strict_inventory(r_dir / "generated")
            assert_true(p_inventory == primary.get("generated_inventory"), "primary generated inventory mismatch")
            assert_true(r_inventory == replay.get("generated_inventory"), "replay generated inventory mismatch")
            assert_true(p_inventory == r_inventory, "primary/replay generated inventories mismatch")

        def category_9() -> None:
            _, p_hashes = strict_inventory(p_dir / "generated")
            _, r_hashes = strict_inventory(r_dir / "generated")
            assert_true(p_hashes == primary.get("generated_sha256"), "primary generated hashes mismatch")
            assert_true(r_hashes == replay.get("generated_sha256"), "replay generated hashes mismatch")
            assert_true(p_hashes == r_hashes, "primary/replay generated hashes mismatch")

        def category_10() -> None:
            p_inventory, p_hashes = strict_inventory(p_dir / "reference")
            r_inventory, r_hashes = strict_inventory(r_dir / "reference")
            assert_true(p_inventory == primary.get("reference_inventory"), "primary reference inventory mismatch")
            assert_true(r_inventory == replay.get("reference_inventory"), "replay reference inventory mismatch")
            assert_true(p_hashes == primary.get("reference_sha256"), "primary reference hashes mismatch")
            assert_true(r_hashes == replay.get("reference_sha256"), "replay reference hashes mismatch")
            assert_true(p_inventory == r_inventory and p_hashes == r_hashes, "references changed in replay")

        def category_11() -> None:
            _, p_generated = strict_inventory(p_dir / "generated")
            _, p_reference = strict_inventory(p_dir / "reference")
            _, r_generated = strict_inventory(r_dir / "generated")
            _, r_reference = strict_inventory(r_dir / "reference")
            for output in EXPECTED:
                p_byte = (p_dir / "generated" / output).read_bytes() == (p_dir / "reference" / output).read_bytes()
                r_byte = (r_dir / "generated" / output).read_bytes() == (r_dir / "reference" / output).read_bytes()
                p_expected = {
                    "generated_sha256": p_generated[output],
                    "reference_sha256": p_reference[output],
                    "byte_equal": p_byte,
                    "hash_equal": p_generated[output] == p_reference[output],
                }
                r_expected = {
                    "generated_sha256": r_generated[output],
                    "reference_sha256": r_reference[output],
                    "byte_equal": r_byte,
                    "hash_equal": r_generated[output] == r_reference[output],
                }
                assert_true(primary.get("comparisons", {}).get(output) == p_expected, f"primary comparison mismatch for {output}")
                assert_true(replay.get("comparisons", {}).get(output) == r_expected, f"replay comparison mismatch for {output}")
                assert_true(all((p_byte, r_byte, p_expected["hash_equal"], r_expected["hash_equal"])), f"false comparison for {output}")

        checks = (
            (1, "checkout_revision", category_1),
            (2, "immutable_image", category_2),
            (3, "interpreter_path", category_3),
            (4, "literal_and_container_command", category_4),
            (5, "exit_status", category_5),
            (6, "stdout_integrity", category_6),
            (7, "stderr_integrity", category_7),
            (8, "generated_inventory", category_8),
            (9, "generated_hashes", category_9),
            (10, "reference_integrity", category_10),
            (11, "output_comparisons", category_11),
        )
        for category, name, check in checks:
            passed_categories += int(evaluate_category(number, category, name, check, failures))

        for output in EXPECTED:
            try:
                equal = (p_dir / "generated" / output).read_bytes() == (r_dir / "generated" / output).read_bytes()
            except OSError:
                equal = False
            replay_bytes_passed += int(equal)
            try:
                reference_equal = (p_dir / "generated" / output).read_bytes() == (p_dir / "reference" / output).read_bytes()
            except OSError:
                reference_equal = False
            reference_bytes_passed += int(reference_equal)

    png = ROOT / "verification_summary.png"
    write_summary_png(png, passed_categories, replay_bytes_passed)
    (ROOT / "figures").mkdir(exist_ok=True)
    shutil.copyfile(png, ROOT / "figures" / "verification_summary.png")
    elapsed = time.time() - float(timing["timed_start_unix_seconds"])
    png_ok = png.is_file() and png.stat().st_size > 0
    complete = successful_executions == 12
    exact_counts = passed_categories == EVIDENCE_REQUIRED and replay_bytes_passed == REPLAY_REQUIRED
    reference_ok = reference_bytes_passed == REFERENCE_REQUIRED
    within_limit = elapsed <= float(timing.get("limit_seconds", 1200))
    if not within_limit:
        classification = "BROKEN"
    elif complete and exact_counts and reference_ok and all_streams_integral and png_ok:
        classification = "SUPPORTED"
    else:
        classification = "REFUTED"
    verification = {
        "evidence_checks": {
            "attempted": EVIDENCE_REQUIRED,
            "passed": passed_categories,
            "failed": EVIDENCE_REQUIRED - passed_categories,
        },
        "replay_byte_comparisons": {
            "attempted": REPLAY_REQUIRED,
            "passed": replay_bytes_passed,
            "failed": REPLAY_REQUIRED - replay_bytes_passed,
        },
        "reference_byte_comparisons": {
            "attempted": REFERENCE_REQUIRED,
            "passed": reference_bytes_passed,
            "failed": REFERENCE_REQUIRED - reference_bytes_passed,
        },
        "individual_failures": failures,
        "elapsed_seconds": round(elapsed, 6),
        "verification_elapsed_seconds": round(time.time() - verification_start, 6),
        "classification": classification,
    }
    canonical_json(ROOT / "verification.json", verification)
    flat = {
        "classification": classification,
        "preflight_status": "PASSED",
        "error": "" if classification == "SUPPORTED" else "one or more support criteria failed",
        "artifact_seed": 20250308,
        "primary_runs_attempted": 6,
        "primary_runs_completed": 6,
        "replay_runs_attempted": 6,
        "replay_runs_completed": 6,
        "successful_executions": successful_executions,
        "total_executions_required": 12,
        "execution_completion_rate": successful_executions / 12,
        "evidence_checks_attempted": EVIDENCE_REQUIRED,
        "evidence_checks_passed": passed_categories,
        "evidence_verification_rate": passed_categories / EVIDENCE_REQUIRED,
        "replay_byte_comparisons_attempted": REPLAY_REQUIRED,
        "replay_byte_comparisons_passed": replay_bytes_passed,
        "replay_byte_agreement": replay_bytes_passed / REPLAY_REQUIRED,
        "reference_byte_comparisons_attempted": REFERENCE_REQUIRED,
        "reference_byte_comparisons_passed": reference_bytes_passed,
        "released_reference_agreement": reference_bytes_passed / REFERENCE_REQUIRED,
        "stream_separation_integrity": all_streams_integral,
        "timed_elapsed_seconds": round(elapsed, 6),
        "timed_limit_seconds": 1200,
        "timed_within_limit": within_limit,
        "png_exists_nonempty": png_ok,
    }
    canonical_json(ROOT / "results.json", flat)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
