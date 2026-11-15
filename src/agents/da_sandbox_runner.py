"""The test runner that is copied INTO the sandbox folder and run by a separate Python process.

It must stay tiny and use only the standard library: it runs with `python -I`, in a folder that
holds only a copy of CodeVision's source, the build's code files and the frozen test. It is never
imported by the Developer Assistant itself.

It runs unittest discovery on tests/<id>/ only, and after EVERY test it rewrites results.json (and
running.txt before each test), so if the time limit ends the process, the server still knows which
tests finished and which one was running. Like a job log that is written line by line, not at the
end of the job.
"""

import json
import os
import sys
import traceback
import unittest

TRACEBACK_LINES = 20


class RecordingResult(unittest.TestResult):
    """Remembers each finished test and saves the list after each one."""

    def __init__(self, root: str):
        super().__init__()
        self._root = root
        self.outcomes: list[dict] = []

    def startTest(self, test):
        super().startTest(test)
        _write(os.path.join(self._root, "running.txt"), _name(test))

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, "pass", "", [])

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record(test, "fail", _message(err), _tail(err))

    def addError(self, test, err):
        super().addError(test, err)
        self._record(test, "error", _message(err), _tail(err))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(test, "skipped", reason, [])

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._record(test, "expected_failure", _message(err), [])

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._record(test, "unexpected_success", "Passed, but was marked as expected to fail.", [])

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        # A passing sub-test says nothing: the parent gets its own addSuccess if all pass.
        if err is not None:
            self._record(test, "fail", _message(err), _tail(err))

    def _record(self, test, result: str, message: str, tail: list[str]) -> None:
        # One row per test: the first non-pass outcome (a failing sub-test) is kept.
        if any(row["name"] == _name(test) for row in self.outcomes):
            return
        self.outcomes.append(
            {"name": _name(test), "result": result, "message": message, "traceback_tail": tail}
        )
        _write(os.path.join(self._root, "results.json"), json.dumps({"tests": self.outcomes}))


def _name(test) -> str:
    return getattr(test, "_testMethodName", str(test))


def _message(err) -> str:
    text = str(err[1]).strip()
    return text[:500] if text else err[0].__name__


def _tail(err) -> list[str]:
    lines = "".join(traceback.format_exception(*err)).splitlines()
    return lines[-TRACEBACK_LINES:]


def _write(path: str, text: str) -> None:
    # Write to a side file, then replace, so the server never reads half a file.
    side = path + ".part"
    with open(side, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(side, path)


def main(root: str, test_id: str) -> int:
    # `python -I` leaves the working folder off sys.path, so add the two places imports come from:
    # src (modules import each other as they do when CodeVision starts from src) and the top
    # folder (for the tests package).
    sys.path.insert(0, os.path.join(root, "src"))
    sys.path.insert(0, root)
    suite = unittest.TestLoader().discover(
        start_dir=os.path.join(root, "tests", test_id), pattern="test_*.py", top_level_dir=root
    )
    result = RecordingResult(root)
    suite.run(result)
    # A folder with no tests at all still gets a results file, so "found nothing" is visible.
    _write(os.path.join(root, "results.json"), json.dumps({"tests": result.outcomes}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
