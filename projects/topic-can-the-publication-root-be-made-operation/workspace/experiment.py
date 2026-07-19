#!/usr/bin/env python3
"""Deterministic signed-checkpoint gossip experiment.

The transparency service signs literal 64-record inventory roots.  Verifiers
are configured with the service public key out of band; release artifacts do
not contain a public key.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# Keep Matplotlib's configuration and font cache inside the experiment workspace.
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(Path(__file__).resolve().parent / ".cache"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


MASTER_SEED = hashlib.sha256(b"publication-root-gossip-experiment-v1").digest()
TREE_SIZE = 64
PROOF_DEPTH = 6
CHECKPOINT_PREFIX = b"INVCHKPT-v1\n"
HEX_RE = re.compile(r"^[0-9a-f]+$")
ROOT_DIR = Path(__file__).resolve().parent
CSV_PATH = ROOT_DIR / "scenario_results.csv"
RESULTS_PATH = ROOT_DIR / "results.json"
FIGURE_DIR = ROOT_DIR / "figures"
FIGURE_PATH = FIGURE_DIR / "checkpoint_gossip_results.png"


@dataclass(frozen=True)
class Checkpoint:
    tree_size: int
    root: bytes
    signature: bytes


def derive_signing_key() -> Ed25519PrivateKey:
    private_seed = hmac.new(
        MASTER_SEED, b"ed25519-private-key", hashlib.sha256
    ).digest()
    return Ed25519PrivateKey.from_private_bytes(private_seed)


def canonical_json(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def record_hash(record: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + record).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def merkle_levels(records: list[bytes]) -> list[list[bytes]]:
    if len(records) != TREE_SIZE:
        raise ValueError(f"tree must contain exactly {TREE_SIZE} records")
    levels = [[record_hash(record) for record in records]]
    while len(levels[-1]) > 1:
        current = levels[-1]
        if len(current) % 2:
            raise AssertionError("power-of-two tree unexpectedly had an odd level")
        levels.append(
            [node_hash(current[i], current[i + 1]) for i in range(0, len(current), 2)]
        )
    if len(levels) != PROOF_DEPTH + 1:
        raise AssertionError("unexpected Merkle-tree depth")
    return levels


def inclusion_proof(levels: list[list[bytes]], leaf_index: int) -> list[dict[str, str]]:
    if not 0 <= leaf_index < TREE_SIZE:
        raise ValueError("leaf index is out of range")
    proof: list[dict[str, str]] = []
    position = leaf_index
    for level in levels[:-1]:
        if position % 2 == 0:
            sibling_position = position + 1
            side = "right"
        else:
            sibling_position = position - 1
            side = "left"
        proof.append({"side": side, "hash": level[sibling_position].hex()})
        position //= 2
    if len(proof) != PROOF_DEPTH:
        raise AssertionError("proof does not have exactly six siblings")
    return proof


def checkpoint_bytes(tree_size: int, root: bytes) -> bytes:
    if type(tree_size) is not int or tree_size != TREE_SIZE:
        raise ValueError("checkpoint tree size must be the integer 64")
    if len(root) != 32:
        raise ValueError("checkpoint root must be exactly 32 bytes")
    return CHECKPOINT_PREFIX + tree_size.to_bytes(8, "big") + root


def sign_checkpoint(
    private_key: Ed25519PrivateKey, tree_size: int, root: bytes
) -> Checkpoint:
    signature = private_key.sign(checkpoint_bytes(tree_size, root))
    if len(signature) != 64:
        raise AssertionError("Ed25519 signature was not 64 bytes")
    return Checkpoint(tree_size, root, signature)


def make_artifact(
    checkpoint: Checkpoint,
    leaf_index: int,
    record: bytes,
    proof: list[dict[str, str]],
) -> dict[str, Any]:
    artifact = {
        "tree_size": checkpoint.tree_size,
        "root": checkpoint.root.hex(),
        "signature": checkpoint.signature.hex(),
        "target_leaf_index": leaf_index,
        "target_record": record.decode("utf-8"),
        "proof": proof,
    }
    # Deliberately no public-key field: trust is pinned out of band.
    if "public_key" in artifact:
        raise AssertionError("artifact must not distribute verifier trust configuration")
    return artifact


def decode_exact_lower_hex(value: Any, byte_length: int, label: str) -> bytes:
    if not isinstance(value, str) or len(value) != 2 * byte_length:
        raise ValueError(f"{label} must be exactly {2 * byte_length} hex characters")
    if not HEX_RE.fullmatch(value):
        raise ValueError(f"{label} must be canonical lowercase hexadecimal")
    decoded = bytes.fromhex(value)
    if len(decoded) != byte_length:
        raise ValueError(f"{label} decoded length is invalid")
    return decoded


def parse_checkpoint(artifact: dict[str, Any]) -> Checkpoint:
    tree_size = artifact.get("tree_size")
    if type(tree_size) is not int or tree_size != TREE_SIZE:
        raise ValueError("artifact tree size must be the integer 64")
    root = decode_exact_lower_hex(artifact.get("root"), 32, "root")
    signature = decode_exact_lower_hex(artifact.get("signature"), 64, "signature")
    return Checkpoint(tree_size, root, signature)


def verify_checkpoint_signature(
    checkpoint: Checkpoint, pinned_public_key: Ed25519PublicKey
) -> bool:
    try:
        pinned_public_key.verify(
            checkpoint.signature,
            checkpoint_bytes(checkpoint.tree_size, checkpoint.root),
        )
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def verify_inclusion(
    record: bytes,
    leaf_index: int,
    proof: Any,
    checkpoint_root: bytes,
) -> bool:
    if type(leaf_index) is not int or not 0 <= leaf_index < TREE_SIZE:
        return False
    if not isinstance(proof, list) or len(proof) != PROOF_DEPTH:
        return False

    current = record_hash(record)
    position = leaf_index
    try:
        for step in proof:
            if not isinstance(step, dict) or set(step) != {"side", "hash"}:
                return False
            sibling = decode_exact_lower_hex(step["hash"], 32, "proof sibling")
            expected_side = "right" if position % 2 == 0 else "left"
            if step["side"] != expected_side:
                return False
            if expected_side == "left":
                current = node_hash(sibling, current)
            else:
                current = node_hash(current, sibling)
            position //= 2
    except (KeyError, TypeError, ValueError):
        return False
    return hmac.compare_digest(current, checkpoint_root)


def verify_artifact(
    artifact: dict[str, Any], pinned_public_key: Ed25519PublicKey
) -> bool:
    """Perform isolated signature and inclusion verification of one artifact."""
    try:
        checkpoint = parse_checkpoint(artifact)
        if not verify_checkpoint_signature(checkpoint, pinned_public_key):
            return False
        leaf_index = artifact.get("target_leaf_index")
        record_text = artifact.get("target_record")
        if not isinstance(record_text, str):
            return False
        record = record_text.encode("utf-8", errors="strict")
        return verify_inclusion(record, leaf_index, artifact.get("proof"), checkpoint.root)
    except (UnicodeError, ValueError, TypeError):
        return False


def gossip_alert(
    artifact_a: dict[str, Any],
    artifact_b: dict[str, Any],
    pinned_public_key: Ed25519PublicKey,
) -> bool:
    """Exchange checkpoints once and detect an authenticated equal-size fork."""
    # Gossip is a comparison layered on top of the same local checks as baseline.
    if not verify_artifact(artifact_a, pinned_public_key):
        return False
    if not verify_artifact(artifact_b, pinned_public_key):
        return False
    try:
        checkpoint_a = parse_checkpoint(artifact_a)
        checkpoint_b = parse_checkpoint(artifact_b)
    except (ValueError, TypeError):
        return False
    # Each peer independently authenticates both exchanged checkpoint tuples.
    for _peer in ("A", "B"):
        if not verify_checkpoint_signature(checkpoint_a, pinned_public_key):
            return False
        if not verify_checkpoint_signature(checkpoint_b, pinned_public_key):
            return False
    return (
        checkpoint_a.tree_size == checkpoint_b.tree_size
        and checkpoint_a.root != checkpoint_b.root
    )


def ordinary_records(kind: str, scenario: int) -> list[bytes]:
    records = []
    for index in range(TREE_SIZE):
        nonce = hmac.new(
            MASTER_SEED,
            f"record|{kind}|{scenario}|{index}".encode(),
            hashlib.sha256,
        ).hexdigest()
        records.append(
            canonical_json(
                {
                    "index": index,
                    "kind": kind,
                    "nonce": nonce,
                    "scenario": scenario,
                }
            )
        )
    if len(records) != TREE_SIZE or len(set(records)) != TREE_SIZE:
        raise AssertionError("scenario records are not 64 distinct byte strings")
    return records


def mutated_attack_record(scenario: int, index: int) -> bytes:
    nonce = hmac.new(
        MASTER_SEED,
        f"mutation|attack|{scenario}|{index}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return canonical_json(
        {
            "index": index,
            "kind": "attack",
            "mutation": "fork-B",
            "nonce": nonce,
            "scenario": scenario,
        }
    )


def build_artifact(
    records: list[bytes],
    target_index: int,
    private_key: Ed25519PrivateKey,
) -> dict[str, Any]:
    levels = merkle_levels(records)
    root = levels[-1][0]
    checkpoint = sign_checkpoint(private_key, TREE_SIZE, root)
    return make_artifact(
        checkpoint,
        target_index,
        records[target_index],
        inclusion_proof(levels, target_index),
    )


def tamper_sanity_checks(
    artifact: dict[str, Any], pinned_public_key: Ed25519PublicKey
) -> tuple[bool, bool]:
    root_tampered = json.loads(json.dumps(artifact))
    root = bytearray.fromhex(root_tampered["root"])
    root[0] ^= 0x01
    root_tampered["root"] = bytes(root).hex()
    parsed_tampered = parse_checkpoint(root_tampered)
    root_tamper_rejected = not verify_checkpoint_signature(
        parsed_tampered, pinned_public_key
    )

    proof_tampered = json.loads(json.dumps(artifact))
    sibling = bytearray.fromhex(proof_tampered["proof"][0]["hash"])
    sibling[0] ^= 0x01
    proof_tampered["proof"][0]["hash"] = bytes(sibling).hex()
    parsed_original_checkpoint = parse_checkpoint(proof_tampered)
    if not verify_checkpoint_signature(parsed_original_checkpoint, pinned_public_key):
        raise AssertionError("proof tampering unexpectedly changed the checkpoint")
    proof_tamper_rejected = not verify_artifact(proof_tampered, pinned_public_key)

    if not root_tamper_rejected:
        raise AssertionError("one-bit signed-root tamper passed signature verification")
    if not proof_tamper_rejected:
        raise AssertionError("one-bit proof-sibling tamper passed inclusion verification")
    return root_tamper_rejected, proof_tamper_rejected


def scenario_row(
    scenario_class: str,
    scenario: int,
    artifact_a: dict[str, Any],
    artifact_b: dict[str, Any],
    pinned_public_key: Ed25519PublicKey,
) -> dict[str, Any]:
    accepted_a = verify_artifact(artifact_a, pinned_public_key)
    accepted_b = verify_artifact(artifact_b, pinned_public_key)
    return {
        "class": scenario_class,
        "scenario": scenario,
        "root_a": artifact_a["root"],
        "root_b": artifact_b["root"],
        "local_accept_a": accepted_a,
        "local_accept_b": accepted_b,
        "dual_acceptance": accepted_a and accepted_b,
        "gossip_alert": gossip_alert(artifact_a, artifact_b, pinned_public_key),
    }


def count(rows: Iterable[dict[str, Any]], predicate: Any) -> int:
    return sum(1 for row in rows if predicate(row))


def write_csv(rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "class",
        "scenario",
        "root_a",
        "root_b",
        "local_accept_a",
        "local_accept_b",
        "dual_acceptance",
        "gossip_alert",
    ]
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def make_figure(metrics: dict[str, Any]) -> None:
    FIGURE_DIR.mkdir(exist_ok=True)
    classes = ["Attack", "Control"]
    baseline_rates = [
        metrics["inclusion_only_attack_scenario_alert_rate"],
        metrics["inclusion_only_control_scenario_alert_rate"],
    ]
    gossip_rates = [
        metrics["gossip_attack_true_positive_rate"],
        metrics["gossip_control_false_positive_rate"],
    ]
    baseline_counts = [
        metrics["inclusion_only_attack_scenario_alert_count"],
        metrics["inclusion_only_control_scenario_alert_count"],
    ]
    gossip_counts = [
        metrics["gossip_attack_detection_count"],
        metrics["gossip_control_false_positive_count"],
    ]

    x = [0, 1]
    width = 0.34
    fig, axis = plt.subplots(figsize=(12, 7), dpi=120)
    bars_baseline = axis.bar(
        [value - width / 2 for value in x],
        baseline_rates,
        width,
        label="Inclusion-only local alert",
        color="#5B8FF9",
    )
    bars_gossip = axis.bar(
        [value + width / 2 for value in x],
        gossip_rates,
        width,
        label="Signed-checkpoint gossip alert",
        color="#F6BD16",
    )
    for bars, counts in ((bars_baseline, baseline_counts), (bars_gossip, gossip_counts)):
        for bar, numerator in zip(bars, counts, strict=True):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.025,
                f"{numerator}/64",
                ha="center",
                va="bottom",
                fontsize=11,
                fontweight="bold",
            )
    axis.set_xticks(x, classes)
    axis.set_ylim(0, 1.05)
    axis.set_ylabel("Fraction of scenarios emitting an alert")
    axis.set_title("Split-view detection from signed-checkpoint gossip")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(FIGURE_PATH)
    plt.close(fig)


def run() -> dict[str, Any]:
    private_key = derive_signing_key()
    pinned_public_key = private_key.public_key()
    rows: list[dict[str, Any]] = []
    sanity_artifact: dict[str, Any] | None = None

    for scenario in range(64):
        fork_a_records = ordinary_records("attack", scenario)
        target_index = (13 * scenario + 5) % TREE_SIZE
        mutation_index = (17 * scenario + 3) % TREE_SIZE
        if mutation_index == target_index:
            mutation_index = (mutation_index + 1) % TREE_SIZE
        fork_b_records = list(fork_a_records)
        fork_b_records[mutation_index] = mutated_attack_record(scenario, mutation_index)
        if len(set(fork_b_records)) != TREE_SIZE:
            raise AssertionError("fork B does not have 64 distinct record byte strings")
        if fork_a_records[target_index] != fork_b_records[target_index]:
            raise AssertionError("target record differs across attack forks")
        artifact_a = build_artifact(fork_a_records, target_index, private_key)
        artifact_b = build_artifact(fork_b_records, target_index, private_key)
        if artifact_a["root"] == artifact_b["root"]:
            raise AssertionError("attack fork roots unexpectedly match")
        if sanity_artifact is None:
            sanity_artifact = artifact_a
        rows.append(
            scenario_row(
                "attack", scenario, artifact_a, artifact_b, pinned_public_key
            )
        )

    for scenario in range(64):
        records = ordinary_records("control", scenario)
        target_index = (13 * scenario + 5) % TREE_SIZE
        artifact = build_artifact(records, target_index, private_key)
        # JSON round-tripping produces an independent but identical artifact copy.
        artifact_a = json.loads(json.dumps(artifact))
        artifact_b = json.loads(json.dumps(artifact))
        if (
            artifact_a["tree_size"] != artifact_b["tree_size"]
            or artifact_a["root"] != artifact_b["root"]
        ):
            raise AssertionError("control checkpoints differ")
        rows.append(
            scenario_row(
                "control", scenario, artifact_a, artifact_b, pinned_public_key
            )
        )

    if sanity_artifact is None:
        raise AssertionError("no artifact available for sanity checks")
    root_tamper_rejected, proof_tamper_rejected = tamper_sanity_checks(
        sanity_artifact, pinned_public_key
    )

    attack_rows = [row for row in rows if row["class"] == "attack"]
    control_rows = [row for row in rows if row["class"] == "control"]
    if len(attack_rows) != 64 or len(control_rows) != 64 or len(rows) != 128:
        raise AssertionError("wrong number of scored scenarios")

    attack_dual = count(attack_rows, lambda row: row["dual_acceptance"])
    attack_local_alerts = sum(
        (not row["local_accept_a"]) + (not row["local_accept_b"])
        for row in attack_rows
    )
    attack_scenario_alerts = count(
        attack_rows,
        lambda row: not row["local_accept_a"] or not row["local_accept_b"],
    )
    gossip_attack = count(attack_rows, lambda row: row["gossip_alert"])
    control_dual = count(control_rows, lambda row: row["dual_acceptance"])
    control_local_alerts = sum(
        (not row["local_accept_a"]) + (not row["local_accept_b"])
        for row in control_rows
    )
    control_scenario_alerts = count(
        control_rows,
        lambda row: not row["local_accept_a"] or not row["local_accept_b"],
    )
    gossip_control = count(control_rows, lambda row: row["gossip_alert"])
    inclusion_only_attack_fork_alert_rate = attack_scenario_alerts / 64
    gossip_attack_rate = gossip_attack / 64

    hypothesis_supported = (
        attack_dual == 64
        and gossip_attack == 64
        and attack_local_alerts == 0
        and control_local_alerts == 0
        and control_dual == 64
        and gossip_control == 0
    )
    metrics: dict[str, Any] = {
        "master_seed_hex": MASTER_SEED.hex(),
        "tree_size": TREE_SIZE,
        "attack_scenario_count": 64,
        "attack_view_count": 128,
        "control_scenario_count": 64,
        "control_view_count": 128,
        "total_scored_scenario_count": 128,
        "attack_dual_acceptance_count": attack_dual,
        "attack_dual_acceptance_rate": attack_dual / 64,
        "attack_view_local_alert_count": attack_local_alerts,
        "attack_view_local_alert_rate": attack_local_alerts / 128,
        "inclusion_only_attack_scenario_alert_count": attack_scenario_alerts,
        "inclusion_only_attack_scenario_alert_rate": inclusion_only_attack_fork_alert_rate,
        "gossip_attack_detection_count": gossip_attack,
        "gossip_attack_true_positive_rate": gossip_attack_rate,
        "control_dual_acceptance_count": control_dual,
        "control_dual_acceptance_rate": control_dual / 64,
        "control_view_local_false_alert_count": control_local_alerts,
        "control_view_local_false_alert_rate": control_local_alerts / 128,
        "inclusion_only_control_scenario_alert_count": control_scenario_alerts,
        "inclusion_only_control_scenario_alert_rate": control_scenario_alerts / 64,
        "gossip_control_false_positive_count": gossip_control,
        "gossip_control_false_positive_rate": gossip_control / 64,
        "detection_rate_improvement": gossip_attack_rate
        - inclusion_only_attack_fork_alert_rate,
        "root_bit_tamper_rejected": root_tamper_rejected,
        "proof_sibling_bit_tamper_rejected": proof_tamper_rejected,
        "hypothesis_supported": hypothesis_supported,
        "hypothesis_outcome": "supported" if hypothesis_supported else "refuted",
    }
    if any(isinstance(value, (dict, list, tuple)) for value in metrics.values()):
        raise AssertionError("results must be a flat object of scalar values")

    write_csv(rows)
    RESULTS_PATH.write_text(
        json.dumps(metrics, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    make_figure(metrics)

    outcome = "SUPPORTED" if hypothesis_supported else "REFUTED"
    print("Ran 64 signed split-view attacks and 64 consistent controls.")
    print(
        f"Attack dual acceptance: {attack_dual}/64; "
        f"local attack-view alerts: {attack_local_alerts}/128; "
        f"gossip detections: {gossip_attack}/64."
    )
    print(
        f"Control dual acceptance: {control_dual}/64; "
        f"local control-view alerts: {control_local_alerts}/128; "
        f"gossip false positives: {gossip_control}/64."
    )
    print(
        f"Detection-rate improvement: {metrics['detection_rate_improvement']:.1f}; "
        f"hypothesis {outcome}."
    )
    return metrics


if __name__ == "__main__":
    run()
