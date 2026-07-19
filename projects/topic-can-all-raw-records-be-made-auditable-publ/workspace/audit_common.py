"""Shared deterministic primitives for the audit-provenance experiment."""

from __future__ import annotations

import hashlib
import json
import random
import zipfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "audit-provenance-v1"
STAGE_SOURCE = "source-archive"
STAGE_OUTPUT = "output-archive"
EXPECTED_UNITS = 128 + 128 * 30


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gen_ast(rng: random.Random, depth: int) -> list[Any]:
    if depth == 0 or rng.random() < 0.25:
        return ["var", rng.randrange(8)]
    op = rng.choice(["not", "and", "or", "xor"])
    if op == "not":
        return ["not", gen_ast(rng, depth - 1)]
    return [op, gen_ast(rng, depth - 1), gen_ast(rng, depth - 1)]


class ParseError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_ast(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ParseError("not_array")
    if not value or not isinstance(value[0], str):
        raise ParseError("invalid_operator")
    op = value[0]
    if op == "var":
        if len(value) != 2:
            raise ParseError("invalid_arity")
        index = value[1]
        if type(index) is not int or not 0 <= index <= 7:
            raise ParseError("invalid_variable")
        return ["var", index]
    if op == "not":
        if len(value) != 2:
            raise ParseError("invalid_arity")
        return ["not", validate_ast(value[1])]
    if op in {"and", "or", "xor"}:
        if len(value) != 3:
            raise ParseError("invalid_arity")
        return [op, validate_ast(value[1]), validate_ast(value[2])]
    raise ParseError("invalid_operator")


def parse_ast_bytes(data: bytes) -> list[Any]:
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError("invalid_utf8") from exc
    try:
        value = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise ParseError("invalid_json") from exc
    return validate_ast(value)


def parser_and_fixed_point(data: bytes) -> tuple[dict[str, Any], bool, list[Any] | None]:
    try:
        parsed = parse_ast_bytes(data)
        first = canonical_json_bytes(parsed)
        reparsed = parse_ast_bytes(first)
        second = canonical_json_bytes(reparsed)
    except ParseError as exc:
        return (
            {"success": False, "error_code": exc.code, "canonical_ast_sha256": None},
            False,
            None,
        )
    return (
        {
            "success": True,
            "error_code": None,
            "canonical_ast_sha256": sha256_bytes(first),
        },
        first == second,
        parsed,
    )


def evaluate(ast: list[Any], assignment: int) -> bool:
    op = ast[0]
    if op == "var":
        return bool((assignment >> ast[1]) & 1)
    if op == "not":
        return not evaluate(ast[1], assignment)
    left = evaluate(ast[1], assignment)
    right = evaluate(ast[2], assignment)
    if op == "and":
        return left and right
    if op == "or":
        return left or right
    if op == "xor":
        return left != right
    raise AssertionError(f"validated AST has unknown operator {op!r}")


def semantic_bitset(ast: list[Any]) -> bytes:
    packed = bytearray(32)
    for assignment in range(256):
        if evaluate(ast, assignment):
            packed[assignment // 8] |= 1 << (assignment % 8)
    return bytes(packed)


def baseline_ast(case_index: int) -> list[Any]:
    return gen_ast(random.Random(710000 + case_index), 4)


def mutant_ast(case_index: int, mutant_index: int, baseline: list[Any] | None = None) -> list[Any]:
    if baseline is None:
        baseline = baseline_ast(case_index)
    rng = random.Random(910000 + 30 * case_index + mutant_index)
    perturbation = gen_ast(rng, 2)
    op = ["and", "or", "xor"][mutant_index % 3]
    return [op, baseline, perturbation]


def unit_identifier(record_type: str, case_index: int, mutant_index: int | None = None) -> str:
    if record_type == "baseline":
        return f"case-{case_index:03d}/baseline"
    if record_type == "pair" and mutant_index is not None:
        return f"case-{case_index:03d}/mutant-{mutant_index:02d}"
    raise ValueError("invalid unit coordinates")


def safe_unit_identifier(unit: str) -> str:
    return unit.replace("/", "__")


def deterministic_zip(path: Path, entries: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.comment = b""
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.extra = b""
            info.comment = b""
            archive.writestr(info, entries[name])


def validate_zip_metadata(path: Path, expected_names: list[str]) -> None:
    with zipfile.ZipFile(path, "r") as archive:
        if archive.comment != b"":
            raise ValueError(f"archive comment present: {path}")
        infos = archive.infolist()
        if [info.filename for info in infos] != sorted(expected_names):
            raise ValueError(f"entry order/names invalid: {path}")
        for info in infos:
            if info.date_time != (1980, 1, 1, 0, 0, 0):
                raise ValueError(f"timestamp invalid: {path}:{info.filename}")
            if info.compress_type != zipfile.ZIP_STORED:
                raise ValueError(f"compression invalid: {path}:{info.filename}")
            if info.extra or info.comment:
                raise ValueError(f"extra/comment metadata present: {path}:{info.filename}")
            if (info.external_attr >> 16) & 0o777 != 0o644:
                raise ValueError(f"mode invalid: {path}:{info.filename}")


def context_digest(
    unit: str,
    stage_name: str,
    ordered_parent_digests: list[str],
    payload_digest: str,
    schema_version: str = SCHEMA_VERSION,
) -> str:
    value = {
        "ordered_parent_digests": ordered_parent_digests,
        "payload_digest": payload_digest,
        "schema_version": schema_version,
        "stage_name": stage_name,
        "unit_identifier": unit,
    }
    return sha256_bytes(canonical_json_bytes(value))


def iter_unit_coordinates():
    for case_index in range(128):
        yield "baseline", case_index, None
        for mutant_index in range(30):
            yield "pair", case_index, mutant_index


def write_canonical_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        for value in values:
            handle.write(canonical_json_bytes(value))
