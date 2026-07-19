#!/usr/bin/env python3
"""Create the final publication manifest in a fresh interpreter."""

from __future__ import annotations

import argparse
from pathlib import Path

from audit_common import canonical_json_bytes, sha256_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    inventory_path = args.root / "records/artifact_inventory.jsonl"
    roots = ["artifacts", "fresh_process", "records", "figures"]
    files = []
    for directory in roots:
        for path in (args.root / directory).rglob("*"):
            if path.is_file() and path != inventory_path:
                files.append(path)
    files.sort(key=lambda path: path.relative_to(args.root).as_posix())
    with inventory_path.open("wb") as handle:
        for path in files:
            row = {
                "path": path.relative_to(args.root).as_posix(),
                "byte_length": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            handle.write(canonical_json_bytes(row))
    print(sha256_file(inventory_path))


if __name__ == "__main__":
    main()
