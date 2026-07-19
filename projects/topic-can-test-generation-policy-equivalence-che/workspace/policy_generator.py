"""Deterministic source-policy generation for the equivalence experiment."""

from __future__ import annotations

import random


SEED = 20250308
SUBJECTS = ["s0", "s1", "s2", "s3"]
ACTIONS = ["a0", "a1", "a2", "a3"]
RESOURCES = ["r0", "r1", "r2", "r3"]
TIME_SLOTS = [0, 1, 2, 3]
REGIONS = ["g0", "g1", "g2", "g3"]
CLEARANCES = [0, 1, 2, 3]
MFA = [False, True]
AMOUNTS = [0, 1, 2, 3]

UNIVERSES = {
    "subjects": SUBJECTS,
    "actions": ACTIONS,
    "resources": RESOURCES,
    "time_slots": TIME_SLOTS,
    "regions": REGIONS,
    "clearances": CLEARANCES,
    "MFA": MFA,
    "amounts": AMOUNTS,
}


def bit(value: int, index: int) -> int:
    return (value >> index) & 1


def generate_source_policies() -> list[dict]:
    """Return the exactly 128 required case/source definitions."""
    shuffled = list(range(128))
    random.Random(SEED).shuffle(shuffled)
    cases: list[dict] = []
    for index, x in enumerate(shuffled):
        case_id = f"T{index:03d}"
        policy = {
            "policy_id": case_id,
            "effect": "allow",
            "subjects": sorted(
                {f"s{x % 4}", f"s{(x + 1 + bit(x, 0)) % 4}"}
            ),
            "actions": sorted(
                {f"a{(x // 4) % 4}", f"a{((x // 4) + 1 + bit(x, 1)) % 4}"}
            ),
            "resources": sorted(
                {
                    f"r{(x // 16) % 4}",
                    f"r{((x // 16) + 1 + bit(x, 2)) % 4}",
                }
            ),
            "time_slots": sorted({x % 4, (x + 1 + bit(x, 3)) % 4}),
            "regions": sorted(
                {f"g{(x // 8) % 4}", f"g{((x // 8) + 1 + bit(x, 4)) % 4}"}
            ),
            "min_clearance": 1 + (x % 3),
            "require_mfa": bool(bit(x, 5)),
            "max_amount": x % 3,
        }
        cases.append({"case_id": case_id, "x": x, "source_policy": policy})
    assert len(cases) == 128
    assert sorted(item["x"] for item in cases) == list(range(128))
    return cases
