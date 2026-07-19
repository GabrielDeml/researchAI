#!/usr/bin/env python3
"""Deterministic refs/replace experiment using authenticated loose Git objects.

This program creates twelve SHA-1 repositories, authenticates an original commit
by parsing loose objects directly, installs an adversarial replacement commit,
and contrasts the raw verifier with ordinary replacement-aware Git traversal.
"""

from __future__ import annotations

import hashlib
import json
import locale
import os
import random
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path
from typing import Any, Iterable


SEED = 20250308
CASE_COUNT = 12
TIME_LIMIT_SECONDS = 1800.0
ROOT = Path(__file__).resolve().parent
REPOS_DIR = ROOT / "repos"
RESULTS_DIR = ROOT / "results"
FIXTURES_DIR = RESULTS_DIR / "fixtures"
FIGURES_DIR = ROOT / "figures"
EMPTY_HOME = ROOT / ".git-empty-home"
CACHE_DIR = ROOT / ".experiment-cache"

LFS_VERSION = b"version https://git-lfs.github.com/spec/v1"
ORIGINAL_LFS = (
    LFS_VERSION
    + b"\n"
    + b"oid sha256:"
    + b"a" * 64
    + b"\nsize 12345\n"
)
GITLINK_1 = "1" * 40
GITLINK_2 = "2" * 40
GITLINK_3 = "3" * 40
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_BYTES_RE = re.compile(br"^[0-9a-f]{64}$")

START_TIME = time.monotonic()
COMMAND_FAILURE_COUNT = 0
PARSING_FAILURE_COUNT = 0
OBJECT_INTEGRITY_FAILURE_COUNT = 0
OBJECT_VALIDATION_COUNT = 0


class ExperimentError(RuntimeError):
    """A setup, fixture, parsing, integrity, or command error."""


class ObjectIntegrityError(ExperimentError):
    """A loose object failed its size or SHA-1 validation."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def write_json(path: Path, value: Any, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        data = canonical_json(value) + b"\n"
        path.write_bytes(data)
    else:
        path.write_text(
            json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def remaining_time() -> float:
    return TIME_LIMIT_SECONDS - (time.monotonic() - START_TIME)


def base_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "LC_ALL": "C",
            "TZ": "UTC",
            "PYTHONHASHSEED": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": str(EMPTY_HOME),
            "XDG_CONFIG_HOME": str(EMPTY_HOME / "xdg"),
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    # Prevent ambient repository-discovery and object-store configuration.
    for name in list(env):
        if name.startswith("GIT_") and name not in {
            "GIT_CONFIG_NOSYSTEM",
            "GIT_TERMINAL_PROMPT",
        }:
            del env[name]
    return env


def run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    input_bytes: bytes | None = None,
    env_overrides: dict[str, str] | None = None,
) -> bytes:
    """Invoke Git with an argument array and the isolated experiment environment."""
    global COMMAND_FAILURE_COUNT
    env = base_environment()
    if env_overrides:
        env.update(env_overrides)
    timeout = min(120.0, remaining_time())
    if timeout <= 0:
        COMMAND_FAILURE_COUNT += 1
        raise ExperimentError("experiment exceeded the 1800-second limit")
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=env,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        COMMAND_FAILURE_COUNT += 1
        stderr = ""
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            stderr = exc.stderr.decode("utf-8", "replace").strip()
        raise ExperimentError(
            f"git command failed: {args!r}; cwd={str(cwd)!r}; stderr={stderr!r}"
        ) from exc
    return completed.stdout


def preflight() -> tuple[str, str, str]:
    if sys.version_info < (3, 10):
        raise ExperimentError(f"Python 3.10+ required, found {sys.version}")

    git_text = run_git(["--version"]).decode("ascii", "strict").strip()
    match = re.fullmatch(r"git version (\d+)\.(\d+)(?:\.(\d+))?.*", git_text)
    if not match:
        raise ExperimentError(f"could not parse Git version: {git_text!r}")
    git_tuple = tuple(int(part or 0) for part in match.groups())
    if git_tuple < (2, 25, 0):
        raise ExperimentError(f"Git 2.25+ required, found {git_text}")

    import matplotlib

    if matplotlib.__version__ != "3.8.4":
        raise ExperimentError(
            f"matplotlib 3.8.4 required, found {matplotlib.__version__}"
        )

    # Explicitly exercise SHA-1 initialization before creating any case fixture.
    with tempfile.TemporaryDirectory(prefix="sha1-preflight-", dir=ROOT) as temp_dir:
        temp_path = Path(temp_dir)
        run_git(["init", "--object-format=sha1", "--quiet", str(temp_path)])
        object_format = run_git(
            ["rev-parse", "--show-object-format"], cwd=temp_path
        ).decode("ascii", "strict").strip()
        if object_format != "sha1":
            raise ExperimentError(f"SHA-1 repositories unsupported: {object_format!r}")

    return sys.version.split()[0], git_text, matplotlib.__version__


def hash_blob(repo: Path, data: bytes) -> str:
    oid = run_git(["hash-object", "-w", "--stdin"], cwd=repo, input_bytes=data)
    text = oid.decode("ascii", "strict").strip().lower()
    if not HEX40_RE.fullmatch(text):
        raise ExperimentError(f"invalid hash-object output: {text!r}")
    return text


def git_blob_oid(data: bytes) -> str:
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def build_tree(repo: Path, leaves: dict[bytes, tuple[str, str]]) -> str:
    """Build a hierarchy from path -> (six-digit mode, object ID)."""

    def recurse(entries: dict[bytes, tuple[str, str]]) -> str:
        direct: dict[bytes, tuple[str, str, str]] = {}
        children: dict[bytes, dict[bytes, tuple[str, str]]] = {}
        for path, (mode, oid) in entries.items():
            first, separator, rest = path.partition(b"/")
            if not first or first in {b".", b".."}:
                raise ExperimentError(f"invalid tree path: {path!r}")
            if separator:
                children.setdefault(first, {})[rest] = (mode, oid)
            else:
                kind = "commit" if mode == "160000" else "blob"
                direct[first] = (mode, kind, oid)

        overlap = set(direct).intersection(children)
        if overlap:
            raise ExperimentError(f"path is both leaf and directory: {overlap!r}")
        for name, child_entries in children.items():
            direct[name] = ("040000", "tree", recurse(child_entries))

        payload = bytearray()
        for name in sorted(direct):
            mode, kind, oid = direct[name]
            payload.extend(f"{mode} {kind} {oid}\t".encode("ascii"))
            payload.extend(name)
            payload.append(0)
        output = run_git(
            ["mktree", "--missing", "-z"], cwd=repo, input_bytes=bytes(payload)
        )
        tree_oid = output.decode("ascii", "strict").strip().lower()
        if not HEX40_RE.fullmatch(tree_oid):
            raise ExperimentError(f"invalid mktree output: {tree_oid!r}")
        return tree_oid

    return recurse(leaves)


def commit_tree(repo: Path, tree_oid: str, message: bytes, timestamp: int) -> str:
    date = f"{timestamp} +0000"
    env = {
        "GIT_AUTHOR_NAME": "Verifier Experiment",
        "GIT_AUTHOR_EMAIL": "verifier@example.invalid",
        "GIT_COMMITTER_NAME": "Verifier Experiment",
        "GIT_COMMITTER_EMAIL": "verifier@example.invalid",
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_DATE": date,
    }
    output = run_git(["commit-tree", tree_oid], cwd=repo, input_bytes=message, env_overrides=env)
    oid = output.decode("ascii", "strict").strip().lower()
    if not HEX40_RE.fullmatch(oid):
        raise ExperimentError(f"invalid commit-tree output: {oid!r}")
    return oid


def original_leaves(repo: Path, case_number: int) -> dict[bytes, tuple[str, str]]:
    contents = {
        b"README.md": ("100644", f"original README case-{case_number:02d}\n".encode()),
        b"visible/case.txt": ("100644", f"visible original case-{case_number:02d}\n".encode()),
        b"bin/run.sh": ("100755", b"#!/bin/sh\nprintf 'original executable\\n'\n"),
        b"links/readme-link": ("120000", b"../README.md"),
        b".gitattributes": (
            "100644",
            b"assets/model.bin filter=lfs diff=lfs merge=lfs -text\n",
        ),
        b"assets/model.bin": ("100644", ORIGINAL_LFS),
        b"nested/data.txt": (
            "100644",
            f"nested original case-{case_number:02d}\n".encode(),
        ),
    }
    leaves = {
        path: (mode, hash_blob(repo, data)) for path, (mode, data) in contents.items()
    }
    leaves[b"vendor/dependency"] = ("160000", GITLINK_1)
    return leaves


def replacement_leaves(
    repo: Path, case_number: int, original: dict[bytes, tuple[str, str]]
) -> dict[bytes, tuple[str, str]]:
    leaves = dict(original)
    if case_number == 0:
        leaves[b"README.md"] = (
            "100644",
            hash_blob(repo, b"adversarial README replacement\n"),
        )
    elif case_number == 1:
        leaves[b"nested/renamed.txt"] = leaves.pop(b"nested/data.txt")
    elif case_number == 2:
        _, oid = leaves[b"bin/run.sh"]
        leaves[b"bin/run.sh"] = ("100644", oid)
    elif case_number == 3:
        leaves[b"links/readme-link"] = (
            "120000",
            hash_blob(repo, b"../nested/data.txt"),
        )
    elif case_number == 4:
        _, oid = leaves[b"links/readme-link"]
        leaves[b"links/readme-link"] = ("100644", oid)
    elif case_number == 5:
        leaves[b"bin/run.sh"] = (
            "100755",
            hash_blob(repo, b"#!/bin/sh\nprintf 'adversarial executable\\n'\n"),
        )
    elif case_number == 6:
        leaves[b"vendor/dependency"] = ("160000", GITLINK_2)
    elif case_number == 7:
        replacement_pointer = (
            LFS_VERSION + b"\noid sha256:" + b"b" * 64 + b"\nsize 54321\n"
        )
        leaves[b"assets/model.bin"] = (
            "100644",
            hash_blob(repo, replacement_pointer),
        )
    elif case_number == 8:
        leaves[b".gitattributes"] = (
            "100644",
            hash_blob(repo, b"assets/model.bin -filter -diff -merge text\n"),
        )
    elif case_number == 9:
        del leaves[b"nested/data.txt"]
    elif case_number == 10:
        leaves[b"adversarial/new.txt"] = (
            "100644",
            hash_blob(repo, b"adversarial addition\n"),
        )
    elif case_number == 11:
        del leaves[b"README.md"]
        leaves[b"visible/case.txt"] = (
            "100644",
            hash_blob(repo, b"adversarial visible content\n"),
        )
        _, executable_oid = leaves[b"bin/run.sh"]
        leaves[b"bin/run.sh"] = ("100644", executable_oid)
        leaves[b"vendor/dependency"] = ("160000", GITLINK_3)
    else:
        raise ExperimentError(f"unexpected case number: {case_number}")
    return leaves


def parse_lfs_pointer(data: bytes) -> tuple[str | None, int | None]:
    # splitlines() accepts a missing terminal newline, so require the exact full shape.
    match = re.fullmatch(
        br"version https://git-lfs\.github\.com/spec/v1\n"
        br"oid sha256:([0-9a-f]{64})\n"
        br"size ([0-9]+)\n",
        data,
    )
    if not match:
        return None, None
    oid_bytes, size_bytes = match.groups()
    if not HEX64_BYTES_RE.fullmatch(oid_bytes):
        return None, None
    return oid_bytes.decode("ascii"), int(size_bytes)


def make_record(path: bytes, mode: str, oid: str, blob_data: bytes | None) -> dict[str, Any]:
    mode = f"{int(mode, 8):06o}"
    if mode not in {"100644", "100755", "120000", "160000"}:
        raise ExperimentError(f"unsupported leaf mode {mode!r} for path {path!r}")
    kind = "gitlink" if mode == "160000" else "symlink" if mode == "120000" else "blob"
    record: dict[str, Any] = {
        "kind": kind,
        "mode": mode,
        "object_id": oid.lower(),
        "path": path.hex(),
    }
    if mode == "100644":
        if blob_data is None:
            raise ExperimentError(f"missing blob data for regular file {path!r}")
        lfs_oid, lfs_size = parse_lfs_pointer(blob_data)
        record["lfs_sha256"] = lfs_oid
        record["lfs_size"] = lfs_size
    return record


def inventory_bytes(records: Iterable[dict[str, Any]]) -> bytes:
    ordered = sorted(records, key=lambda record: bytes.fromhex(record["path"]))
    return canonical_json(ordered)


def inventory_fingerprint(serialized: bytes) -> str:
    return hashlib.sha256(serialized).hexdigest()


class LooseObjectReader:
    """Replacement-disabled authenticated reader for only this repo's loose objects."""

    def __init__(self, repo: Path):
        self.objects_dir = repo / ".git" / "objects"
        self.validated = 0

    def read(self, oid: str, expected_type: str | None = None) -> tuple[str, bytes]:
        global OBJECT_INTEGRITY_FAILURE_COUNT, OBJECT_VALIDATION_COUNT
        oid = oid.lower()
        if not HEX40_RE.fullmatch(oid):
            raise ExperimentError(f"invalid requested object ID: {oid!r}")
        path = self.objects_dir / oid[:2] / oid[2:]
        try:
            compressed = path.read_bytes()
            raw = zlib.decompress(compressed)
        except (OSError, zlib.error) as exc:
            raise ExperimentError(f"cannot read loose object {oid} at {path}") from exc
        nul = raw.find(b"\0")
        if nul < 0:
            raise ExperimentError(f"object {oid} has no header terminator")
        header, payload = raw[:nul], raw[nul + 1 :]
        try:
            object_type_bytes, size_bytes = header.split(b" ", 1)
            object_type = object_type_bytes.decode("ascii", "strict")
            if not size_bytes or not size_bytes.isdigit():
                raise ValueError("non-decimal size")
            declared_size = int(size_bytes)
        except (ValueError, UnicodeError) as exc:
            raise ExperimentError(f"object {oid} has invalid header {header!r}") from exc
        if declared_size != len(payload):
            OBJECT_INTEGRITY_FAILURE_COUNT += 1
            raise ObjectIntegrityError(
                f"object {oid} size mismatch: declared {declared_size}, actual {len(payload)}"
            )
        recomputed = hashlib.sha1(header + b"\0" + payload).hexdigest()
        if recomputed != oid:
            OBJECT_INTEGRITY_FAILURE_COUNT += 1
            raise ObjectIntegrityError(
                f"object {oid} hash mismatch: recomputed {recomputed}"
            )
        if expected_type is not None and object_type != expected_type:
            raise ExperimentError(
                f"object {oid} type mismatch: expected {expected_type}, got {object_type}"
            )
        self.validated += 1
        OBJECT_VALIDATION_COUNT += 1
        return object_type, payload


def parse_commit_tree(payload: bytes) -> str:
    global PARSING_FAILURE_COUNT
    header_block, separator, _message = payload.partition(b"\n\n")
    if not separator:
        PARSING_FAILURE_COUNT += 1
        raise ExperimentError("commit has no header/message separator")
    tree_values = [line[5:] for line in header_block.split(b"\n") if line.startswith(b"tree ")]
    if len(tree_values) != 1:
        PARSING_FAILURE_COUNT += 1
        raise ExperimentError(f"commit has {len(tree_values)} tree headers")
    try:
        tree_oid = tree_values[0].decode("ascii", "strict").lower()
    except UnicodeError as exc:
        PARSING_FAILURE_COUNT += 1
        raise ExperimentError("commit tree ID is not ASCII") from exc
    if not HEX40_RE.fullmatch(tree_oid):
        PARSING_FAILURE_COUNT += 1
        raise ExperimentError(f"commit has invalid tree ID: {tree_oid!r}")
    return tree_oid


def parse_binary_tree(payload: bytes) -> list[tuple[str, bytes, str]]:
    global PARSING_FAILURE_COUNT
    entries: list[tuple[str, bytes, str]] = []
    position = 0
    try:
        while position < len(payload):
            space = payload.index(b" ", position)
            nul = payload.index(b"\0", space + 1)
            mode_bytes = payload[position:space]
            name = payload[space + 1 : nul]
            oid_start = nul + 1
            oid_end = oid_start + 20
            if oid_end > len(payload):
                raise ValueError("truncated object ID")
            if not mode_bytes or any(byte not in b"01234567" for byte in mode_bytes):
                raise ValueError("invalid octal mode")
            if not name or b"/" in name:
                raise ValueError("invalid tree entry name")
            mode = f"{int(mode_bytes, 8):06o}"
            oid = payload[oid_start:oid_end].hex()
            entries.append((mode, name, oid))
            position = oid_end
    except (ValueError, IndexError) as exc:
        PARSING_FAILURE_COUNT += 1
        raise ExperimentError(f"invalid binary tree at byte {position}: {exc}") from exc
    return entries


def raw_inventory(repo: Path, commit_oid: str) -> tuple[str, bytes, int]:
    reader = LooseObjectReader(repo)
    _commit_type, commit_payload = reader.read(commit_oid, "commit")
    tree_oid = parse_commit_tree(commit_payload)
    records: list[dict[str, Any]] = []

    def walk(current_tree_oid: str, prefix: bytes) -> None:
        _tree_type, tree_payload = reader.read(current_tree_oid, "tree")
        for mode, name, oid in parse_binary_tree(tree_payload):
            path = prefix + name
            if mode == "040000":
                walk(oid, path + b"/")
            elif mode in {"100644", "100755", "120000"}:
                _blob_type, blob_payload = reader.read(oid, "blob")
                records.append(make_record(path, mode, oid, blob_payload))
            elif mode == "160000":
                # A gitlink names a commit in another repository. Never open it here.
                records.append(make_record(path, mode, oid, None))
            else:
                raise ExperimentError(f"unsupported tree mode {mode!r} at {path!r}")

    walk(tree_oid, b"")
    return tree_oid, inventory_bytes(records), reader.validated


def raw_blob(repo: Path, oid: str) -> bytes:
    reader = LooseObjectReader(repo)
    return reader.read(oid, "blob")[1]


def ordinary_inventory(
    repo: Path, commit_oid: str, *, disable_replacements: bool
) -> bytes:
    env = {"GIT_NO_REPLACE_OBJECTS": "1"} if disable_replacements else None
    output = run_git(
        ["ls-tree", "-r", "-z", "--full-tree", commit_oid],
        cwd=repo,
        env_overrides=env,
    )
    records: list[dict[str, Any]] = []
    for item in output.split(b"\0"):
        if not item:
            continue
        try:
            metadata, path = item.split(b"\t", 1)
            mode_bytes, object_type, oid_bytes = metadata.split(b" ")
            mode = mode_bytes.decode("ascii", "strict")
            oid = oid_bytes.decode("ascii", "strict").lower()
        except (ValueError, UnicodeError) as exc:
            raise ExperimentError(f"invalid ls-tree record: {item!r}") from exc
        if not HEX40_RE.fullmatch(oid):
            raise ExperimentError(f"invalid ls-tree object ID: {oid!r}")
        normalized_mode = f"{int(mode, 8):06o}"
        if normalized_mode == "160000":
            if object_type != b"commit":
                raise ExperimentError(f"gitlink is not commit type: {item!r}")
            blob_data = None
        else:
            if object_type != b"blob":
                raise ExperimentError(f"leaf is not blob type: {item!r}")
            blob_data = run_git(
                ["cat-file", "blob", oid], cwd=repo, env_overrides=env
            )
        records.append(make_record(path, normalized_mode, oid, blob_data))
    return inventory_bytes(records)


def index_inventory(repo: Path) -> bytes:
    output = run_git(["ls-files", "--stage", "-z"], cwd=repo)
    records: list[dict[str, Any]] = []
    for item in output.split(b"\0"):
        if not item:
            continue
        try:
            metadata, path = item.split(b"\t", 1)
            mode_bytes, oid_bytes, stage_bytes = metadata.split(b" ")
            if stage_bytes != b"0":
                continue
            mode = mode_bytes.decode("ascii", "strict")
            oid = oid_bytes.decode("ascii", "strict").lower()
        except (ValueError, UnicodeError) as exc:
            raise ExperimentError(f"invalid ls-files --stage record: {item!r}") from exc
        normalized_mode = f"{int(mode, 8):06o}"
        data = None if normalized_mode == "160000" else raw_blob(repo, oid)
        records.append(make_record(path, normalized_mode, oid, data))
    return inventory_bytes(records)


def working_tree_inventory(repo: Path) -> bytes:
    records: list[dict[str, Any]] = []

    def scan(directory: Path, prefix: bytes) -> None:
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda entry: os.fsencode(entry.name))
        for entry in entries:
            name = os.fsencode(entry.name)
            if not prefix and name == b".git":
                continue
            relative = prefix + name
            entry_path = Path(entry.path)
            if entry.is_symlink():
                target = os.readlink(os.fsencode(entry.path))
                if isinstance(target, str):
                    target = os.fsencode(target)
                records.append(make_record(relative, "120000", git_blob_oid(target), target))
            elif entry.is_dir(follow_symlinks=False):
                scan(entry_path, relative + b"/")
            elif entry.is_file(follow_symlinks=False):
                data = entry_path.read_bytes()
                file_stat = entry.stat(follow_symlinks=False)
                mode = "100755" if file_stat.st_mode & stat.S_IXUSR else "100644"
                records.append(make_record(relative, mode, git_blob_oid(data), data))

    scan(repo, b"")
    return inventory_bytes(records)


def sparse_projection(repo: Path) -> set[bytes]:
    output = run_git(["ls-files", "-v", "-z"], cwd=repo)
    projected: set[bytes] = set()
    skip_count = 0
    for item in output.split(b"\0"):
        if not item:
            continue
        if len(item) < 3 or item[1:2] != b" ":
            raise ExperimentError(f"invalid ls-files -v record: {item!r}")
        tag, path = item[:1], item[2:]
        if tag.upper() == b"S":
            skip_count += 1
        else:
            projected.add(path)
    if b"visible/case.txt" not in projected:
        raise ExperimentError("visible/case.txt was not in the sparse projection")
    if skip_count < 1:
        raise ExperimentError("sparse checkout had no skip-worktree paths")
    return projected


def path_set(serialized_inventory: bytes) -> set[bytes]:
    records = json.loads(serialized_inventory)
    return {bytes.fromhex(record["path"]) for record in records}


def assert_expected_mutation(
    case_number: int, original_inventory: bytes, replacement_inventory: bytes
) -> None:
    """Independently require that no inventory records beyond the case mutation changed."""
    original_records = {
        bytes.fromhex(record["path"]): record for record in json.loads(original_inventory)
    }
    replacement_records = {
        bytes.fromhex(record["path"]): record for record in json.loads(replacement_inventory)
    }
    changed_paths = {
        path
        for path in set(original_records).union(replacement_records)
        if original_records.get(path) != replacement_records.get(path)
    }
    expected = {
        0: {b"README.md"},
        1: {b"nested/data.txt", b"nested/renamed.txt"},
        2: {b"bin/run.sh"},
        3: {b"links/readme-link"},
        4: {b"links/readme-link"},
        5: {b"bin/run.sh"},
        6: {b"vendor/dependency"},
        7: {b"assets/model.bin"},
        8: {b".gitattributes"},
        9: {b"nested/data.txt"},
        10: {b"adversarial/new.txt"},
        11: {b"README.md", b"visible/case.txt", b"bin/run.sh", b"vendor/dependency"},
    }[case_number]
    if changed_paths != expected:
        raise ExperimentError(
            f"case-{case_number:02d}: replacement changed "
            f"{sorted(changed_paths)!r}, expected {sorted(expected)!r}"
        )


def snapshot_fixture(
    path: Path,
    *,
    commit_oid: str,
    tree_oid: str,
    serialized_inventory: bytes,
    validated_objects: int,
) -> None:
    write_json(
        path,
        {
            "commit_id": commit_oid,
            "fingerprint_sha256": inventory_fingerprint(serialized_inventory),
            "inventory": json.loads(serialized_inventory),
            "tree_id": tree_oid,
            "validated_object_count": validated_objects,
        },
        compact=True,
    )


def verify_status(repo: Path) -> str:
    status = run_git(["status", "--porcelain=v1"], cwd=repo).decode(
        "utf-8", "surrogateescape"
    )
    lines = status.splitlines()
    if " M visible/case.txt" not in lines:
        raise ExperimentError(f"unstaged visible/case.txt mutation missing: {status!r}")
    index_only = [line for line in lines if line.endswith(" visible/index-only.txt")]
    if not index_only or len(index_only[0]) < 2 or index_only[0][1] != "D":
        raise ExperimentError(f"index-only path is not absent from worktree: {status!r}")
    if "?? visible/worktree-only.txt" not in lines:
        raise ExperimentError(f"untracked worktree-only path missing: {status!r}")
    return status


def run_case(case_number: int) -> dict[str, Any]:
    case_start = time.monotonic()
    label = f"case-{case_number:02d}"
    repo = REPOS_DIR / label
    run_git(["init", "--object-format=sha1", "--quiet", str(repo)])
    run_git(["config", "gc.auto", "0"], cwd=repo)
    run_git(["config", "user.name", "Verifier Experiment"], cwd=repo)
    run_git(["config", "user.email", "verifier@example.invalid"], cwd=repo)

    original = original_leaves(repo, case_number)
    original_tree_created = build_tree(repo, original)
    original_oid = commit_tree(
        repo,
        original_tree_created,
        f"original case-{case_number:02d}\n".encode(),
        1_700_000_000 + case_number,
    )
    run_git(["update-ref", "refs/heads/main", original_oid], cwd=repo)

    replacement = replacement_leaves(repo, case_number, original)
    replacement_tree_created = build_tree(repo, replacement)
    replacement_oid = commit_tree(
        repo,
        replacement_tree_created,
        f"replacement case-{case_number:02d}\n".encode(),
        1_700_001_000 + case_number,
    )
    if original_oid == replacement_oid:
        raise ExperimentError(f"{label}: original and replacement commits are equal")

    original_tree, original_bytes, original_validations = raw_inventory(repo, original_oid)
    replacement_tree, replacement_bytes, replacement_validations = raw_inventory(
        repo, replacement_oid
    )
    if original_tree != original_tree_created or replacement_tree != replacement_tree_created:
        raise ExperimentError(f"{label}: raw commit tree differs from constructed tree")
    assert_expected_mutation(case_number, original_bytes, replacement_bytes)

    snapshot_fixture(
        FIXTURES_DIR / f"authenticated-{label}.json",
        commit_oid=original_oid,
        tree_oid=original_tree,
        serialized_inventory=original_bytes,
        validated_objects=original_validations,
    )
    snapshot_fixture(
        FIXTURES_DIR / f"replacement-{label}.json",
        commit_oid=replacement_oid,
        tree_oid=replacement_tree,
        serialized_inventory=replacement_bytes,
        validated_objects=replacement_validations,
    )
    (FIXTURES_DIR / f"pinned-{label}.txt").write_text(original_oid + "\n", encoding="ascii")

    # Construct divergent sparse-checkout, index, and physical worktree state.
    run_git(["checkout", "-f", "main"], cwd=repo)
    run_git(["sparse-checkout", "init", "--no-cone"], cwd=repo)
    run_git(
        ["sparse-checkout", "set", "--no-cone", "--stdin"],
        cwd=repo,
        input_bytes=b"/visible/\n",
    )
    projected = sparse_projection(repo)

    index_only_oid = hash_blob(repo, f"index-only case-{case_number:02d}\n".encode())
    run_git(
        [
            "update-index",
            "--add",
            "--cacheinfo",
            "100644",
            index_only_oid,
            "visible/index-only.txt",
        ],
        cwd=repo,
    )
    visible_dir = repo / "visible"
    (visible_dir / "case.txt").write_bytes(
        f"working-tree mutation case-{case_number:02d}\n".encode()
    )
    (visible_dir / "worktree-only.txt").write_bytes(
        f"untracked case-{case_number:02d}\n".encode()
    )
    status_text = verify_status(repo)

    index_bytes = index_inventory(repo)
    working_bytes = working_tree_inventory(repo)
    fingerprints = {
        "original": inventory_fingerprint(original_bytes),
        "replacement": inventory_fingerprint(replacement_bytes),
        "index": inventory_fingerprint(index_bytes),
        "working_tree": inventory_fingerprint(working_bytes),
    }
    pairwise_distinct = len(set(fingerprints.values())) == 4
    complete_path_sets = {
        "original": path_set(original_bytes),
        "replacement": path_set(replacement_bytes),
        "index": path_set(index_bytes),
        "working_tree": path_set(working_bytes),
    }
    sparse_nonempty = bool(projected)
    sparse_differs_from_all = all(projected != paths for paths in complete_path_sets.values())
    fixture_valid = pairwise_distinct and sparse_nonempty and sparse_differs_from_all
    if not fixture_valid:
        raise ExperimentError(
            f"{label}: invalid fixture: pairwise={pairwise_distinct}, "
            f"sparse_nonempty={sparse_nonempty}, sparse_distinct={sparse_differs_from_all}"
        )

    run_git(["replace", original_oid, replacement_oid], cwd=repo)
    replace_ref = repo / ".git" / "refs" / "replace" / original_oid
    if not replace_ref.is_file() or replace_ref.read_text(encoding="ascii").strip() != replacement_oid:
        raise ExperimentError(f"{label}: replacement ref does not contain R_k")
    resolved = run_git(["rev-parse", f"refs/replace/{original_oid}"], cwd=repo).decode(
        "ascii", "strict"
    ).strip()
    if resolved != replacement_oid:
        raise ExperimentError(f"{label}: replacement ref resolves to {resolved}, not R_k")

    # The tested verifier receives only repo path and the literal authenticated O_k.
    tested_tree, tested_raw_bytes, tested_validations = raw_inventory(repo, original_oid)
    raw_original_equal = tested_raw_bytes == original_bytes
    raw_replacement_equal = tested_raw_bytes == replacement_bytes
    raw_tree_equal = tested_tree == original_tree

    ordinary_bytes = ordinary_inventory(repo, original_oid, disable_replacements=False)
    control_bytes = ordinary_inventory(repo, original_oid, disable_replacements=True)
    ordinary_original_equal = ordinary_bytes == original_bytes
    ordinary_replacement_equal = ordinary_bytes == replacement_bytes
    control_original_equal = control_bytes == original_bytes

    sparse_serialized = canonical_json(sorted(path.hex() for path in projected))
    return {
        "case": case_number,
        "case_name": label,
        "original_commit": original_oid,
        "replacement_commit": replacement_oid,
        "original_tree": original_tree,
        "replacement_tree": replacement_tree,
        "original_fingerprint": fingerprints["original"],
        "replacement_fingerprint": fingerprints["replacement"],
        "index_fingerprint": fingerprints["index"],
        "working_tree_fingerprint": fingerprints["working_tree"],
        "sparse_projection_fingerprint": inventory_fingerprint(sparse_serialized),
        "sparse_projected_path_count": len(projected),
        "pairwise_inventory_fingerprints_distinct": pairwise_distinct,
        "sparse_projection_nonempty": sparse_nonempty,
        "sparse_projection_differs_from_complete_paths": sparse_differs_from_all,
        "fixture_valid": fixture_valid,
        "raw_equals_original": raw_original_equal,
        "raw_equals_replacement": raw_replacement_equal,
        "raw_tree_equals_authenticated_original_tree": raw_tree_equal,
        "ordinary_equals_original": ordinary_original_equal,
        "ordinary_equals_replacement": ordinary_replacement_equal,
        "no_replace_control_equals_original": control_original_equal,
        "authenticated_original_validated_objects": original_validations,
        "replacement_validated_objects": replacement_validations,
        "tested_raw_validated_objects": tested_validations,
        "status_porcelain_v1": status_text,
        "elapsed_seconds": round(time.monotonic() - case_start, 6),
        "case_runtime_seconds": round(time.monotonic() - case_start, 6),
    }


def aggregate(cases: list[dict[str, Any]], versions: tuple[str, str, str]) -> dict[str, Any]:
    python_version, git_version, matplotlib_version = versions
    counts = {
        "raw_original_match_count": sum(case["raw_equals_original"] for case in cases),
        "raw_replacement_match_count": sum(case["raw_equals_replacement"] for case in cases),
        "ordinary_original_match_count": sum(case["ordinary_equals_original"] for case in cases),
        "ordinary_replacement_match_count": sum(case["ordinary_equals_replacement"] for case in cases),
        "no_replace_control_match_count": sum(
            case["no_replace_control_equals_original"] for case in cases
        ),
        "fixture_divergence_count": sum(case["fixture_valid"] for case in cases),
        "raw_tree_match_count": sum(
            case["raw_tree_equals_authenticated_original_tree"] for case in cases
        ),
    }
    runtimes = [float(case["case_runtime_seconds"]) for case in cases]
    total_runtime = time.monotonic() - START_TIME
    supported = (
        len(cases) == CASE_COUNT
        and counts["fixture_divergence_count"] == CASE_COUNT
        and counts["raw_original_match_count"] == CASE_COUNT
        and counts["raw_replacement_match_count"] == 0
        and counts["ordinary_replacement_match_count"] == CASE_COUNT
        and counts["ordinary_original_match_count"] == 0
        and counts["no_replace_control_match_count"] == CASE_COUNT
        and counts["raw_tree_match_count"] == CASE_COUNT
        and OBJECT_INTEGRITY_FAILURE_COUNT == 0
        and PARSING_FAILURE_COUNT == 0
        and COMMAND_FAILURE_COUNT == 0
        and total_runtime <= TIME_LIMIT_SECONDS
    )
    valid_refutation = any(
        case["fixture_valid"]
        and (not case["raw_equals_original"] or not case["ordinary_equals_replacement"])
        for case in cases
    )
    decision = "supported" if supported else "refuted" if valid_refutation else "error"
    per_case_runtimes = {
        f"case_{case['case']:02d}_runtime_seconds": case["case_runtime_seconds"]
        for case in cases
    }
    return {
        "experiment_topic": "authenticated Git commit verification versus refs/replace",
        "decision": decision,
        "hypothesis_supported": supported,
        "case_count": len(cases),
        **counts,
        "object_integrity_failure_count": OBJECT_INTEGRITY_FAILURE_COUNT,
        "parsing_failure_count": PARSING_FAILURE_COUNT,
        "command_failure_count": COMMAND_FAILURE_COUNT,
        "object_validation_count": OBJECT_VALIDATION_COUNT,
        "random_seed": SEED,
        "python_version": python_version,
        "git_version": git_version,
        "matplotlib_version": matplotlib_version,
        "case_runtime_seconds_min": round(min(runtimes), 6) if runtimes else 0.0,
        "case_runtime_seconds_max": round(max(runtimes), 6) if runtimes else 0.0,
        "case_runtime_seconds_mean": round(sum(runtimes) / len(runtimes), 6)
        if runtimes
        else 0.0,
        **per_case_runtimes,
        "total_runtime_seconds": round(total_runtime, 6),
        "within_1800_second_budget": total_runtime <= TIME_LIMIT_SECONDS,
    }


def make_figure(summary: dict[str, Any]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [
        "Raw = original",
        "Raw = replacement",
        "Ordinary = original",
        "Ordinary = replacement",
    ]
    values = [
        summary["raw_original_match_count"],
        summary["raw_replacement_match_count"],
        summary["ordinary_original_match_count"],
        summary["ordinary_replacement_match_count"],
    ]
    colors = ["#2A9D8F", "#E76F51", "#F4A261", "#264653"]
    figure, axis = plt.subplots(figsize=(10.5, 6.0))
    bars = axis.bar(labels, values, color=colors, width=0.68)
    axis.set_ylim(0, 12)
    axis.set_yticks(range(0, 13, 2))
    axis.set_ylabel("Repositories (n=12)")
    axis.set_title("Effect of refs/replace on traversal pinned to the same commit ID")
    axis.grid(axis="y", alpha=0.25)
    axis.set_axisbelow(True)
    for bar, value in zip(bars, values, strict=True):
        y = value + 0.16 if value < 12 else 11.72
        va = "bottom" if value < 12 else "top"
        axis.text(bar.get_x() + bar.get_width() / 2, y, str(value), ha="center", va=va)
    figure.tight_layout()
    figure.savefig(RESULTS_DIR / "key_result.png", dpi=160)
    figure.savefig(FIGURES_DIR / "refs_replace_traversal_counts.png", dpi=160)
    plt.close(figure)


def concise_summary(summary: dict[str, Any]) -> str:
    return (
        "Ran 12 deterministic SHA-1 Git repositories with authenticated loose-object "
        "verification, adversarial refs/replace commits, sparse checkouts, and divergent "
        "index/worktree states.\n"
        f"Key counts: raw=original {summary['raw_original_match_count']}/12, "
        f"raw=replacement {summary['raw_replacement_match_count']}/12, "
        f"ordinary=original {summary['ordinary_original_match_count']}/12, "
        f"ordinary=replacement {summary['ordinary_replacement_match_count']}/12, "
        f"no-replace control=original {summary['no_replace_control_match_count']}/12, "
        f"valid fixtures {summary['fixture_divergence_count']}/12, "
        f"integrity failures {summary['object_integrity_failure_count']}.\n"
        f"Decision: hypothesis {summary['decision']}."
    )


def prepare_output_directories() -> None:
    for path in (REPOS_DIR, RESULTS_DIR, FIGURES_DIR, EMPTY_HOME):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=False)
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def timeout_handler(_signum: int, _frame: Any) -> None:
    raise ExperimentError("experiment exceeded the 1800-second limit")


def main() -> int:
    # PYTHONHASHSEED only takes effect at interpreter startup. Re-exec once when
    # needed so the running experiment, not merely its children, has the pin.
    if os.environ.get("PYTHONHASHSEED") != "0":
        deterministic_env = os.environ.copy()
        deterministic_env.update(
            {
                "LC_ALL": "C",
                "TZ": "UTC",
                "PYTHONHASHSEED": "0",
                "MPLCONFIGDIR": str(CACHE_DIR / "matplotlib"),
                "XDG_CACHE_HOME": str(CACHE_DIR / "xdg"),
            }
        )
        os.execve(sys.executable, [sys.executable, *sys.argv], deterministic_env)
    random.seed(SEED)
    os.environ.update(
        {
            "LC_ALL": "C",
            "TZ": "UTC",
            "PYTHONHASHSEED": "0",
            "MPLCONFIGDIR": str(CACHE_DIR / "matplotlib"),
            "XDG_CACHE_HOME": str(CACHE_DIR / "xdg"),
        }
    )
    locale.setlocale(locale.LC_ALL, "C")
    if hasattr(time, "tzset"):
        time.tzset()
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, TIME_LIMIT_SECONDS)
    cases: list[dict[str, Any]] = []
    try:
        prepare_output_directories()
        versions = preflight()
        for case_number in range(CASE_COUNT):
            cases.append(run_case(case_number))
        summary = aggregate(cases, versions)
        write_json(RESULTS_DIR / "cases.json", cases)
        write_json(RESULTS_DIR / "summary.json", summary)
        write_json(ROOT / "results.json", summary, compact=True)
        make_figure(summary)
        # Refresh runtime after figure generation so the reported total covers the full run.
        summary["total_runtime_seconds"] = round(time.monotonic() - START_TIME, 6)
        summary["within_1800_second_budget"] = (
            summary["total_runtime_seconds"] <= TIME_LIMIT_SECONDS
        )
        write_json(RESULTS_DIR / "summary.json", summary)
        write_json(ROOT / "results.json", summary, compact=True)
        print(concise_summary(summary))
        if summary["decision"] == "error":
            return 2
        return 0
    except Exception as exc:
        error_result = {
            "decision": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "hypothesis_supported": False,
            "case_count": len(cases),
            "object_integrity_failure_count": OBJECT_INTEGRITY_FAILURE_COUNT,
            "parsing_failure_count": PARSING_FAILURE_COUNT,
            "command_failure_count": COMMAND_FAILURE_COUNT,
            "random_seed": SEED,
            "total_runtime_seconds": round(time.monotonic() - START_TIME, 6),
        }
        write_json(ROOT / "results.json", error_result, compact=True)
        if RESULTS_DIR.exists():
            write_json(RESULTS_DIR / "cases.json", cases)
            write_json(RESULTS_DIR / "summary.json", error_result)
        print(
            f"Experiment error after {len(cases)}/{CASE_COUNT} cases: "
            f"{type(exc).__name__}: {exc}"
        )
        return 2
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == "__main__":
    raise SystemExit(main())
