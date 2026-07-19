"""Baseline and 30 deterministic lossy policy canonicalizers."""

from __future__ import annotations

import json
from collections.abc import Callable


SELECTOR_FIELDS = ("subjects", "actions", "resources", "time_slots", "regions")

MUTATION_CATALOG = {
    "M01": "delete subjects",
    "M02": "delete actions",
    "M03": "delete resources",
    "M04": "delete time_slots",
    "M05": "delete regions",
    "M06": "delete effect",
    "M07": "delete min_clearance",
    "M08": "delete require_mfa",
    "M09": "delete max_amount",
    "M10": "replace subjects by its lexicographically first member if nonempty",
    "M11": "similarly truncate actions",
    "M12": "similarly truncate resources",
    "M13": "replace time_slots by its minimum member if nonempty",
    "M14": "similarly truncate regions",
    "M15": "replace min_clearance v by 2*floor(v/2)",
    "M16": "replace min_clearance by 0",
    "M17": "replace max_amount v by 1 when v is 0 or 1 and by 3 when v is 2 or 3",
    "M18": "replace max_amount by 3",
    "M19": "replace require_mfa by false",
    "M20": "replace effect by \"deny\"",
    "M21": "map subjects s1->s0 and s3->s2, leaving s0 and s2 fixed, then deduplicate",
    "M22": "apply the analogous a1->a0 and a3->a2 action map",
    "M23": "apply the analogous r1->r0 and r3->r2 resource map",
    "M24": "map time slots 1->0 and 3->2, leaving 0 and 2 fixed",
    "M25": "apply the analogous g1->g0 and g3->g2 region map",
    "M26": "intersect subjects with {\"s0\",\"s1\"}",
    "M27": "intersect actions with {\"a0\",\"a1\"}",
    "M28": "intersect resources with {\"r0\",\"r1\"}",
    "M29": "intersect time_slots with {0,2}",
    "M30": "intersect regions with {\"g0\",\"g1\"}",
}


def canonical_json_bytes(obj: object) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
        + b"\n"
    )


def _load_and_normalize(data: bytes) -> dict:
    document = json.loads(data.decode("utf-8"))
    policy = document["policy"]
    for field in SELECTOR_FIELDS:
        if field in policy:
            policy[field] = sorted(set(policy[field]))
    return document


def canonicalize(data: bytes) -> bytes:
    """C0: normalize only fields already present, then canonically serialize."""
    return canonical_json_bytes(_load_and_normalize(data))


def _delete(field: str) -> Callable[[dict], None]:
    return lambda policy: policy.pop(field, None)


def _truncate(field: str) -> Callable[[dict], None]:
    def transform(policy: dict) -> None:
        if field in policy and policy[field]:
            policy[field] = [min(policy[field])]

    return transform


def _map_selector(field: str, mapping: dict) -> Callable[[dict], None]:
    def transform(policy: dict) -> None:
        if field in policy:
            policy[field] = sorted({mapping.get(value, value) for value in policy[field]})

    return transform


def _intersect(field: str, retained: set) -> Callable[[dict], None]:
    def transform(policy: dict) -> None:
        if field in policy:
            policy[field] = sorted(set(policy[field]) & retained)

    return transform


def _set(field: str, value: object) -> Callable[[dict], None]:
    def transform(policy: dict) -> None:
        if field in policy:
            policy[field] = value

    return transform


TRANSFORMS: dict[str, Callable[[dict], None]] = {
    "M01": _delete("subjects"),
    "M02": _delete("actions"),
    "M03": _delete("resources"),
    "M04": _delete("time_slots"),
    "M05": _delete("regions"),
    "M06": _delete("effect"),
    "M07": _delete("min_clearance"),
    "M08": _delete("require_mfa"),
    "M09": _delete("max_amount"),
    "M10": _truncate("subjects"),
    "M11": _truncate("actions"),
    "M12": _truncate("resources"),
    "M13": _truncate("time_slots"),
    "M14": _truncate("regions"),
    "M15": lambda p: p.__setitem__("min_clearance", 2 * (p["min_clearance"] // 2))
    if "min_clearance" in p
    else None,
    "M16": _set("min_clearance", 0),
    "M17": lambda p: p.__setitem__("max_amount", 1 if p["max_amount"] <= 1 else 3)
    if "max_amount" in p
    else None,
    "M18": _set("max_amount", 3),
    "M19": _set("require_mfa", False),
    "M20": _set("effect", "deny"),
    "M21": _map_selector("subjects", {"s1": "s0", "s3": "s2"}),
    "M22": _map_selector("actions", {"a1": "a0", "a3": "a2"}),
    "M23": _map_selector("resources", {"r1": "r0", "r3": "r2"}),
    "M24": _map_selector("time_slots", {1: 0, 3: 2}),
    "M25": _map_selector("regions", {"g1": "g0", "g3": "g2"}),
    "M26": _intersect("subjects", {"s0", "s1"}),
    "M27": _intersect("actions", {"a0", "a1"}),
    "M28": _intersect("resources", {"r0", "r1"}),
    "M29": _intersect("time_slots", {0, 2}),
    "M30": _intersect("regions", {"g0", "g1"}),
}


def canonicalize_mutant(data: bytes, mutant_id: str) -> bytes:
    """Parse, normalize, mutate, and serialize one archive invocation."""
    if mutant_id not in TRANSFORMS:
        raise ValueError(f"unknown mutant: {mutant_id}")
    document = _load_and_normalize(data)
    policy = document["policy"]
    TRANSFORMS[mutant_id](policy)
    for field in SELECTOR_FIELDS:
        if field in policy:
            policy[field] = sorted(set(policy[field]))
    return canonical_json_bytes(document)


assert list(MUTATION_CATALOG) == [f"M{i:02d}" for i in range(1, 31)]
assert set(TRANSFORMS) == set(MUTATION_CATALOG)
