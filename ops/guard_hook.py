"""PreToolUse hook: before each tool call a WORKER makes, check the usage guard.

Only acts when DA_WORKER=1 (set by the chief's launcher). In Gian's own sessions, in this cloud
build and in the reviewers it does nothing, so the guard can never lock people out (X11).

When the answer is STOP the hook blocks (exit 2) every tool except one write: the worker's note
`ops/state/worker_note.md` (X12). The block message tells the worker to write it and stop.
Inside a worker any error blocks (fails closed).
"""

import json
import os
import sys
from pathlib import Path

import usage_guard

NOTE_NAME = "worker_note.md"
BLOCK_TEXT = (
    "Usage line reached ({reason}). Write your state to ops/state/worker_note.md, then stop."
)


def note_path() -> Path:
    return (usage_guard.state_path().parent / NOTE_NAME).resolve()


def _is_note_write(payload: dict) -> bool:
    if payload.get("tool_name") not in ("Write", "Edit"):
        return False
    given = (payload.get("tool_input") or {}).get("file_path")
    if not given:
        return False
    base = Path(payload.get("cwd") or ".")
    return (base / given).resolve() == note_path()


def check(payload: dict, reader: usage_guard.Reader = usage_guard.endpoint_reader) -> str | None:
    """Return None to allow, or the block message."""
    if os.environ.get("DA_WORKER") != "1":
        return None
    decision = usage_guard.decide(usage_guard.get_usage(reader))
    if decision.go or _is_note_write(payload):
        return None
    return BLOCK_TEXT.format(reason=decision.reason)


def main(stdin=None, reader: usage_guard.Reader = usage_guard.endpoint_reader) -> int:
    try:
        payload = json.load(stdin or sys.stdin)
        message = check(payload, reader)
    except Exception:  # noqa: BLE001 - fail closed inside a worker, stay silent outside
        if os.environ.get("DA_WORKER") != "1":
            return 0
        message = BLOCK_TEXT.format(reason="guard blind: the guard hook failed")
    if message:
        print(message, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
