"""Small helpers for STATUS.md, the chief's whole memory (kept at 60 lines or less).

AS400 comparison: STATUS.md is the data area the chief reads before every step.
"""

import sys
from pathlib import Path

MAX_LINES = 60
LOG_HEADING = "## Log"


def _read(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(trim(lines)) + "\n", encoding="utf-8")


def trim(lines: list[str], max_lines: int = MAX_LINES) -> list[str]:
    """Drop the oldest Log lines first, so the top (facts, usage, stops) is never lost."""
    lines = list(lines)
    if LOG_HEADING not in lines:
        return lines[:max_lines]
    log_at = lines.index(LOG_HEADING)
    while len(lines) > max_lines and len(lines) > log_at + 1:
        del lines[log_at + 1]  # oldest log line sits right under the heading
    return lines[:max_lines]


def set_line(path: Path, prefix: str, text: str) -> None:
    """Replace the line that starts with `prefix` (for example 'Usage:'), or add it at the top."""
    lines = _read(path)
    new = f"{prefix} {text}"
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = new
            break
    else:
        lines.insert(1 if lines else 0, new)
    _write(path, lines)


def set_usage_line(path: Path, five_hour, weekly, as_of: str, stopped: bool) -> None:
    """The line the chief updates on every run (Gian, 6 Nov)."""
    text = (
        f"5h {_pct(five_hour)} / weekly {_pct(weekly)} (as of {as_of}), "
        f"stopped {'yes' if stopped else 'no'}"
    )
    set_line(path, "Usage:", text)


def _pct(value) -> str:
    return "unknown" if value is None else f"{value:g}%"


def add_log(path: Path, text: str) -> None:
    lines = _read(path)
    if LOG_HEADING not in lines:
        lines.append(LOG_HEADING)
    lines.append(f"- {text}")
    _write(path, lines)


def mark_paused(path: Path, stage: str, issue: str) -> None:
    """Record that a stage is paused until Gian answers an issue (AC-4)."""
    add_log(path, f"PAUSED {stage}: waiting for Gian, see {issue}")


if __name__ == "__main__":
    print(f"{len(_read(Path(sys.argv[1])))} lines")
