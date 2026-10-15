"""The summary table of the results per test class, printed by tests/conftest.py."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

SAMPLE_TESTS = '''
import unittest


class TestSample(unittest.TestCase):
    """Sample class covering a bit of everything."""

    def test_passes(self):
        pass

    def test_fails(self):
        self.fail("on purpose")

    @unittest.skip("on purpose")
    def test_skipped(self):
        pass

    def test_with_subtests(self):
        for value in (1, 2, 3):
            with self.subTest(value=value):
                self.assertNotEqual(value, 3)


def test_function():
    pass
'''


class TestSummaryTable(unittest.TestCase):
    """The summary table counts tests and subtests per test class."""

    def _run(self, *args):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            shutil.copy(TESTS_DIR / "conftest.py", tmp_path / "conftest.py")
            (tmp_path / "test_sample.py").write_text(SAMPLE_TESTS, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args],
                cwd=tmp_path,
                capture_output=True,
                text=True,
            )
            table_file = tmp_path / "table.md"
            return result.stdout, table_file.read_text(encoding="utf-8") if table_file.exists() else None

    def test_table_counts_outcomes_per_class(self):
        output, table = self._run("--summary-table-file=table.md")
        self.assertIn("summary by test class", output)
        # As in pytest's own counts, a test whose subtest fails passes itself; the subtest is counted as failed.
        row = "| `TestSample` | `test_sample.py` | 2 | 1 | 1 | 2 | 1 | Sample class covering a bit of everything. |"
        self.assertIn(row, output)
        self.assertIn("| `(functions)` | `test_sample.py` | 1 | 0 | 0 | 0 | 0 |", output)
        self.assertIn("| **Total** | | **3** | **1** | **1** | **2** | **1** | |", output)
        self.assertIn(row, table)

    def test_table_can_be_disabled(self):
        output, table = self._run("--no-summary-table")
        self.assertNotIn("summary by test class", output)
        self.assertIsNone(table)


if __name__ == "__main__":
    unittest.main(verbosity=2)
