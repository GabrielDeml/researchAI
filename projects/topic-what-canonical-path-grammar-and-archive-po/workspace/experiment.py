#!/usr/bin/env python3
"""Canonical archive-path validation experiment.

Generates a fully enumerated two-entry PAX corpus, round-trips every manifest
through ``tarfile``, and compares an exact canonical-key duplicate detector
with an archive-wide component-trie validator. Archives are never extracted.
"""

from __future__ import annotations

import csv
import io
import json
import os
import random
import re
import tarfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal, Sequence

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / ".cache"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


SEED = 20250308
FIGURES_DIR = ROOT / "figures"
CSV_PATH = ROOT / "validation_results.csv"
RESULTS_PATH = ROOT / "results.json"

EntryType = Literal["regular", "directory", "symlink"]
Entry = tuple[str, EntryType]

DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
RESERVED_STEMS = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


class PathParseError(ValueError):
    """A member name violates the shared archive path grammar."""


@dataclass(frozen=True)
class ParsedPath:
    canonical: str
    canonical_components: tuple[str, ...]
    raw_components: tuple[str, ...]


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    reason: str


@dataclass(frozen=True)
class ArchiveCase:
    archive_id: str
    archive_class: Literal["ancestor", "type", "implicit_alias", "control"]
    entries: tuple[Entry, Entry]


@dataclass
class TrieNode:
    children: dict[str, "TrieNode"] = field(default_factory=dict)
    complete_types: list[EntryType] = field(default_factory=list)
    raw_prefixes: set[tuple[str, ...]] = field(default_factory=set)


def parse_path(raw_name: str) -> ParsedPath:
    """Parse one member name according to the experiment's shared grammar."""
    if raw_name == "":
        raise PathParseError("empty name")
    if raw_name.startswith("/"):
        raise PathParseError("absolute path before separator conversion")
    if DRIVE_PREFIX.match(raw_name):
        raise PathParseError("ASCII drive prefix")
    if ":" in raw_name:
        raise PathParseError("colon")
    for char in raw_name:
        codepoint = ord(char)
        if codepoint == 0 or 1 <= codepoint <= 31 or codepoint == 127:
            raise PathParseError(f"control character U+{codepoint:04X}")

    converted = raw_name.replace("\\", "/")
    if converted.startswith("/"):
        raise PathParseError("absolute path after separator conversion")

    raw_components = tuple(converted.split("/"))
    if any(component == "" for component in raw_components):
        raise PathParseError("empty component")

    canonical_components: list[str] = []
    for component in raw_components:
        canonical = unicodedata.normalize("NFKC", component).casefold().rstrip(" .")
        if canonical in {"", ".", ".."}:
            raise PathParseError(f"forbidden canonical component {canonical!r}")
        stem = canonical.split(".", 1)[0]
        if stem in RESERVED_STEMS:
            raise PathParseError(f"reserved platform name {stem!r}")
        canonical_components.append(canonical)

    canonical_tuple = tuple(canonical_components)
    return ParsedPath(
        canonical="/".join(canonical_tuple),
        canonical_components=canonical_tuple,
        raw_components=raw_components,
    )


def parser_oracle() -> tuple[list[dict[str, object]], int, int]:
    valid_cases = [
        ("a/b", "a/b"),
        ("A/B", "a/b"),
        ("a\\b", "a/b"),
        ("café/x", "café/x"),
        ("cafe\u0301/x", "café/x"),
        ("Ａlpha/x", "alpha/x"),
        ("Data./x", "data/x"),
        ("Data /x", "data/x"),
        ("Straße/x", "strasse/x"),
        ("x/y-z_1", "x/y-z_1"),
    ]
    invalid_cases = [
        "",
        "/abs",
        "\\abs",
        "C:/abs",
        "c:\\abs",
        "\\\\server\\share\\x",
        "//server/share/x",
        "../x",
        "a/../x",
        "..\\x",
        "a\\..\\x",
        "．．/x",
        "a/．．/x",
        "a//b",
        "a\\\\b",
        "a/ /b",
        ".",
        "a/.",
        "a:b",
        "file:stream",
        "a" + chr(0) + "b",
        "a" + chr(10) + "b",
        "a" + chr(127) + "b",
        "CON",
        "nul.txt",
        "a/COM1",
        "Lpt9/data",
    ]

    outcomes: list[dict[str, object]] = []
    valid_matches = 0
    for raw_name, expected in valid_cases:
        try:
            actual = parse_path(raw_name).canonical
            matched = actual == expected
            detail = actual
        except PathParseError as exc:
            matched = False
            detail = f"rejected: {exc}"
        valid_matches += int(matched)
        outcomes.append(
            {
                "category": "valid",
                "input": raw_name,
                "expected": expected,
                "actual": detail,
                "matched": matched,
            }
        )

    invalid_matches = 0
    for raw_name in invalid_cases:
        try:
            detail = parse_path(raw_name).canonical
            matched = False
        except PathParseError as exc:
            detail = f"rejected: {exc}"
            matched = True
        invalid_matches += int(matched)
        outcomes.append(
            {
                "category": "invalid",
                "input": raw_name,
                "expected": "rejected",
                "actual": detail,
                "matched": matched,
            }
        )

    return outcomes, valid_matches, invalid_matches


def exact_key(entries: Sequence[Entry]) -> ValidationResult:
    parsed_entries: list[ParsedPath] = []
    for raw_name, _entry_type in entries:
        try:
            parsed_entries.append(parse_path(raw_name))
        except PathParseError as exc:
            return ValidationResult(False, f"parser error: {exc}")

    seen: set[str] = set()
    for parsed in parsed_entries:
        if parsed.canonical in seen:
            return ValidationResult(False, f"duplicate canonical path: {parsed.canonical}")
        seen.add(parsed.canonical)
    return ValidationResult(True, "accepted")


def walk_trie(node: TrieNode, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], TrieNode]]:
    yield path, node
    for component in sorted(node.children):
        yield from walk_trie(node.children[component], path + (component,))


def component_trie(entries: Sequence[Entry]) -> ValidationResult:
    parsed_entries: list[tuple[ParsedPath, EntryType]] = []
    for raw_name, entry_type in entries:
        try:
            parsed_entries.append((parse_path(raw_name), entry_type))
        except PathParseError as exc:
            return ValidationResult(False, f"parser error: {exc}")

    root = TrieNode()
    for parsed, entry_type in parsed_entries:
        node = root
        component_count = len(parsed.canonical_components)
        for depth, canonical_component in enumerate(parsed.canonical_components, start=1):
            node = node.children.setdefault(canonical_component, TrieNode())
            if depth < component_count:
                node.raw_prefixes.add(parsed.raw_components[:depth])
        node.complete_types.append(entry_type)

    for path, node in walk_trie(root):
        canonical_path = "/".join(path) or "<root>"
        if len(node.complete_types) > 1:
            return ValidationResult(False, f"duplicate canonical path: {canonical_path}")
        types = set(node.complete_types)
        if "directory" in types and ({"regular", "symlink"} & types):
            return ValidationResult(False, f"directory/type conflict: {canonical_path}")
        if ({"regular", "symlink"} & types) and node.children:
            return ValidationResult(False, f"non-directory has descendant: {canonical_path}")
        if len(node.raw_prefixes) > 1:
            return ValidationResult(False, f"raw-prefix spelling collision: {canonical_path}")

    return ValidationResult(True, "accepted")


def generate_corpus() -> list[ArchiveCase]:
    cases: list[ArchiveCase] = []

    for i in range(24):
        path = f"ancestor{i:02d}/node"
        ancestor_type: EntryType = "regular" if i < 12 else "symlink"
        cases.append(
            ArchiveCase(
                archive_id=f"ancestor-{i:02d}",
                archive_class="ancestor",
                entries=((path, ancestor_type), (path + "/child.txt", "regular")),
            )
        )

    for i in range(24):
        path = f"type{i:02d}/node"
        conflicting_type: EntryType = "regular" if i < 12 else "symlink"
        cases.append(
            ArchiveCase(
                archive_id=f"type-{i:02d}",
                archive_class="type",
                entries=((path, "directory"), (path, conflicting_type)),
            )
        )

    alias_pairs = [
        ("Alpha", "alpha"),
        ("café", "cafe\u0301"),
        ("Ａlpha", "Alpha"),
        ("data.", "data"),
        ("data ", "data"),
        ("Straße", "STRASSE"),
    ]
    contexts = ["", "outer", "outer/deep", "x/y/z"]
    alias_index = 0
    for left_alias, right_alias in alias_pairs:
        for context in contexts:
            left_prefix = "/".join(part for part in (context, left_alias) if part)
            right_prefix = "/".join(part for part in (context, right_alias) if part)
            left_name = left_prefix + "/left.txt"
            right_name = right_prefix + "/right.txt"
            left_parsed = parse_path(left_name)
            right_parsed = parse_path(right_name)
            assert left_parsed.canonical != right_parsed.canonical
            assert left_parsed.canonical_components[:-1] == right_parsed.canonical_components[:-1]
            assert left_parsed.raw_components[:-1] != right_parsed.raw_components[:-1]
            cases.append(
                ArchiveCase(
                    archive_id=f"implicit-alias-{alias_index:02d}",
                    archive_class="implicit_alias",
                    entries=((left_name, "regular"), (right_name, "regular")),
                )
            )
            alias_index += 1

    for i in range(8):
        path = f"ctrl-dir{i}/node"
        cases.append(
            ArchiveCase(
                archive_id=f"control-{i:02d}",
                archive_class="control",
                entries=((path, "directory"), (path + "/child.txt", "regular")),
            )
        )
    for i in range(8):
        cases.append(
            ArchiveCase(
                archive_id=f"control-{i + 8:02d}",
                archive_class="control",
                entries=(
                    (f"ctrl-file{i}/node", "regular"),
                    (f"ctrl-file{i}/node2/child.txt", "regular"),
                ),
            )
        )
    for i in range(8):
        prefix = f"ctrl-implicit{i}/node"
        cases.append(
            ArchiveCase(
                archive_id=f"control-{i + 16:02d}",
                archive_class="control",
                entries=((prefix + "/left.txt", "regular"), (prefix + "/right.txt", "regular")),
            )
        )

    class_counts = {archive_class: sum(case.archive_class == archive_class for case in cases) for archive_class in {case.archive_class for case in cases}}
    assert class_counts == {"ancestor": 24, "type": 24, "implicit_alias": 24, "control": 24}
    assert len(cases) == 96
    assert len({case.archive_id for case in cases}) == len(cases)
    return cases


def pax_round_trip(entries: Sequence[Entry]) -> tuple[Entry, ...]:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for raw_name, entry_type in entries:
            info = tarfile.TarInfo(name=raw_name)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            if entry_type == "regular":
                info.type = tarfile.REGTYPE
                info.size = 1
                archive.addfile(info, io.BytesIO(b"x"))
            elif entry_type == "directory":
                info.type = tarfile.DIRTYPE
                info.size = 0
                archive.addfile(info)
            elif entry_type == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = "safe-target"
                info.size = 0
                archive.addfile(info)
            else:
                raise AssertionError(f"unsupported entry type: {entry_type}")

    decoded: list[Entry] = []
    payload.seek(0)
    with tarfile.open(fileobj=payload, mode="r:") as archive:
        for member in archive:
            if member.isreg():
                decoded_type: EntryType = "regular"
                extracted = archive.extractfile(member)
                if extracted is None or extracted.read() != b"x":
                    raise RuntimeError(f"corpus-integrity failure: bad regular payload for {member.name!r}")
            elif member.isdir():
                decoded_type = "directory"
            elif member.issym():
                decoded_type = "symlink"
                if member.linkname != "safe-target":
                    raise RuntimeError(f"corpus-integrity failure: bad symlink target for {member.name!r}")
            else:
                raise RuntimeError(f"corpus-integrity failure: unexpected tar type for {member.name!r}")
            decoded.append((member.name, decoded_type))
    return tuple(decoded)


def archive_order_metrics(rows: Sequence[dict[str, object]], validator: str, archive_class: str | None = None) -> tuple[int, int]:
    relevant = [
        row
        for row in rows
        if row["validator"] == validator and (archive_class is None or row["class"] == archive_class)
    ]
    by_archive: dict[str, dict[str, bool]] = {}
    for row in relevant:
        by_archive.setdefault(str(row["archive_id"]), {})[str(row["order"])] = bool(row["accepted"])
    if any(set(orders) != {"forward", "reverse"} for orders in by_archive.values()):
        raise AssertionError("missing order result")
    accepted_both = sum(orders["forward"] and orders["reverse"] for orders in by_archive.values())
    disagreements = sum(orders["forward"] != orders["reverse"] for orders in by_archive.values())
    return accepted_both, disagreements


def write_csv(rows: Sequence[dict[str, object]]) -> None:
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["archive_id", "class", "order", "validator", "accepted", "rejection_reason"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def create_figure(run_counts: dict[tuple[str, str], int], disagreement_counts: dict[str, int]) -> None:
    display_classes = ["ancestor", "type", "implicit alias", "control"]
    data_classes = ["ancestor", "type", "implicit_alias", "control"]
    validators = ["exact-key", "component-trie"]
    colors = ["#4C78A8", "#F58518"]
    x_positions = list(range(len(display_classes)))
    width = 0.36

    figure, axis = plt.subplots(figsize=(10, 6))
    for validator_index, validator in enumerate(validators):
        offset = (validator_index - 0.5) * width
        counts = [run_counts[(validator, archive_class)] for archive_class in data_classes]
        percentages = [count / 48 * 100 for count in counts]
        bars = axis.bar(
            [x + offset for x in x_positions],
            percentages,
            width,
            label=validator,
            color=colors[validator_index],
        )
        for bar, count, percentage in zip(bars, counts, percentages, strict=True):
            if percentage >= 10:
                label_y = percentage - 2
                vertical_alignment = "top"
                label_color = "white"
            else:
                label_y = percentage + 1.5
                vertical_alignment = "bottom"
                label_color = "black"
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                label_y,
                str(count),
                ha="center",
                va=vertical_alignment,
                color=label_color,
                fontweight="bold",
                fontsize=10,
            )

    axis.set_xticks(x_positions, display_classes)
    axis.set_ylim(0, 100)
    axis.set_ylabel("Order-specific runs accepted (%)")
    axis.set_xlabel("Archive class")
    figure.suptitle("Canonical archive-path validator acceptance by class", y=0.98)
    handles, labels = axis.get_legend_handles_labels()
    figure.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.94), ncols=2)
    axis.grid(axis="y", alpha=0.25)
    disagreement_text = "Order disagreements: " + "; ".join(
        f"{validator}={disagreement_counts[validator]}" for validator in validators
    )
    figure.text(0.5, 0.01, disagreement_text, ha="center", fontsize=10)
    figure.tight_layout(rect=(0, 0.04, 1, 0.86))
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURES_DIR / "acceptance_by_class.png", dpi=180)
    plt.close(figure)


def main() -> int:
    random.seed(SEED)

    oracle_results, oracle_valid_matches, oracle_invalid_matches = parser_oracle()
    oracle_total = len(oracle_results)
    oracle_matches = oracle_valid_matches + oracle_invalid_matches
    oracle_accuracy = oracle_matches / oracle_total
    if oracle_matches != oracle_total:
        raise RuntimeError("parser-oracle failure: parser does not exactly match fixed oracle")

    corpus = generate_corpus()
    validators = {"exact-key": exact_key, "component-trie": component_trie}
    rows: list[dict[str, object]] = []
    integrity_matches = 0
    total_streams = 0

    for case in corpus:
        for order in ("forward", "reverse"):
            source_entries = case.entries if order == "forward" else tuple(reversed(case.entries))
            decoded_entries = pax_round_trip(source_entries)
            total_streams += 1
            if decoded_entries != tuple(source_entries):
                raise RuntimeError(
                    f"corpus-integrity failure for {case.archive_id}/{order}: "
                    f"expected {source_entries!r}, got {decoded_entries!r}"
                )
            integrity_matches += 1
            for validator_name, validator in validators.items():
                result = validator(decoded_entries)
                rows.append(
                    {
                        "archive_id": case.archive_id,
                        "class": case.archive_class,
                        "order": order,
                        "validator": validator_name,
                        "accepted": result.accepted,
                        "rejection_reason": "" if result.accepted else result.reason,
                    }
                )

    assert total_streams == 192
    assert len(rows) == 384
    write_csv(rows)

    class_names = ["ancestor", "type", "implicit_alias", "control"]
    run_counts = {
        (validator, archive_class): sum(
            bool(row["accepted"])
            for row in rows
            if row["validator"] == validator and row["class"] == archive_class
        )
        for validator in validators
        for archive_class in class_names
    }
    archive_counts: dict[tuple[str, str], int] = {}
    class_disagreements: dict[tuple[str, str], int] = {}
    for validator in validators:
        for archive_class in class_names:
            accepted_both, disagreements = archive_order_metrics(rows, validator, archive_class)
            archive_counts[(validator, archive_class)] = accepted_both
            class_disagreements[(validator, archive_class)] = disagreements

    disagreement_counts = {
        validator: archive_order_metrics(rows, validator)[1] for validator in validators
    }
    create_figure(run_counts, disagreement_counts)

    conflict_classes = ["ancestor", "type", "implicit_alias"]
    component_trie_conflict_accepted_runs = sum(
        run_counts[("component-trie", archive_class)] for archive_class in conflict_classes
    )
    component_trie_conflict_rejected_runs = 144 - component_trie_conflict_accepted_runs
    component_trie_conflict_archives_accepted_both = sum(
        archive_counts[("component-trie", archive_class)] for archive_class in conflict_classes
    )
    component_trie_conflict_archives_rejected_both = sum(
        24 - archive_counts[("component-trie", archive_class)] - class_disagreements[("component-trie", archive_class)]
        for archive_class in conflict_classes
    )
    exact_key_conflict_accepted_runs = sum(
        run_counts[("exact-key", archive_class)] for archive_class in conflict_classes
    )
    exact_key_conflict_archives_accepted_both = sum(
        archive_counts[("exact-key", archive_class)] for archive_class in conflict_classes
    )

    hypothesis_supported = all(
        [
            oracle_accuracy == 1.0,
            integrity_matches == 192,
            component_trie_conflict_accepted_runs == 0,
            component_trie_conflict_archives_rejected_both == 72,
            exact_key_conflict_archives_accepted_both >= 48,
            exact_key_conflict_accepted_runs >= 96,
            disagreement_counts["exact-key"] == 0,
            run_counts[("exact-key", "control")] == 48,
            run_counts[("component-trie", "control")] == 48,
            disagreement_counts["component-trie"] == 0,
        ]
    )

    results: dict[str, str | int | float | bool] = {
        "seed": SEED,
        "python_version_requirement_met": True,
        "parser_oracle_valid_matches": oracle_valid_matches,
        "parser_oracle_valid_total": 10,
        "parser_oracle_invalid_matches": oracle_invalid_matches,
        "parser_oracle_invalid_total": 27,
        "parser_oracle_matches": oracle_matches,
        "parser_oracle_total": oracle_total,
        "parser_oracle_accuracy": oracle_accuracy,
        "parser_oracle_results": json.dumps(oracle_results, ensure_ascii=False, separators=(",", ":")),
        "archive_count": len(corpus),
        "pax_stream_count": total_streams,
        "validator_stream_pair_count": len(rows),
        "corpus_integrity_matches": integrity_matches,
        "corpus_integrity_total": total_streams,
        "corpus_integrity_rate": integrity_matches / total_streams,
        "component_trie_conflict_runs_rejected": component_trie_conflict_rejected_runs,
        "component_trie_conflict_runs_total": 144,
        "component_trie_conflict_rejection_rate": component_trie_conflict_rejected_runs / 144,
        "component_trie_conflict_archives_accepted_both_orders": component_trie_conflict_archives_accepted_both,
        "component_trie_conflict_archives_rejected_both_orders": component_trie_conflict_archives_rejected_both,
        "exact_key_conflict_runs_accepted": exact_key_conflict_accepted_runs,
        "exact_key_conflict_runs_total": 144,
        "exact_key_conflict_archives_accepted_both_orders": exact_key_conflict_archives_accepted_both,
        "exact_key_conflict_archives_total": 72,
        "exact_key_order_disagreements": disagreement_counts["exact-key"],
        "component_trie_order_disagreements": disagreement_counts["component-trie"],
        "hypothesis_supported": hypothesis_supported,
        "hypothesis_conclusion": "supported" if hypothesis_supported else "refuted",
    }
    for validator in validators:
        metric_prefix = validator.replace("-", "_")
        for archive_class in class_names:
            results[f"{metric_prefix}_{archive_class}_runs_accepted"] = run_counts[(validator, archive_class)]
            results[f"{metric_prefix}_{archive_class}_runs_total"] = 48
            results[f"{metric_prefix}_{archive_class}_archives_accepted_both_orders"] = archive_counts[(validator, archive_class)]
            results[f"{metric_prefix}_{archive_class}_order_disagreements"] = class_disagreements[(validator, archive_class)]
        results[f"{metric_prefix}_control_acceptance_rate"] = run_counts[(validator, "control")] / 48

    with RESULTS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")

    print("Ran 96 manifests as 192 in-memory PAX streams (forward and reverse), with 384 validator-stream evaluations.")
    print(
        f"Parser oracle: {oracle_matches}/{oracle_total}; corpus integrity: {integrity_matches}/{total_streams}."
    )
    print(
        "Accepted runs by class (ancestor/type/implicit_alias/control): "
        f"exact-key={','.join(str(run_counts[('exact-key', name)]) for name in class_names)}; "
        f"component-trie={','.join(str(run_counts[('component-trie', name)]) for name in class_names)}."
    )
    print(
        f"Conflict archives accepted in both orders: exact-key={exact_key_conflict_archives_accepted_both}/72; "
        f"component-trie={component_trie_conflict_archives_accepted_both}/72."
    )
    print(
        f"Order disagreements: exact-key={disagreement_counts['exact-key']}; "
        f"component-trie={disagreement_counts['component-trie']}."
    )
    print(f"Hypothesis: {'SUPPORTED' if hypothesis_supported else 'REFUTED'}.")
    return 0 if hypothesis_supported else 1


if __name__ == "__main__":
    raise SystemExit(main())
