"""Independent exact finite-domain semantic oracle using integer bit masks."""

from __future__ import annotations

import itertools


SUBJECTS = ["s0", "s1", "s2", "s3"]
ACTIONS = ["a0", "a1", "a2", "a3"]
RESOURCES = ["r0", "r1", "r2", "r3"]
TIME_SLOTS = [0, 1, 2, 3]
REGIONS = ["g0", "g1", "g2", "g3"]
CLEARANCES = [0, 1, 2, 3]
MFA_VALUES = [False, True]
AMOUNTS = [0, 1, 2, 3]
DOMAINS = (
    SUBJECTS,
    ACTIONS,
    RESOURCES,
    TIME_SLOTS,
    REGIONS,
    CLEARANCES,
    MFA_VALUES,
    AMOUNTS,
)
REQUEST_DOMAIN_SIZE = 4 * 4 * 4 * 4 * 4 * 4 * 2 * 4


def _build_value_masks() -> list[dict[object, int]]:
    masks = [{value: 0 for value in domain} for domain in DOMAINS]
    for request_index, request in enumerate(itertools.product(*DOMAINS)):
        request_bit = 1 << request_index
        for dimension, value in enumerate(request):
            masks[dimension][value] |= request_bit
    return masks


VALUE_MASKS = _build_value_masks()
ALL_REQUESTS_MASK = (1 << REQUEST_DOMAIN_SIZE) - 1


def _union_mask(dimension: int, values: list) -> int:
    mask = 0
    for value in values:
        mask |= VALUE_MASKS[dimension][value]
    return mask


def policy_bitset(policy: dict) -> int:
    """Return bit j=1 exactly when lexicographic request j is allowed."""
    if policy["effect"] != "allow":
        return 0
    result = ALL_REQUESTS_MASK
    result &= _union_mask(0, policy["subjects"])
    result &= _union_mask(1, policy["actions"])
    result &= _union_mask(2, policy["resources"])
    result &= _union_mask(3, policy["time_slots"])
    result &= _union_mask(4, policy["regions"])
    result &= _union_mask(
        5, [value for value in CLEARANCES if value >= policy["min_clearance"]]
    )
    if policy["require_mfa"]:
        result &= VALUE_MASKS[6][True]
    result &= _union_mask(7, [value for value in AMOUNTS if value <= policy["max_amount"]])
    return result


def behavioral_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def decode_request(index: int) -> dict:
    if not 0 <= index < REQUEST_DOMAIN_SIZE:
        raise ValueError("request index out of range")
    positions = [0] * len(DOMAINS)
    remainder = index
    for dimension in range(len(DOMAINS) - 1, -1, -1):
        remainder, positions[dimension] = divmod(remainder, len(DOMAINS[dimension]))
    values = [DOMAINS[i][positions[i]] for i in range(len(DOMAINS))]
    return dict(
        zip(
            (
                "subject",
                "action",
                "resource",
                "time_slot",
                "region",
                "clearance",
                "require_mfa_value",
                "amount",
            ),
            values,
            strict=True,
        )
    )


def first_counterexample(left: int, right: int) -> dict | None:
    difference = left ^ right
    if not difference:
        return None
    index = (difference & -difference).bit_length() - 1
    return {
        "request_index": index,
        "request": decode_request(index),
        "baseline_decision": "allow" if (left >> index) & 1 else "deny",
        "comparison_decision": "allow" if (right >> index) & 1 else "deny",
    }


assert REQUEST_DOMAIN_SIZE == 32768
