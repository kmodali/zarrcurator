"""pytest plugin printing a summary table of the results per test class.

At the end of a run, a Markdown table lists for each test class (or each test module, for
test functions outside classes) the tests and subtests that passed, failed or were skipped,
with the first line of the class (or module) docstring describing what it covers.

Options:
    --no-summary-table          do not print the table
    --summary-table-file=PATH   also write the table to PATH
"""

from pathlib import Path

try:
    from _pytest.subtests import SubtestReport
except ImportError:  # pytest < 9 has no built-in subtests
    SubtestReport = None


OUTCOMES = ("passed", "failed", "skipped")


def pytest_addoption(parser):
    group = parser.getgroup("summary table")
    group.addoption(
        "--no-summary-table",
        action="store_true",
        default=False,
        help="Do not print the summary table of the results per test class.",
    )
    group.addoption(
        "--summary-table-file",
        default=None,
        help="Also write the summary table of the results per test class to this file (Markdown).",
    )


def pytest_configure(config):
    config._summary_table = SummaryTable()
    config.pluginmanager.register(config._summary_table, "summary-table")


def _first_line(doc):
    return doc.strip().splitlines()[0].strip() if doc and doc.strip() else ""


def _group_key(nodeid):
    """Return (file, class) of a test id; the class is '(functions)' for tests outside classes."""
    parts = nodeid.split("::")
    return Path(parts[0]).name, parts[1] if len(parts) > 2 else "(functions)"


class SummaryTable:
    """Collects the results per test class and prints them as a table."""

    def __init__(self):
        # (file, class) -> {"description", "tests": {outcome: n}, "subtests": {outcome: n}}, in collection order
        self.groups = {}

    def _group(self, key):
        return self.groups.setdefault(
            key,
            {"description": "", "tests": dict.fromkeys(OUTCOMES, 0), "subtests": dict.fromkeys(OUTCOMES, 0)},
        )

    def pytest_collection_modifyitems(self, items):
        for item in items:
            group = self._group(_group_key(item.nodeid))
            if not group["description"]:
                owner = getattr(item, "cls", None) or getattr(item, "module", None)
                group["description"] = _first_line(getattr(owner, "__doc__", None))

    def pytest_runtest_logreport(self, report):
        group = self._group(_group_key(report.nodeid))
        if SubtestReport is not None and isinstance(report, SubtestReport):
            group["subtests"][report.outcome] += 1
        elif report.when == "call" or (report.when == "setup" and not report.passed):
            # Tests skipped or failing in setup have no 'call' report.
            group["tests"][report.outcome] += 1
        elif report.when == "teardown" and report.failed:
            group["tests"]["failed"] += 1

    def lines(self):
        header = "| Test class | File | Tests passed | Failed | Skipped | Subtests passed | Subtests failed | Covers |"
        lines = [header, "|" + "---|" * 8]
        totals = {"tests": dict.fromkeys(OUTCOMES, 0), "subtests": dict.fromkeys(OUTCOMES, 0)}
        for (file_name, class_name), group in self.groups.items():
            tests, subtests = group["tests"], group["subtests"]
            if not any(tests.values()) and not any(subtests.values()):
                continue  # collected but not run, e.g. deselected
            for kind in totals:
                for outcome in OUTCOMES:
                    totals[kind][outcome] += group[kind][outcome]
            lines.append(
                f"| `{class_name}` | `{file_name}` | {tests['passed']} | {tests['failed']} | {tests['skipped']} "
                f"| {subtests['passed']} | {subtests['failed']} | {group['description']} |"
            )
        lines.append(
            f"| **Total** | | **{totals['tests']['passed']}** | **{totals['tests']['failed']}** "
            f"| **{totals['tests']['skipped']}** | **{totals['subtests']['passed']}** "
            f"| **{totals['subtests']['failed']}** | |"
        )
        return lines

    def pytest_terminal_summary(self, terminalreporter, config):
        if config.getoption("no_summary_table") or not self.groups:
            return
        lines = self.lines()
        terminalreporter.write_sep("=", "summary by test class")
        for line in lines:
            terminalreporter.write_line(line)
        path = config.getoption("summary_table_file")
        if path:
            Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
            terminalreporter.write_line(f"summary table written to {path}")
