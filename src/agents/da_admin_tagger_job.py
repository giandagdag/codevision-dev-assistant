"""The AI scan as a background job (fix 11-2, AG-8). Same lock-file pattern as the index rebuild.

AS400 picture: a submitted batch job with an exclusive lock. One job at a time across rebuild and
scan; progress is a counter you can read ("120 of 340"). Never logs code, prompt or reply.
"""

import threading
from datetime import datetime
from pathlib import Path

from agents.da_admin_index import index_dir, read_health
from agents.da_admin_modules import module_paths
from agents.da_admin_rebuild import (
    LOCK_NAME,
    ONE_JOB_AT_A_TIME,
    TAGGER_LOCK_NAME,
    _lock_path,
    _take_lock,
    running_since,
    source_folder,
)
from agents.da_admin_tag_store import read_store
from agents.da_admin_tagger import ScriptedTaggerClient, paths_to_tag, run_tagging
from agents.da_llm_client import get_llm_client
from configs.da_config import Settings
from da_logging import get_logger
from pydantic_classes.da_rulebook_models import Policy

logger = get_logger(__name__)

PROGRESS = {"done": 0, "total": 0}  # one job at a time, so one counter is enough
LAST_MESSAGE = {"text": ""}  # the result line of the newest scan, shown next to the buttons


def scan_running(directory: Path | None = None) -> datetime | None:
    return running_since(directory=directory, name=TAGGER_LOCK_NAME)


def progress_text() -> str:
    return f"Scanning… {PROGRESS['done']} of {PROGRESS['total']}"


def status_line(directory: Path | None = None) -> str:
    """Running progress, else the newest result (empty before the first scan)."""
    return progress_text() if scan_running(directory) is not None else LAST_MESSAGE["text"]


def tags_out_of_date(directory: Path | None = None) -> bool:
    """True when the index was built after the last scan ("Tag new or changed" is worth a click)."""
    health = read_health(directory)
    runs = read_store(directory)["runs"]
    if not health.built or health.built_at is None or not runs:
        return False
    return health.built_at > datetime.fromisoformat(runs[0]["started_at"])


def pick_client(settings: Settings, policy: Policy):
    """Home (fake provider) answers from the script; work uses the tagger role's model."""
    if settings.llm_provider == "fake":
        return ScriptedTaggerClient()
    return get_llm_client("tagger", settings, policy.tagger_model)


def _run(policy, settings, started_by, only_changed, started, directory, client):
    out = directory or index_dir()
    try:
        root = source_folder(policy)
        paths = module_paths(policy.index_folder_scope, directory)
        todo, waiting = paths_to_tag(
            paths, read_store(directory), root, only_changed, settings.tagger_max_modules
        )
        PROGRESS.update(done=0, total=len(todo))

        def progress(done: int, total: int) -> None:
            PROGRESS.update(done=done, total=total)

        result = run_tagging(
            todo, root, policy.capabilities, client or pick_client(settings, policy), started_by,
            [e.pattern for e in policy.index_exclusions], directory, started, progress,
        )
        text = result.message
        if result.saved:
            text = f"Done: {result.scanned} scanned, {result.proposed} proposals."
        if waiting:
            text += f" {waiting} more wait for the next scan."
        LAST_MESSAGE["text"] = text
    except Exception as error:  # a failed job must still free the lock
        logger.warning("AI scan failed: %s", type(error).__name__)
        LAST_MESSAGE["text"] = f"The scan failed: {error}"
    finally:
        _lock_path(out, TAGGER_LOCK_NAME).unlink(missing_ok=True)


def start_scan(
    policy: Policy,
    settings: Settings,
    started_by: str,
    only_changed: bool = False,
    now: datetime | None = None,
    directory: Path | None = None,
    client=None,
    wait: bool = False,
) -> tuple[bool, str]:
    """Start one background scan. Returns (started, message). `client` and `wait` are for tests."""
    started = now or datetime.now()
    if running_since(started, directory, LOCK_NAME) is not None or scan_running(directory):
        return False, ONE_JOB_AT_A_TIME
    if not _take_lock(started, directory, TAGGER_LOCK_NAME):
        return False, ONE_JOB_AT_A_TIME
    PROGRESS.update(done=0, total=0)
    job = threading.Thread(
        target=_run,
        args=(policy, settings, started_by, only_changed, started, directory, client),
        daemon=True,
    )
    job.start()
    if wait:
        job.join()
    return True, f"Scanning… started {started:%H:%M}"
