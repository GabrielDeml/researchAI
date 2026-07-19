"""Independent, explicit parser and validator for policy JSON archives."""

from __future__ import annotations

import json


SUBJECTS = ["s0", "s1", "s2", "s3"]
ACTIONS = ["a0", "a1", "a2", "a3"]
RESOURCES = ["r0", "r1", "r2", "r3"]
TIME_SLOTS = [0, 1, 2, 3]
REGIONS = ["g0", "g1", "g2", "g3"]
TOP_LEVEL_KEYS = {"version", "policy"}
POLICY_KEYS = {
    "policy_id",
    "effect",
    "subjects",
    "actions",
    "resources",
    "time_slots",
    "regions",
    "min_clearance",
    "require_mfa",
    "max_amount",
}


class PolicyParseError(ValueError):
    pass


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PolicyParseError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _selector(value: object, universe: list, field: str) -> list:
    if type(value) is not list:
        raise PolicyParseError(f"{field} must be a list")
    member_type = type(universe[0])
    if any(type(item) is not member_type or item not in universe for item in value):
        raise PolicyParseError(f"{field} contains an invalid value")
    if len(value) != len(set(value)):
        raise PolicyParseError(f"{field} contains duplicate members")
    if value != sorted(value):
        raise PolicyParseError(f"{field} must be sorted")
    return list(value)


def _bounded_integer(value: object, field: str) -> int:
    if type(value) is not int or not 0 <= value <= 3:
        raise PolicyParseError(f"{field} must be an integer in 0..3")
    return value


def parse_archive(data: bytes) -> dict:
    """Validate archive bytes and return a complete policy with defaults applied."""
    if type(data) is not bytes:
        raise PolicyParseError("archive must be bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PolicyParseError("archive is not valid UTF-8") from exc
    if not text.endswith("\n") or text[:-1].endswith("\n"):
        raise PolicyParseError("archive must end in exactly one newline")
    try:
        document = json.loads(text[:-1], object_pairs_hook=_object_without_duplicate_keys)
    except PolicyParseError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise PolicyParseError("malformed JSON") from exc
    if type(document) is not dict:
        raise PolicyParseError("top level must be an object")
    if set(document) != TOP_LEVEL_KEYS:
        raise PolicyParseError("top level must contain exactly version and policy")
    if type(document["version"]) is not int or document["version"] != 1:
        raise PolicyParseError("version must be integer 1")
    source = document["policy"]
    if type(source) is not dict:
        raise PolicyParseError("policy must be an object")
    if set(source) - POLICY_KEYS:
        raise PolicyParseError("policy contains an extra key")
    if "policy_id" not in source or type(source["policy_id"]) is not str:
        raise PolicyParseError("policy_id must be present and a string")

    effect = source.get("effect", "deny")
    if type(effect) is not str or effect not in {"allow", "deny"}:
        raise PolicyParseError("effect must be allow or deny")
    require_mfa = source.get("require_mfa", False)
    if type(require_mfa) is not bool:
        raise PolicyParseError("require_mfa must be boolean")

    return {
        "policy_id": source["policy_id"],
        "effect": effect,
        "subjects": _selector(source.get("subjects", SUBJECTS), SUBJECTS, "subjects"),
        "actions": _selector(source.get("actions", ACTIONS), ACTIONS, "actions"),
        "resources": _selector(
            source.get("resources", RESOURCES), RESOURCES, "resources"
        ),
        "time_slots": _selector(
            source.get("time_slots", TIME_SLOTS), TIME_SLOTS, "time_slots"
        ),
        "regions": _selector(source.get("regions", REGIONS), REGIONS, "regions"),
        "min_clearance": _bounded_integer(
            source.get("min_clearance", 0), "min_clearance"
        ),
        "require_mfa": require_mfa,
        "max_amount": _bounded_integer(source.get("max_amount", 3), "max_amount"),
    }
