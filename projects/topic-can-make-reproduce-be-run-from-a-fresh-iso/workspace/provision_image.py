#!/usr/bin/env python3
"""Create the offline locked Docker image package from an already-local image.

This is an explicit provisioning step, not part of preflight or the timed
experiment.  It never performs ``docker pull`` and refuses an unsuitable image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
ID_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


def execute(argv: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )


def required(argv: list[str]) -> bytes:
    result = execute(argv)
    if result.returncode != 0:
        raise RuntimeError(
            f"{argv!r} exited {result.returncode}: "
            f"{result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return result.stdout


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image_reference", help="already-local pinned tag or immutable ID")
    args = parser.parse_args()
    raw = required(["docker", "image", "inspect", args.image_reference])
    image = json.loads(raw)[0]
    image_id = image["Id"]
    architecture = image["Architecture"]
    operating_system = image["Os"]
    expected_arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else platform.machine().lower()
    if not ID_PATTERN.fullmatch(image_id):
        raise RuntimeError(f"invalid immutable image ID {image_id!r}")
    if operating_system != "linux" or architecture != expected_arch:
        raise RuntimeError(
            f"local image platform {operating_system}/{architecture} does not equal linux/{expected_arch}"
        )
    smoke = execute(
        [
            "docker", "run", "--rm", "--network", "none", args.image_reference,
            "sh", "-c", "python3 --version && git --version && make --version",
        ]
    )
    if smoke.returncode != 0 or not smoke.stdout.startswith(b"Python 3.12."):
        raise RuntimeError(
            "image lacks the required Python 3.12/Git/Make toolchain: "
            + smoke.stderr.decode("utf-8", "replace").strip()
        )
    image_dir = ROOT / "image"
    image_dir.mkdir(exist_ok=True)
    archive = image_dir / "experiment-image.tar"
    save = execute(["docker", "image", "save", "--output", str(archive), args.image_reference])
    if save.returncode != 0:
        raise RuntimeError(save.stderr.decode("utf-8", "replace").strip())
    lock = {
        "archive_sha256": hash_file(archive),
        "image_id": image_id,
        "image_reference": args.image_reference,
    }
    (ROOT / "image.lock.json").write_text(
        json.dumps(lock, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"Packaged {args.image_reference} as {archive.name}; "
        f"image ID {image_id}; archive SHA-256 {lock['archive_sha256']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"image provisioning failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
