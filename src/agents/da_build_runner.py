"""Runs builds in the background (spec section 10, decision D-D).

Each build is a thread inside the server. The thread only runs da_build_loop.run_build; the
DATABASE is the truth about the build, not the thread, so a restart loses nothing but time.

At most `build_max_parallel` builds run at once on this server (the AI is shared). The others
wait their turn, first in first out, and say so in the progress list. Like a job queue with a
maximum number of active jobs: the rest sit in the queue as JOBQ entries until a slot is free.
(The count is per running copy of the server. If CodeVision runs as several copies on OCP, the
limit is per copy: open question Q14 (e), plan item P9.)
"""

import threading
from collections.abc import Callable
from datetime import UTC, datetime

from agents import da_build_loop as loop
from agents.da_build_flow import (
    RUNNING_STEPS,
    SERVER_RESTART_MESSAGE,
    BuildTx,
    _require_request,
    _write,
)
from configs.da_config import Settings
from da_logging import get_logger
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import (
    add_progress,
    ensure_build_tables,
    read_build_state,
    read_progress,
    read_running_requests,
    save_build_state,
)
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request
from pydantic_classes.da_build_models import ProgressLine

logger = get_logger(__name__)

WAIT_SECONDS = 1.0

_condition = threading.Condition()
_active: set[str] = set()
_waiting: list[str] = []
_threads: dict[str, threading.Thread] = {}


def waiting_text(ahead: int) -> str:
    return f"Waiting for a free slot ({ahead} ahead of you)."


def submit_build(
    settings: Settings,
    request_id: str,
    client_factory: Callable[[Settings, str], object] | None = None,
) -> threading.Thread:
    """Run the request's running build on a background thread. Submitting a request that
    already has a live thread does nothing (one build at a time per request, rule B4)."""
    with _condition:
        existing = _threads.get(request_id)
        if existing is not None and existing.is_alive():
            return existing
        thread = threading.Thread(
            target=_work,
            args=(settings, request_id, client_factory),
            name=f"da-build-{request_id}",
            daemon=True,  # a server shutdown must not wait for a build
        )
        _threads[request_id] = thread
        _waiting.append(request_id)
    thread.start()
    return thread


def active_count() -> int:
    with _condition:
        return len(_active)


def _work(settings: Settings, request_id: str, client_factory) -> None:
    try:
        if _wait_for_slot(settings, request_id):
            try:
                loop.run_build(settings, request_id, client_factory)
            finally:
                with _condition:
                    _active.discard(request_id)
                    _condition.notify_all()
    except Exception:  # noqa: BLE001 - a thread must never die without a log line
        logger.exception("The background build of %s stopped on an error.", request_id)
        with _condition:
            _active.discard(request_id)
            if request_id in _waiting:
                _waiting.remove(request_id)
            _condition.notify_all()


def _wait_for_slot(settings: Settings, request_id: str) -> bool:
    """Wait first in first out for a free slot. False if the build was stopped while waiting."""
    limit = get_rulebook_for_request(
        settings.db_path, request_id
    ).rulebook.policy.build_max_parallel
    announced = -1
    while True:
        with _condition:
            if _waiting and _waiting[0] == request_id and len(_active) < limit:
                _waiting.remove(request_id)
                _active.add(request_id)
                return True
            position = _waiting.index(request_id)
            ahead = max(0, len(_active) + position - limit + 1)
            if ahead == announced:
                _condition.wait(timeout=WAIT_SECONDS)
        if not _still_running(settings, request_id):
            _leave_queue(request_id)
            return False
        if ahead != announced:
            announced = ahead
            _note_waiting(settings, request_id, ahead)


def _leave_queue(request_id: str) -> None:
    with _condition:
        if request_id in _waiting:
            _waiting.remove(request_id)
        _condition.notify_all()


def _still_running(settings: Settings, request_id: str) -> bool:
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        state = read_build_state(conn, request_id)
    return state is not None and state.step in RUNNING_STEPS


def _note_waiting(settings: Settings, request_id: str, ahead: int) -> None:
    """Tell the progress list the build is queued. Nobody ahead means a slot is free right now
    and the build takes it, so there is nothing to say."""
    if ahead == 0:
        return
    with _write(settings.db_path) as conn:
        state = read_build_state(conn, request_id)
        if state is None or state.step not in RUNNING_STEPS:
            return
        progress = read_progress(conn, request_id, state.build_number)
        number = (progress[-1].line_number + 1) if progress else 1
        add_progress(
            conn,
            ProgressLine(
                request_id=request_id,
                build_number=state.build_number,
                line_number=number,
                text=waiting_text(ahead),
                state="pending",
                started_at=datetime.now(UTC),
            ),
        )


def recover_interrupted_builds(settings: Settings, now: datetime | None = None) -> list[str]:
    """At server start-up no build can really be running, so any build still marked running was
    cut off. Mark it `b_interrupted` with the restart message; Try again resumes it from the last
    saved step (spec section 10, row 6-27). Returns the requests that were fixed."""
    now = now or datetime.now(UTC)
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        stuck = read_running_requests(conn)
    fixed = []
    for request_id in stuck:
        with _write(settings.db_path) as conn:
            state = read_build_state(conn, request_id)
            if state is None or state.step not in RUNNING_STEPS:
                continue
            tx = BuildTx(conn, _require_request(conn, request_id), state, now)
            tx.audit(
                "system", "build_interrupted", {"why": SERVER_RESTART_MESSAGE, "kind": "restart"}
            )
            tx.say("assistant", f"The build paused: {SERVER_RESTART_MESSAGE}")
            tx.set(step="b_interrupted", message=SERVER_RESTART_MESSAGE)
            save_build_state(conn, tx.state, state.revision, now)
            fixed.append(request_id)
    return fixed
