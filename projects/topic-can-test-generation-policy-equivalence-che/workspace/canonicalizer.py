"""Reference and deliberately lossy policy-archive canonicalizers."""

from __future__ import annotations

import copy
import io
import json
import zipfile
from pathlib import PurePosixPath


MAX_POLICY_SIZE = 1024 * 1024
PRINCIPALS = ("p0", "p1", "p2", "p3")
ACTIONS = ("a0", "a1", "a2", "a3")
RESOURCES = ("r0", "r1", "r2", "r3")
HOURS = (0, 1, 2, 3)
ZONES = ("internal", "external")
DOMAINS = {
    "principals": PRINCIPALS,
    "actions": ACTIONS,
    "resources": RESOURCES,
    "hours": HOURS,
    "zones": ZONES,
}
TOP_KEYS = {"default_effect", "rules"}
RULE_KEYS = {
    "id",
    "effect",
    "principals",
    "actions",
    "resources",
    "mfa",
    "hours",
    "zones",
    "priority",
}

MUTANT_IDS = [
    *(f"D{i:02d}" for i in range(1, 10)),
    *(f"F{i:02d}" for i in range(1, 8)),
    *(f"T{i:02d}" for i in range(1, 9)),
    *(f"M{i:02d}" for i in range(1, 7)),
]
MUTANT_SEEDS = {mutant_id: 730001 + i for i, mutant_id in enumerate(MUTANT_IDS)}


class CanonicalizationError(ValueError):
    pass


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalizationError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _selector(value, domain: tuple, field: str) -> list:
    if not isinstance(value, list) or not value:
        raise CanonicalizationError(f"{field} must be a nonempty array")
    if any(item not in domain or type(item) is not type(domain[0]) for item in value):
        raise CanonicalizationError(f"invalid {field} value")
    if len(value) != len(set(value)):
        raise CanonicalizationError(f"duplicate {field} value")
    return sorted(value, key=domain.index)


def _parse_archive(data: bytes) -> dict:
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            infos = archive.infolist()
            names = [entry.filename for entry in infos]
            if len(names) != len(set(names)):
                raise CanonicalizationError("duplicate entry name")
            for entry in infos:
                path = PurePosixPath(entry.filename)
                if (
                    entry.is_dir()
                    or entry.filename.startswith("/")
                    or ".." in path.parts
                    or "." in path.parts
                    or entry.flag_bits & 1
                    or entry.compress_type != zipfile.ZIP_STORED
                ):
                    raise CanonicalizationError("invalid ZIP entry")
            if names != ["policy.json"] or infos[0].file_size > MAX_POLICY_SIZE:
                raise CanonicalizationError("archive must contain one small policy.json")
            payload = archive.read(infos[0])
            if len(payload) > MAX_POLICY_SIZE:
                raise CanonicalizationError("policy.json exceeds 1 MiB")
    except CanonicalizationError:
        raise
    except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError) as exc:
        raise CanonicalizationError(f"invalid ZIP: {exc}") from exc
    try:
        document = json.loads(
            payload.decode("utf-8", errors="strict"), object_pairs_hook=_unique_object
        )
    except CanonicalizationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalizationError(f"invalid JSON: {exc}") from exc
    if not isinstance(document, dict) or set(document) - TOP_KEYS:
        raise CanonicalizationError("invalid policy object or unknown key")
    default_effect = document.get("default_effect", "deny")
    rules = document.get("rules", [])
    if type(default_effect) is not str or default_effect not in ("allow", "deny"):
        raise CanonicalizationError("invalid default_effect")
    if not isinstance(rules, list):
        raise CanonicalizationError("rules must be an array")
    normalized = []
    ids = set()
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) - RULE_KEYS:
            raise CanonicalizationError("invalid rule object or unknown key")
        rule_id = rule.get("id")
        if type(rule_id) is not str or rule_id in ids:
            raise CanonicalizationError("missing, non-string, or duplicate rule id")
        ids.add(rule_id)
        effect = rule.get("effect", "deny")
        mfa = rule.get("mfa", "any")
        priority = rule.get("priority", 0)
        if type(effect) is not str or effect not in ("allow", "deny"):
            raise CanonicalizationError("invalid effect")
        if type(mfa) is not str or mfa not in ("any", "required", "forbidden"):
            raise CanonicalizationError("invalid mfa")
        if type(priority) is not int or not 0 <= priority <= 3:
            raise CanonicalizationError("invalid priority")
        item = {"id": rule_id, "effect": effect}
        for field, domain in DOMAINS.items():
            item[field] = _selector(rule.get(field, list(domain)), domain, field)
        item["mfa"] = mfa
        item["priority"] = priority
        # Dict insertion order is irrelevant because serialization sorts keys.
        normalized.append(item)
    return {"default_effect": default_effect, "rules": normalized}


def _write_archive(policy: dict) -> bytes:
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


def _explicit(policy: dict) -> dict:
    return {
        "default_effect": policy["default_effect"],
        "rules": [
            {
                "id": rule["id"],
                "effect": rule["effect"],
                "principals": list(rule["principals"]),
                "actions": list(rule["actions"]),
                "resources": list(rule["resources"]),
                "mfa": rule["mfa"],
                "hours": list(rule["hours"]),
                "zones": list(rule["zones"]),
                "priority": rule["priority"],
            }
            for rule in policy["rules"]
        ],
    }


def _mutate(policy: dict, canonicalizer_id: str) -> dict:
    output = _explicit(copy.deepcopy(policy))
    if canonicalizer_id == "D01":
        output.pop("default_effect")
    elif canonicalizer_id == "D02":
        for rule in output["rules"]:
            rule.pop("effect")
    elif canonicalizer_id in {"D03", "D04", "D05", "D06", "D07"}:
        field = {
            "D03": "principals",
            "D04": "actions",
            "D05": "resources",
            "D06": "hours",
            "D07": "zones",
        }[canonicalizer_id]
        for rule in output["rules"]:
            rule.pop(field)
    elif canonicalizer_id == "D08":
        for rule in output["rules"]:
            rule.pop("mfa")
    elif canonicalizer_id == "D09":
        for rule in output["rules"]:
            rule.pop("priority")
    elif canonicalizer_id == "F01":
        output["default_effect"] = "allow"
    elif canonicalizer_id == "F02":
        for rule in output["rules"]:
            rule["effect"] = "allow"
    elif canonicalizer_id in {"F03", "F04", "F05"}:
        field, singleton = {
            "F03": ("principals", ["p0"]),
            "F04": ("actions", ["a0"]),
            "F05": ("resources", ["r0"]),
        }[canonicalizer_id]
        for rule in output["rules"]:
            rule[field] = singleton.copy()
    elif canonicalizer_id == "F06":
        for rule in output["rules"]:
            rule["mfa"] = "required"
    elif canonicalizer_id == "F07":
        for rule in output["rules"]:
            rule["priority"] = 0
    elif canonicalizer_id == "T01":
        output["rules"] = output["rules"][:1]
    elif canonicalizer_id == "T02":
        output["rules"] = output["rules"][:2]
    elif canonicalizer_id in {"T03", "T04", "T05", "T06", "T07"}:
        field = {
            "T03": "principals",
            "T04": "actions",
            "T05": "resources",
            "T06": "hours",
            "T07": "zones",
        }[canonicalizer_id]
        for rule in output["rules"]:
            rule[field] = rule[field][:1]
    elif canonicalizer_id == "T08":
        for rule in output["rules"]:
            rule["priority"] = min(rule["priority"], 1)
    elif canonicalizer_id == "M01":
        merged = []
        for effect in ("deny", "allow"):
            members = [rule for rule in output["rules"] if rule["effect"] == effect]
            if not members:
                continue
            rule = {
                "id": f"merged_{effect}",
                "effect": effect,
                "mfa": (
                    members[0]["mfa"]
                    if all(member["mfa"] == members[0]["mfa"] for member in members)
                    else "any"
                ),
                "priority": max(member["priority"] for member in members),
            }
            for field, domain in DOMAINS.items():
                values = {value for member in members for value in member[field]}
                rule[field] = [value for value in domain if value in values]
            merged.append(rule)
        output["rules"] = merged
    elif canonicalizer_id in {"M02", "M03", "M04", "M05", "M06"}:
        field = {
            "M02": "principals",
            "M03": "actions",
            "M04": "resources",
            "M05": "hours",
            "M06": "zones",
        }[canonicalizer_id]
        for rule in output["rules"]:
            if len(rule[field]) >= 2:
                rule[field] = list(DOMAINS[field])
    else:
        raise KeyError(f"unknown canonicalizer: {canonicalizer_id}")
    return output


def canonicalize(data: bytes, canonicalizer_id: str = "C0") -> bytes:
    normalized = _parse_archive(data)
    if canonicalizer_id == "C0":
        output = _explicit(normalized)
    elif canonicalizer_id in MUTANT_IDS:
        output = _mutate(normalized, canonicalizer_id)
    else:
        raise KeyError(f"unknown canonicalizer: {canonicalizer_id}")
    return _write_archive(output)

