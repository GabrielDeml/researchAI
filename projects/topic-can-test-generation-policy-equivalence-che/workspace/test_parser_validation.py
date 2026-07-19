"""Focused adversarial tests for independent archive/schema validation."""

import io
import json
import unittest
import warnings
import zipfile

import independent_parser


def make_archive(
    payload: bytes,
    *,
    name: str = "policy.json",
    compression: int = zipfile.ZIP_STORED,
    extra_entries: tuple[tuple[str, bytes], ...] = (),
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        archive.writestr(name, payload, compress_type=compression)
        for extra_name, extra_payload in extra_entries:
            archive.writestr(extra_name, extra_payload, compress_type=compression)
    return buffer.getvalue()


class IndependentParserValidationTests(unittest.TestCase):
    def assert_rejected(self, archive: bytes):
        with self.assertRaises(independent_parser.ArchiveValidationError):
            independent_parser.parse_archive(archive)

    def test_rejects_invalid_archive_layouts_and_encoding(self):
        valid = b'{"rules":[]}\n'
        cases = {
            "extra entry": make_archive(valid, extra_entries=(("other", b"x"),)),
            "directory": make_archive(valid, name="policy.json/"),
            "traversal": make_archive(valid, name="../policy.json"),
            "compression": make_archive(valid, compression=zipfile.ZIP_DEFLATED),
            "non UTF-8": make_archive(b"\xff"),
            "oversized": make_archive(b" " * (1024 * 1024 + 1)),
        }
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            cases["duplicate entry"] = make_archive(
                valid, extra_entries=(("policy.json", valid),)
            )
        for name, archive in cases.items():
            with self.subTest(name=name):
                self.assert_rejected(archive)

    def test_rejects_schema_violations(self):
        valid_rule = {
            "id": "r00",
            "effect": "allow",
            "principals": ["p0"],
            "actions": ["a0"],
            "resources": ["r0"],
            "mfa": "any",
            "hours": [0],
            "zones": ["internal"],
            "priority": 0,
        }
        documents = [
            {"unknown": True},
            {"default_effect": "maybe"},
            {"rules": {}},
            {"rules": [{}]},
            {"rules": [valid_rule, valid_rule]},
            {"rules": [{**valid_rule, "unknown": True}]},
            {"rules": [{**valid_rule, "effect": 1}]},
            {"rules": [{**valid_rule, "principals": []}]},
            {"rules": [{**valid_rule, "actions": ["a0", "a0"]}]},
            {"rules": [{**valid_rule, "resources": ["r9"]}]},
            {"rules": [{**valid_rule, "mfa": "sometimes"}]},
            {"rules": [{**valid_rule, "hours": [False]}]},
            {"rules": [{**valid_rule, "zones": ["elsewhere"]}]},
            {"rules": [{**valid_rule, "priority": True}]},
            {"rules": [{**valid_rule, "priority": 4}]},
        ]
        for index, document in enumerate(documents):
            with self.subTest(index=index):
                payload = json.dumps(document, separators=(",", ":")).encode()
                self.assert_rejected(make_archive(payload))
        self.assert_rejected(make_archive(b'{"rules":[],"rules":[]}'))


if __name__ == "__main__":
    unittest.main()

