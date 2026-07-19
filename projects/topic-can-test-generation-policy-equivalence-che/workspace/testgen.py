"""Deterministic source-policy corpus generator.

This module deliberately owns its domain constants and ZIP writer.  It does not
import either implementation that will later consume the generated archives.
"""

from __future__ import annotations

import io
import json
import random
import zipfile
from pathlib import Path


CORPUS_SEED = 20250308
PRINCIPALS = ["p0", "p1", "p2", "p3"]
ACTIONS = ["a0", "a1", "a2", "a3"]
RESOURCES = ["r0", "r1", "r2", "r3"]
HOURS = [0, 1, 2, 3]
ZONES = ["internal", "external"]


def _archive_bytes(policy: dict) -> bytes:
    payload = (
        json.dumps(
            policy, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        + "\n"
    ).encode("utf-8")
    buffer = io.BytesIO()
    info = zipfile.ZipInfo("policy.json", date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.extra = b""
    info.comment = b""
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.comment = b""
        archive.writestr(info, payload)
    return buffer.getvalue()


def write_archive(policy: dict, path: Path) -> bytes:
    data = _archive_bytes(policy)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _mask_values(rng: random.Random, domain: list) -> list:
    mask = rng.randint(1, (1 << len(domain)) - 1)
    return [value for index, value in enumerate(domain) if mask & (1 << index)]


def _random_rule(rng: random.Random, rule_id: str) -> dict:
    return {
        "id": rule_id,
        "effect": rng.choice(["allow", "deny"]),
        "principals": _mask_values(rng, PRINCIPALS),
        "actions": _mask_values(rng, ACTIONS),
        "resources": _mask_values(rng, RESOURCES),
        "mfa": rng.choice(["any", "required", "forbidden"]),
        "hours": _mask_values(rng, HOURS),
        "zones": _mask_values(rng, ZONES),
        "priority": rng.randint(0, 3),
    }


def _random_policies() -> list[tuple[str, dict]]:
    rng = random.Random(CORPUS_SEED)
    policies = []
    for policy_number in range(1, 113):
        default_effect = rng.choice(["allow", "deny"])
        rules = []
        signatures = set()
        for rule_number in range(rng.randint(2, 6)):
            while True:
                rule = _random_rule(rng, f"r{rule_number:02d}")
                signature = json.dumps(
                    {key: value for key, value in rule.items() if key != "id"},
                    sort_keys=True,
                    separators=(",", ":"),
                )
                if signature not in signatures:
                    signatures.add(signature)
                    rules.append(rule)
                    break
        policies.append(
            (
                f"R{policy_number:03d}",
                {"default_effect": default_effect, "rules": rules},
            )
        )
    return policies


def _rule(
    rule_id: str,
    effect: str,
    principals: list | None = None,
    actions: list | None = None,
    resources: list | None = None,
    mfa: str = "any",
    hours: list | None = None,
    zones: list | None = None,
    priority: int = 0,
) -> dict:
    return {
        "id": rule_id,
        "effect": effect,
        "principals": list(PRINCIPALS if principals is None else principals),
        "actions": list(ACTIONS if actions is None else actions),
        "resources": list(RESOURCES if resources is None else resources),
        "mfa": mfa,
        "hours": list(HOURS if hours is None else hours),
        "zones": list(ZONES if zones is None else zones),
        "priority": priority,
    }


def _edge_policies() -> list[tuple[str, dict]]:
    q0 = (["p0"], ["a0"], ["r0"], "forbidden", [0], ["internal"])
    q1 = (["p1"], ["a1"], ["r1"], "required", [1], ["external"])
    restrictive_allow = _rule("r00", "allow", *q1)
    restrictive_deny = _rule("r00", "deny", *q1)
    edges: list[dict] = [
        {},
        {"default_effect": "allow"},
        {"default_effect": "deny", "rules": [restrictive_allow]},
        {"default_effect": "allow", "rules": [restrictive_deny]},
        {"default_effect": "deny", "rules": [_rule("r00", "allow")]},
        {"default_effect": "allow", "rules": [_rule("r00", "deny")]},
        {
            "default_effect": "deny",
            "rules": [_rule("r00", "allow", *q0), _rule("r01", "allow", *q1)],
        },
        {
            "default_effect": "allow",
            "rules": [_rule("r00", "deny", *q0), _rule("r01", "deny", *q1)],
        },
        {
            "default_effect": "deny",
            "rules": [
                _rule("r00", "allow", priority=3),
                _rule("r01", "deny", priority=0),
            ],
        },
        {
            "default_effect": "allow",
            "rules": [
                _rule("r00", "deny", priority=3),
                _rule("r01", "allow", priority=0),
            ],
        },
        {
            "default_effect": "deny",
            "rules": [
                _rule("r00", "allow", principals=["p0"]),
                _rule("r01", "deny", actions=["a0"]),
                _rule("r02", "allow"),
            ],
        },
        {
            "default_effect": "deny",
            "rules": [
                _rule("r00", "allow", priority=0),
                _rule("r01", "deny", priority=1),
                _rule("r02", "allow", priority=2),
                _rule("r03", "deny", priority=3),
            ],
        },
        {
            "default_effect": "deny",
            "rules": [
                _rule(
                    "r00",
                    "allow",
                    principals=PRINCIPALS[:2],
                    actions=ACTIONS[:2],
                    resources=RESOURCES[:2],
                    mfa="required",
                    hours=HOURS[:2],
                    zones=ZONES,
                )
            ],
        },
        {
            "default_effect": "allow",
            "rules": [
                _rule(
                    "r00",
                    "deny",
                    principals=PRINCIPALS[:2],
                    actions=ACTIONS[:2],
                    resources=RESOURCES[:2],
                    mfa="forbidden",
                    hours=HOURS[:2],
                    zones=ZONES,
                )
            ],
        },
        {
            "default_effect": "deny",
            "rules": [_rule("r00", "allow", *q0), _rule("r01", "allow", *q1)],
        },
        {
            "default_effect": "allow",
            "rules": [_rule("r00", "deny", *q0), _rule("r01", "deny", *q1)],
        },
    ]
    return [(f"E{index:02d}", policy) for index, policy in enumerate(edges, 1)]


def generate_corpus(output_dir: Path) -> dict[str, bytes]:
    corpus = _random_policies() + _edge_policies()
    if len(corpus) != 128:
        raise AssertionError(f"expected 128 policies, got {len(corpus)}")
    archives = {}
    for policy_id, policy in corpus:
        archives[policy_id] = write_archive(policy, output_dir / f"{policy_id}.zip")
    return archives
