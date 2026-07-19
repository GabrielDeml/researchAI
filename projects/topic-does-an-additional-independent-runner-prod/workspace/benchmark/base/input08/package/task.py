#!/usr/bin/env python3
import argparse
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

PACKAGE_ID = 'input08'
MODE = 'input'


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
