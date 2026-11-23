"""Name the kinds of problem in a rejected AI reply, for log lines (Fix G7, R5).

A log line used to say only "3 problems". The kinds say what went wrong without ever repeating
the AI's own text (that stays in logs/da_rejected_replies.log).
"""

# (kind, a phrase of the app's own check sentence). The first match wins, so the length words
# come before the general "wrong shape".
_KIND_PHRASES: tuple[tuple[str, str], ...] = (
    ("json", "not valid json"),
    ("too_long", "at most"),
    ("too_long", "too long"),
    ("shape", "wrong shape"),
    ("library", "library '"),
    ("library", "not in the python standard library"),
    ("protected", "is protected"),
    ("folder", "allowed folder"),
    ("file_name", "file name must match"),
    ("reuse", "reuse"),
    ("reuse", "discover hit"),
    ("design", "design"),
)


def problem_kind(problem: str) -> str:
    lower = problem.lower()
    for kind, phrase in _KIND_PHRASES:
        if phrase in lower:
            return kind
    return "other"


def problem_kinds(problems: list[str]) -> str:
    """For example "2 problems (library, folder)"."""
    kinds = sorted({problem_kind(problem) for problem in problems})
    noun = "problem" if len(problems) == 1 else "problems"
    return f"{len(problems)} {noun} ({', '.join(kinds)})" if kinds else "0 problems"
