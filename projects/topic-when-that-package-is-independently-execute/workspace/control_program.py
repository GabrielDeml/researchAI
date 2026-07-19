"""Deterministic CSV generator used by the strace parser controls."""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path


SEEDS = (101, 202, 303)


def csv_bytes(seed: int) -> bytes:
    # Build text explicitly so the expected UTF-8 encoding and LF convention do
    # not depend on the platform's text-file newline translation.
    lines = ["seed,row,value\n"]
    rng = random.Random(seed)
    for row in range(128):
        lines.append(f"{seed},{row},{rng.randrange(0, 1_000_000)}\n")
    return "".join(lines).encode("utf-8")


def create_files(output: Path, exclusive: bool) -> None:
    output.mkdir(parents=True, exist_ok=False)
    mode = "xb" if exclusive else "wb"
    for seed in SEEDS:
        with (output / f"seed_{seed}.csv").open(mode) as stream:
            stream.write(csv_bytes(seed))


def negative_rewrite(output: Path) -> None:
    for seed in SEEDS:
        path = output / f"seed_{seed}.csv"
        with path.open("rb") as stream:
            if len(stream.read(1)) != 1:
                raise RuntimeError(f"negative-control read failed: {path}")
        with path.open("wb") as stream:
            stream.write(csv_bytes(seed))


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in {"positive", "prepare-negative", "negative"}:
        print("usage: control_program.py MODE OUTPUT_DIRECTORY", file=sys.stderr)
        return 2
    mode, output_text = argv[1:]
    output = Path(output_text)
    if mode == "positive":
        create_files(output, exclusive=True)
    elif mode == "prepare-negative":
        create_files(output, exclusive=True)
    else:
        negative_rewrite(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
