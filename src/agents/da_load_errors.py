"""Fix NP: whose fault is a test file that cannot load? Decided once, from the error itself.

Like reading the message in a failed CALL: "object not found in library list" is the system
administrator's job; "program ended with a wrong parameter" is the programmer's. Plain code, no AI.
"""

import re
from pathlib import Path

from agents.da_check_words import FROZEN_TEST_TEXT, MISSING_LIBRARY_TEXT, NOT_PROVEN_TEXT
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
    if error.kind != "import":
        return "frozen_test", ""
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
    trace = "\n".join(error.traceback_tail).replace("\\", "/")
    if any(path in trace for path in planned):
        return "planned_code", ""
    return "frozen_test", ""


def _in_source(name: str, reference_src: Path) -> bool:
    top = name.split(".")[0]
    return (reference_src / top).is_dir() or (reference_src / f"{top}.py").is_file()


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
