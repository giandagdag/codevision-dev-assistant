"""Evidence helper: copied INTO the sandbox (as da_evidence.py) and called by the tests.

A test calls `evidence(self, "total", (2, 3), 5, 5)` before its assert. It is like a job log line
that prints the input record, the expected value and the value the step really produced.
Standard library only: it runs with `python -I` inside the sandbox and must stand alone, so the
secret patterns below are a copy of `_SECRET_PATTERNS` in da_understand_checks.py (a test fails if
the two lists ever differ).
"""

import re

VALUE_LIMIT = 500
HIDDEN = "[hidden]"
SECRET_PATTERNS = (
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"\bsk-[A-Za-z0-9_-]{20,}",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\b(?:password|passwd|pwd|secret|api[_ -]?key|token)\s*[:=]\s*\S+",
)
_SECRETS = [re.compile(pattern, re.IGNORECASE) for pattern in SECRET_PATTERNS]

# The runner reads and clears this list after each test.
lines: list[dict] = []


def _show(value) -> tuple[str, bool]:
    """(text, cut): the repr of a value, hidden if it looks like a secret, cut at 500."""
    try:
        text = repr(value)
    except Exception:  # a broken __repr__ must not fail the test
        text = "<repr failed>"
    if any(pattern.search(text) for pattern in _SECRETS):
        return HIDDEN, False
    return text[:VALUE_LIMIT], len(text) > VALUE_LIMIT


def evidence(test, label, given, expected, actual) -> None:
    """Record one check. `test` is accepted so the call reads like an assert (self first)."""
    try:
        match = bool(expected == actual)
    except Exception:  # odd objects may refuse to compare
        match = False
    shown = [_show(given), _show(expected), _show(actual)]
    lines.append(
        {
            "label": str(label)[:VALUE_LIMIT],
            "given": shown[0][0],
            "expected": shown[1][0],
            "actual": shown[2][0],
            "match": match,
            "cut": any(cut for _text, cut in shown),
        }
    )
