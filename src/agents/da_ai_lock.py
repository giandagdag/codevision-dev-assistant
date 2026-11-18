"""One AI call at a time per request (B2 S5).

AS400 picture: a record lock. While a request waits on the AI, a second click (same window, a
second tab, or a reload) is refused with a plain message instead of racing the first one.

Kept in memory: enough for the one-process laptop and the current work setup. If CodeVision runs
several worker processes later, move it to a table (see specs/parked-items.md).
"""

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from db_table_functions.db_tbl_da_understand import UnderstandError

TIME_LIMIT = timedelta(minutes=10)  # a stuck entry clears itself after this
BUSY_MESSAGE = "The AI is still working on this request. Please wait a moment, then try again."

_held: dict[str, datetime] = {}
_guard = threading.Lock()


class AiBusyError(UnderstandError):
    """Shown as a plain message line, like the other screen errors."""


def try_start(request_id: str, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    with _guard:
        started = _held.get(request_id)
        if started is not None and now - started < TIME_LIMIT:
            return False
        _held[request_id] = now
        return True


def finish(request_id: str) -> None:
    with _guard:
        _held.pop(request_id, None)


def is_busy(request_id: str, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    with _guard:
        started = _held.get(request_id)
        return started is not None and now - started < TIME_LIMIT


@contextmanager
def ai_turn(request_id: str | None) -> Iterator[None]:
    """Hold the request for one action; released even when the AI call raises."""
    if not request_id:  # creating a request: nothing to lock yet
        yield
        return
    if not try_start(request_id):
        raise AiBusyError(BUSY_MESSAGE)
    try:
        yield
    finally:
        finish(request_id)


def locked_call(request_id: str | None, run: Callable, refused: Callable[[str], tuple]):
    """Run one screen action under the lock; a busy request returns `refused(message)`."""
    try:
        with ai_turn(request_id):
            return run()
    except AiBusyError as error:
        return refused(str(error))
