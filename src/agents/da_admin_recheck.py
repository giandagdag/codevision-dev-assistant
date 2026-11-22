"""Re-check the "No capability fits" programs after a new capability (Fix G4, S6).

AS400 picture: resubmit only the rejected lines of a batch after the code table changed. Same job
lock as the index job, so one job runs at a time. The AI proposes; Admin still approves.
"""

import threading
from datetime import datetime
from pathlib import Path

from agents import da_admin_job as job
from agents.da_admin_index import index_dir
from agents.da_admin_rebuild import (
    ALREADY_RUNNING,
    _lock_path,
    _take_lock,
    running_since,
    source_folder,
)
from agents.da_admin_tag_store import read_store
from agents.da_admin_tagger import STATE_PROPOSED, STATE_UNREADABLE, run_tagging
from agents.da_admin_tagger_job import pick_client
from configs.da_config import Settings
from da_logging import get_logger
from pydantic_classes.da_rulebook_models import Policy

logger = get_logger(__name__)


def recheck_paths(directory: Path | None = None) -> list[str]:
    """Open proposals with no fit and no new-capability suggestion (the `none` ones), and the
    programs the AI could not read (Fix G5 R8)."""
    modules = read_store(directory)["modules"]
    return sorted(
        path for path, e in modules.items()
        if isinstance(e, dict) and (e.get("state") == STATE_UNREADABLE or (
            e.get("state") == STATE_PROPOSED
            and not e.get("proposed_capability") and not e.get("new_name")))
    )


def end_line(paths: list[str], directory: Path | None = None) -> str:
    """"Re-check done: 18 programs placed, 23 still with no fit, 0 could not be read." (N4)"""
    modules = read_store(directory)["modules"]
    entries = [e for e in (modules.get(p) for p in paths) if isinstance(e, dict)]
    unreadable = sum(e.get("state") == STATE_UNREADABLE for e in entries)
    placed = sum(
        e.get("state") == STATE_PROPOSED and bool(e.get("proposed_capability") or e.get("new_name"))
        for e in entries
    )
    no_fit = len(entries) - unreadable - placed
    return (
        f"Re-check done: {placed} programs placed, {no_fit} still with no fit, "
        f"{unreadable} could not be read."
    )


def _run(policy, settings, started_by, started, directory, client, paths) -> None:
    out = directory or index_dir()
    job.begin(out, started, started_by, "recheck", "Manual")
    try:
        run_tagging(
            paths, source_folder(policy, settings.llm_provider, settings), policy.capabilities,
            client or pick_client(settings, policy), started_by,
            [e.pattern for e in policy.index_exclusions], out, None,
            lambda done, total: job.progress(out, done, total, step=3),
            stop=lambda: job.stop_requested(out),
        )
        job.set_end_line(out, end_line(paths, out))
    except Exception as error:  # a crash must free the lock and leave the old tags as they were
        logger.warning("Re-check failed: %s", type(error).__name__)
        job.fail(out, f"Re-check failed: {error}")
    finally:
        job.clear_stop(out)
        _lock_path(out).unlink(missing_ok=True)


def start_recheck(
    policy: Policy, settings: Settings, started_by: str, now: datetime | None = None,
    directory: Path | None = None, wait: bool = False, client=None,
) -> tuple[bool, str]:
    """Start the re-check in the background. Returns (started, message)."""
    started = now or datetime.now()
    paths = recheck_paths(directory)
    if not paths:
        return False, "No programs wait with 'No capability fits'."
    if running_since(started, directory) is not None or not _take_lock(started, directory):
        return False, ALREADY_RUNNING
    args = (policy, settings, started_by, started, directory, client, paths)
    thread = threading.Thread(target=_run, args=args, daemon=True)
    thread.start()
    if wait:
        thread.join()
    return True, f"Re-checking {len(paths)} programs."
