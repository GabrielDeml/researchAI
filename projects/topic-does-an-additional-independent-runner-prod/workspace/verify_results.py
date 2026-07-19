#!/usr/bin/env python3
"""Independent structural verification for the generated experiment outputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PACKAGE_IDS = (
    [f"wd{i:02d}" for i in range(1, 9)]
    + [f"input{i:02d}" for i in range(1, 9)]
    + [f"output{i:02d}" for i in range(1, 9)]
)
EXPECTED_INSTRUCTIONS = {
    "wd": "Run task.py from the supplied experiment files; it reads data/input.csv and writes results/artifact.json.",
    "input": "Run package/task.py using data as the input root and write the result to the OUTPUT_ARTIFACT path supplied by the runner.",
    "output": "Run package/task.py with the supplied INPUT_FILE and place the result in results.",
}


def category(package_id: str) -> str:
    return "wd" if package_id.startswith("wd") else (
        "input" if package_id.startswith("input") else "output"
    )


def read_input(path: Path) -> list[tuple[int, int]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == ["id", "value"]
        rows = [(int(row["id"]), int(row["value"])) for row in reader]
    assert len(rows) == 64
    assert [row_id for row_id, _ in rows] == list(range(64))
    return rows


def validate_base() -> None:
    base = ROOT / "benchmark" / "base"
    assert sorted(path.name for path in base.iterdir()) == sorted(PACKAGE_IDS)
    for package_index, package_id in enumerate(PACKAGE_IDS, start=1):
        sandbox = base / package_id
        package = sandbox / "package"
        assert package.is_dir()
        assert (package / "instruction.txt").read_text(encoding="utf-8") == (
            EXPECTED_INSTRUCTIONS[category(package_id)]
        )
        package_rows = read_input(package / "data" / "input.csv")
        workspace_input = sandbox / "data" / "input.csv"
        within_category = int(package_id[-2:])
        should_exist = (
            category(package_id) == "wd" and within_category >= 5
        ) or (
            category(package_id) == "input" and within_category <= 4
        )
        assert workspace_input.exists() == should_exist
        if should_exist:
            workspace_rows = read_input(workspace_input)
            assert all(
                workspace_id == package_id_value
                and workspace_value == package_value + 100000 + package_index
                for (package_id_value, package_value), (workspace_id, workspace_value)
                in zip(package_rows, workspace_rows)
            )


def validate_protocols_and_artifacts() -> None:
    runs = ROOT / "benchmark" / "runs"
    artifact_count = 0
    for mode in ("ambiguous", "canonical"):
        for runner in ("package-relative", "workspace-relative"):
            runner_root = runs / mode / runner
            assert sorted(path.name for path in runner_root.iterdir()) == sorted(PACKAGE_IDS)
            for package_id in PACKAGE_IDS:
                sandbox = runner_root / package_id
                package = sandbox / "package"
                if mode == "canonical":
                    assert not (package / "instruction.txt").exists()
                    protocol = json.loads(
                        (package / "protocol.json").read_text(encoding="utf-8")
                    )
                    assert protocol["schema_version"] == 1
                    assert Path(protocol["cwd"]).is_absolute()
                    assert all(Path(value).is_absolute() for value in protocol["argv"][:2])
                    assert all(Path(value).is_absolute() for value in protocol["roles"].values())
                for artifact in sandbox.rglob("artifact.json"):
                    artifact_count += 1
                    payload = artifact.read_bytes()
                    assert payload.endswith(b"\n") and not payload.endswith(b"\n\n")
                    record = json.loads(payload)
                    expected = json.dumps(
                        record, sort_keys=True, separators=(",", ":")
                    ).encode("utf-8") + b"\n"
                    assert payload == expected
                    assert record["package_id"] == package_id
                    assert record["row_count"] == 64
                    assert len(record["input_sha256"]) == 64
    # Ambiguous mode has 16 paired successes (32 artifacts) plus 8 one-sided
    # successes; all 48 canonical runs succeed.
    assert artifact_count == 88, artifact_count


def validate_results() -> None:
    metrics = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))
    assert isinstance(metrics, dict)
    assert all(isinstance(value, (str, int, float, bool)) for value in metrics.values())
    expected_headlines = {
        "ambiguous_outcome_disagreement_count": 24,
        "ambiguous_disagreement_rate": 1.0,
        "preflight_disagreement_count": 8,
        "artifact_manifest_disagreement_count": 16,
        "artifact_hash_disagreement_count": 8,
        "canonical_success_count": 24,
        "canonical_outcome_agreement_count": 24,
        "canonical_artifact_hash_agreement_count": 24,
        "hypothesis_supported": True,
        "hypothesis_result": "SUPPORTED",
    }
    for key, expected in expected_headlines.items():
        assert metrics[key] == expected, (key, metrics[key], expected)

    with (ROOT / "results.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 48
    assert len({(row["mode"], row["package_id"]) for row in rows}) == 48
    canonical_rows = [row for row in rows if row["mode"] == "canonical"]
    assert len(canonical_rows) == 24
    for row in canonical_rows:
        assert row["both_success"] == "True"
        assert row["outcome_disagreement"] == "False"
        assert row["artifact_hash_agreement"] == "True"
        assert json.loads(row["runner_a_outcome"]) == json.loads(row["runner_b_outcome"])

    figure = ROOT / "figures" / "disagreement_rates.png"
    assert figure.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert figure.stat().st_size > 10_000


def main() -> int:
    validate_base()
    validate_protocols_and_artifacts()
    validate_results()
    print("Verified fixtures, 96 isolated runs, 88 artifacts, 48 result rows, flat metrics JSON, and PNG output.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
