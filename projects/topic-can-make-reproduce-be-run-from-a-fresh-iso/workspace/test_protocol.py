#!/usr/bin/env python3
"""Offline standard-library contract tests for the experiment package."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import subprocess
import tempfile

import experiment
import verify


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="reproduce-contract-") as temporary:
        root = Path(temporary)
        (root / "reproduce.py").write_text(experiment.REPRODUCE_PY, encoding="utf-8", newline="\n")
        (root / "build_references.py").write_text(
            experiment.BUILD_REFERENCES_PY, encoding="utf-8", newline="\n"
        )
        reference = subprocess.run(
            [experiment.sys.executable, "build_references.py"],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        generated = subprocess.run(
            [experiment.sys.executable, "reproduce.py"],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert reference.returncode == 0
        assert generated.returncode == 0
        assert generated.stdout == b"generated 3 files from 10000 records\n"
        assert generated.stderr == b"seed=20250308\n"
        generated_names = sorted(path.name for path in (root / "generated").iterdir())
        reference_names = sorted(path.name for path in (root / "reference").iterdir())
        assert generated_names == reference_names == list(experiment.EXPECTED)
        for name in experiment.EXPECTED:
            assert (root / "generated" / name).read_bytes() == (root / "reference" / name).read_bytes()
        csv_payload = (root / "generated" / "samples.csv").read_bytes()
        assert csv_payload.startswith(b"i,x,y\n")
        assert csv_payload.count(b"\n") == 10001
        summary = json.loads((root / "generated" / "summary.json").read_text(encoding="utf-8"))
        assert summary["n"] == 10000
        histogram = (root / "generated" / "histogram.bin").read_bytes()
        assert len(histogram) == 1024
        assert sum(struct.unpack("<256I", histogram)) == 10000
        png = root / "verification_summary.png"
        verify.write_summary_png(png, 66, 18)
        payload = png.read_bytes()
        assert payload[:8] == b"\x89PNG\r\n\x1a\n"
        width, height = struct.unpack(">II", payload[16:24])
        assert (width, height) == (1200, 700)
    print("Offline contract tests passed: independent outputs match, streams are exact, PNG is 1200x700.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
