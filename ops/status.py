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


def _is_next(line: str) -> bool:
    return line.lstrip("- ").startswith("Next:")


def set_next(path: Path, text: str) -> None:
    """Make the file hold exactly one `- Next:` line, with this text (Phase A fix 3, F2).

    Replaces the first one together with its indented continuation lines, deletes any other
    `Next:` lines, and adds the line at the end of "## Where we are" when there is none. Empty
    text is refused, so a typo can never blank the chief's next step.
    """
    text = " ".join(text.split())
    if not text:
        raise ValueError("the next step cannot be empty")
    new = f"- Next: {text}"
    lines, out, placed, skipping = _read(path), [], False, False
    for line in lines:
        if skipping and line.startswith("  ") and line.strip():
            continue  # a continuation of a Next line that is being replaced or removed
        skipping = _is_next(line)
        if skipping:
            if not placed:
                out.append(new)
                placed = True
            continue
        out.append(line)
    if not placed:
        out = _insert_in_section(out, new)
    _write(path, out)


def _insert_in_section(lines: list[str], new: str) -> list[str]:
    """Put `new` at the end of "## Where we are" (the heading is added if it is missing)."""
    heading = "## Where we are"
    if heading not in lines:
        at = lines.index(LOG_HEADING) if LOG_HEADING in lines else len(lines)
        return lines[:at] + [heading, new, ""] + lines[at:]
    start = lines.index(heading) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    while end > start and not lines[end - 1].strip():
        end -= 1  # keep the blank line that separates the sections
    return lines[:end] + [new] + lines[end:]


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
