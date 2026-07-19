from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trace_parser import analyze_trace_set


class TraceParserTests(unittest.TestCase):
    def _trace(self, text: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "trace.42"
        path.write_text(text, encoding="utf-8")
        return path

    def test_unfinished_dup_chdir_and_write(self) -> None:
        path = self._trace(
            '100.000000 chdir("/capture") = 0\n'
            '100.100000 openat(AT_FDCWD, "out.csv", O_WRONLY|O_CREAT|O_TRUNC, 0666 <unfinished ...>\n'
            '100.200000 <... openat resumed>) = 3</capture/out.csv>\n'
            '100.300000 dup(3</capture/out.csv>) = 7</capture/out.csv>\n'
            '100.400000 write(7</capture/out.csv>, "x", 1) = 1\n'
            '100.500000 close(7</capture/out.csv>) = 0\n'
        )
        result = analyze_trace_set([path], ["/capture/out.csv"], 99.0)
        provenance = result["/capture/out.csv"]
        self.assertTrue(provenance.created_after_start)
        self.assertTrue(provenance.wrote_positive_bytes)
        self.assertTrue(provenance.write_before_read)

    def test_preexisting_read_then_rewrite_is_negative(self) -> None:
        path = self._trace(
            '100.000000 openat(AT_FDCWD, "/capture/out.csv", O_RDONLY) = 3</capture/out.csv>\n'
            '100.100000 read(3</capture/out.csv>, "x", 1) = 1\n'
            '100.200000 close(3</capture/out.csv>) = 0\n'
            '100.300000 openat(AT_FDCWD, "/capture/out.csv", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 3</capture/out.csv>\n'
            '100.400000 write(3</capture/out.csv>, "x", 1) = 1\n'
        )
        result = analyze_trace_set(
            [path],
            ["/capture/out.csv"],
            99.0,
            initially_absent={"/capture/out.csv": False},
        )
        provenance = result["/capture/out.csv"]
        self.assertFalse(provenance.created_after_start)
        self.assertTrue(provenance.wrote_positive_bytes)
        self.assertFalse(provenance.write_before_read)

    def test_temp_write_then_rename_does_not_retroactively_count_write(self) -> None:
        path = self._trace(
            '100.000000 openat(AT_FDCWD, "/capture/tmp", O_WRONLY|O_CREAT, 0666) = 3</capture/tmp>\n'
            '100.100000 write(3</capture/tmp>, "x", 1) = 1\n'
            '100.200000 close(3</capture/tmp>) = 0\n'
            '100.300000 rename("/capture/tmp", "/capture/out.csv") = 0\n'
        )
        result = analyze_trace_set([path], ["/capture/out.csv"], 99.0)
        provenance = result["/capture/out.csv"]
        self.assertTrue(provenance.created_after_start)
        self.assertFalse(provenance.wrote_positive_bytes)
        self.assertFalse(provenance.write_before_read)


if __name__ == "__main__":
    unittest.main()
