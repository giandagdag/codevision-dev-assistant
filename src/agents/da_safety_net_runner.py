"""Runs the safety net write in the background (Phase 9, step 18b).

Writing and proving the net takes a minute or more (one AI call, a sandbox run, fix calls), so the
click must not wait for it. Like `da_build_runner`, the thread only calls the engine; the DATABASE
is the truth. If the server stops while it runs, `recover_interrupted_safety_nets` turns the step
into `s_unable` at the next start and Try again runs it from the start. AS400 picture: a SBMJOB
that the 5250 screen does not wait for.
"""

import threading

from agents import da_safety_net_flow as net_flow
from configs.da_config import Settings
from da_logging import get_logger

logger = get_logger(__name__)

_threads: dict[str, threading.Thread] = {}
_lock = threading.Lock()


def submit_safety_net(
    settings: Settings, request_id: str, base_revision: int, **engine_options
) -> threading.Thread:
    """Start the write for this request on a thread. A request whose write is already running
    gets the existing thread back (one write at a time, F2). `engine_options` (runner, client)
    are for tests only."""
    with _lock:
        existing = _threads.get(request_id)
        if existing is not None and existing.is_alive():
            return existing
        thread = threading.Thread(
            target=_work,
            args=(settings, request_id, base_revision, engine_options),
            name=f"da-net-{request_id}",
            daemon=True,  # a server shutdown must not wait for it
        )
        _threads[request_id] = thread
    thread.start()
    return thread


def _work(settings: Settings, request_id: str, base_revision: int, engine_options: dict) -> None:
    try:
        net_flow.run_safety_net(settings, request_id, base_revision, **engine_options)
    except Exception:  # noqa: BLE001 - a thread must never die without a log line
        # Nothing was saved by a half-done run; the step stays as it was, so the screen offers
        # Try again (s_unable) or the next server start moves s_writing to s_unable.
        logger.exception("The background safety net of %s stopped on an error.", request_id)
