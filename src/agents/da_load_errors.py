"""Fix NP: whose fault is a test file that cannot load? Decided once, from the error itself.

Like reading the message in a failed CALL: "object not found in library list" is the system
administrator's job; "program ended with a wrong parameter" is the programmer's. Plain code, no AI.
"""

import re
from pathlib import Path

from agents.da_check_words import FROZEN_TEST_TEXT, MISSING_LIBRARY_TEXT, NOT_PROVEN_TEXT
from agents.da_evidence_helper import hide_secret
from pydantic_classes.da_build_models import LayerBResult, LoadError

_MISSING = re.compile(r"No module named '([^']+)'")
_FROM = re.compile(r"cannot import name '[^']+' from '([^']+)'")
SYSTEM_FAULTS = ("missing_library", "frozen_test")  # the Developer Assistant / server's problem


def classify_load_error(
    error: LoadError, reference_src: Path, planned_paths: list[str]
) -> tuple[str, str]:
    """(fault, module). fault is missing_library, planned_code or frozen_test; module names the
    missing library (empty otherwise).

    planned_code: the AI can fix it (a wrong name or path in the written code). missing_library:
    the server's Python lacks something nobody here can add. frozen_test: the frozen test itself
    cannot run, and it is never rewritten silently."""
    planned = [path.replace("\\", "/") for path in planned_paths]
    stems = {Path(path).stem for path in planned}
    trace = "\n".join(error.traceback_tail).replace("\\", "/")
    in_planned = any(path in trace for path in planned)
    if error.kind != "import":  # a set-up that fails inside the written code is the AI's to fix
        return ("planned_code" if in_planned else "frozen_test"), ""
    wanted = _MISSING.search(error.message)
    wrong_name = _FROM.search(error.message)
    name = (wanted or wrong_name).group(1) if (wanted or wrong_name) else ""
    if name:
        known = name.rsplit(".", 1)[-1] in stems or _in_source(name, reference_src)
        if known:
            return "planned_code", ""
        return "missing_library", name.split(".")[0]
    # Some other error while the file loaded: planned code if its file is in the trace, else the
    # frozen test's own code.
    return ("planned_code" if in_planned else "frozen_test"), ""


# --- what the developer may see (N3): no server path, no secret ---

SANDBOX = "<sandbox>"
TAIL_LINES = 20
# A path: starts at a non-word character, so "and/or" is not one. Brackets and commas end it.
_PART = r"[^\s'\"<>:|*?()\[\]\\/,]"
_PATH = re.compile(rf"(?<![\w.])(?:[A-Za-z]:)?[\\/](?:{_PART}+[\\/])*{_PART}*")


def _swap_path(match: re.Match) -> str:
    parts = match.group(0).replace("\\", "/").split("/")
    named = [i for i, part in enumerate(parts) if part.startswith("da_sandbox_")]
    if named:
        rest = parts[named[0] + 1 :]
    elif "src" in parts:  # keep the tail from src on, so the file can still be found
        rest = parts[parts.index("src") :]
    else:
        rest = parts[-1:]
    rest = [part for part in rest if part]
    return f"{SANDBOX}/{'/'.join(rest)}" if rest else SANDBOX


def hide_sandbox(text: str) -> str:
    """Server paths become `<sandbox>/...` (the part from src on is kept) and a line that looks
    like a secret becomes [hidden] (the same patterns D1 uses, one line at a time)."""
    return "\n".join(hide_secret(_PATH.sub(_swap_path, line)) for line in text.split("\n"))


def clean_result(result: LayerBResult) -> None:
    """Hide paths and secrets in what Layer B saved, so nothing unsafe is stored or drawn."""
    error = result.load_error
    if error is not None:
        error.message = hide_sandbox(error.message)
        error.traceback_tail = [hide_sandbox(line) for line in error.traceback_tail][-TAIL_LINES:]
    for item in result.tests:
        item.message = hide_sandbox(item.message)
        item.traceback_tail = [hide_sandbox(line) for line in item.traceback_tail][-TAIL_LINES:]


def reason_lines(result: LayerBResult | None) -> list[str]:
    """The reason a run is not clean, as plain lines: a load error with the end of its trace,
    and every Not proven row with its message. Empty when there is nothing to explain."""
    if result is None:
        return []
    lines: list[str] = []
    error = result.load_error
    if error is not None:
        lines.append(f"The test file could not load. {error.error_type}: {error.message}".strip())
        lines += error.traceback_tail
    for item in result.tests:
        if item.result == "not_proven":
            lines.append(f"{item.name}: {item.message or 'Not proven: no result recorded'}")
            lines += item.traceback_tail
    return [hide_sandbox(line) for line in lines]


def _in_source(name: str, reference_src: Path) -> bool:
    top = name.split(".")[0]
    return (reference_src / top).is_dir() or (reference_src / f"{top}.py").is_file()


def load_failed_text(result: LayerBResult) -> str | None:
    """"0 of 6 ran: the test file could not load" for a load error, else None (count as usual)."""
    if result.load_error is None:
        return None
    return f"{result.ran_count} of {len(result.tests)} ran: the test file could not load"


def is_system_pause(result: LayerBResult | None) -> bool:
    """True when the run stops for a reason that is not the code's: tests that never reported
    (Not proven), or a load error whose fault is the server or a frozen test. No round is used
    and the AI is not called (F3)."""
    if result is None:
        return False
    if result.not_proven:
        return True
    return result.load_error is not None and result.load_error.fault in SYSTEM_FAULTS


def pause_text(result: LayerBResult) -> str:
    """The sentence for a system pause."""
    error = result.load_error
    if error is None or error.fault not in SYSTEM_FAULTS:
        return NOT_PROVEN_TEXT
    if error.fault == "missing_library":
        return MISSING_LIBRARY_TEXT.format(module=missing_module(error))
    return FROZEN_TEST_TEXT.format(message=_first_line(error.message))


def missing_module(error: LoadError) -> str:
    match = _MISSING.search(error.message) or _FROM.search(error.message)
    return match.group(1).split(".")[0] if match else "a library"


def _first_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[0][:200] if lines else "(no message)"
