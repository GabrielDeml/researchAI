"""Static dependency boundary tests for the independent checker."""

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class DependencyBoundaryTests(unittest.TestCase):
    def test_generator_does_not_import_consumers(self):
        tree = ast.parse((ROOT / "testgen.py").read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        self.assertNotIn("canonicalizer", imported)
        self.assertNotIn("verifier", imported)

    def test_independent_modules_do_not_import_canonicalizer(self):
        for filename in ("independent_parser.py", "verifier.py"):
            tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
            imported = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)
            self.assertNotIn("canonicalizer", imported, filename)

    def test_verifier_enumerates_exactly_1024_requests(self):
        import verifier

        self.assertEqual(sum(1 for _ in verifier.all_requests()), 1024)


if __name__ == "__main__":
    unittest.main()
