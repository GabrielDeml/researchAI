"""Focused standard-library tests for parser independence and validation."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

from independent_parser import PolicyParseError, parse_archive


def archive(policy: dict, version: object = 1) -> bytes:
    return (json.dumps({"version": version, "policy": policy}) + "\n").encode()


class ParserTests(unittest.TestCase):
    def test_defaults_and_empty_lists(self) -> None:
        parsed = parse_archive(archive({"policy_id": "P", "subjects": []}))
        self.assertEqual(parsed["subjects"], [])
        self.assertEqual(parsed["actions"], ["a0", "a1", "a2", "a3"])
        self.assertEqual(parsed["effect"], "deny")
        self.assertEqual(parsed["max_amount"], 3)

    def test_rejects_required_invalid_forms(self) -> None:
        invalid = [
            b"{\n",
            archive({}),
            archive({"policy_id": 3}),
            archive({"policy_id": "P", "extra": True}),
            archive({"policy_id": "P"}, version=True),
            archive({"policy_id": "P", "subjects": ["s1", "s0"]}),
            archive({"policy_id": "P", "subjects": ["s0", "s0"]}),
            archive({"policy_id": "P", "subjects": ["s4"]}),
            archive({"policy_id": "P", "min_clearance": 4}),
            archive({"policy_id": "P", "require_mfa": 1}),
            archive({"policy_id": "P"}) + b"\n",
        ]
        for data in invalid:
            with self.subTest(data=data):
                with self.assertRaises(PolicyParseError):
                    parse_archive(data)

    def test_independent_module_import_boundaries(self) -> None:
        root = Path(__file__).resolve().parent
        imports: dict[str, set[str]] = {}
        for name in ("canonicalizers.py", "independent_parser.py", "independent_verifier.py"):
            tree = ast.parse((root / name).read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            imports[name] = imported
        self.assertNotIn("canonicalizers", imports["independent_parser.py"])
        self.assertNotIn("canonicalizers", imports["independent_verifier.py"])
        self.assertNotIn("independent_parser", imports["canonicalizers.py"])
        self.assertNotIn("independent_verifier", imports["canonicalizers.py"])


if __name__ == "__main__":
    unittest.main()
