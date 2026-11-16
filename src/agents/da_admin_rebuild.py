"""Rebuild index from Admin (fix 11-1, AF-7 and AF-8; closes parked item P23). Plain code, no AI.

AS400 picture: a submitted batch job. One job at a time (a lock file, like a *EXCL object lock),
it runs in the background and writes one line to the job log (da_code_index_runs.json).
"""

import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path

from agents.da_admin_index import index_dir, record_run
from agents.da_code_index import Embedder, FakeEmbedder, WorkEmbedder
from da_build_code_index import build_index
from da_logging import get_logger
from pydantic_classes.da_rulebook_models import Policy

logger = get_logger(__name__)

LOCK_NAME = "da_code_index.lock"
TAGGER_LOCK_NAME = "da_tagger.lock"
LOCK_MAX_AGE = timedelta(hours=2)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_FOLDER = Path(__file__).resolve().parents[1]  # B1's default source when nothing is set
SERVER_STARTED = datetime.now()  # a lock from before this moment belongs to a dead server
ALREADY_RUNNING = "A rebuild is already running. Wait for it to finish."
ONE_JOB_AT_A_TIME = "One job at a time: wait for the other one to finish."


def source_folder(policy: Policy) -> Path:
    """Folder scope first, then B1's DA_CODE_INDEX_SOURCE, then B1's default."""
    scope = policy.index_folder_scope.strip()
    if scope:
        return Path(scope) if Path(scope).is_absolute() else PROJECT_ROOT / scope
    return Path(os.environ.get("DA_CODE_INDEX_SOURCE") or SRC_FOLDER)


def pick_embedder(provider: str) -> Embedder:
    """Work gets the real embedder, anything else the made-up one (never a fake index at work).

    The provider comes from the settings (they read .env), not from os.environ: .env values never
    reach os.environ, so reading it here would pick the made-up embedder at work."""
    return WorkEmbedder() if provider == "onprem" else FakeEmbedder()


def _lock_path(directory: Path | None, name: str = LOCK_NAME) -> Path:
    return (directory or index_dir()) / name


def running_since(
    now: datetime | None = None, directory: Path | None = None, name: str = LOCK_NAME
) -> datetime | None:
    """Start time of the running job, or None. A stale or unreadable lock is cleared."""
    path = _lock_path(directory, name)
    try:
        started = datetime.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["started"])
    except OSError:
        return None
    except ValueError, KeyError, TypeError:
        path.unlink(missing_ok=True)
        return None
    if started < SERVER_STARTED or (now or datetime.now()) - started > LOCK_MAX_AGE:
        path.unlink(missing_ok=True)
        return None
    return started


def _take_lock(started: datetime, directory: Path | None, name: str = LOCK_NAME) -> bool:
    path = _lock_path(directory, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as lock:  # "x" fails if it exists: one winner
            lock.write(json.dumps({"started": started.isoformat(timespec="seconds")}))
    except FileExistsError:
        return False
    return True


def _run(
    policy: Policy,
    started_by: str,
    started: datetime,
    embedder: Embedder | None,
    directory: Path | None,
    provider: str,
) -> None:
    out = directory or index_dir()
    try:
        summary = build_index(
            source_folder(policy),
            out,
            embedder or pick_embedder(provider),
            say=lambda _text: None,
            extra_exclusions=[e.pattern for e in policy.index_exclusions],
        )
        record_run(
            started_by, started, summary.saved, summary.count, summary.skipped,
            summary.message, out,
        )
    except Exception as error:  # a failed job must still free the lock and leave a log line
        logger.warning("Index rebuild failed: %s", type(error).__name__)
        record_run(started_by, started, False, 0, [], f"Rebuild failed: {error}", out)
    finally:
        _lock_path(out).unlink(missing_ok=True)


def start_rebuild(
    policy: Policy,
    started_by: str,
    now: datetime | None = None,
    embedder: Embedder | None = None,
    directory: Path | None = None,
    wait: bool = False,
    provider: str = "",
) -> tuple[bool, str]:
    """Start one background build. Returns (started, message). `wait` is for tests only.

    `provider` is the settings' llm_provider; empty (the default) means the made-up embedder."""
    started = now or datetime.now()
    if running_since(started, directory, TAGGER_LOCK_NAME) is not None:
        return False, ONE_JOB_AT_A_TIME
    if running_since(started, directory) is not None or not _take_lock(started, directory):
        return False, ALREADY_RUNNING
    job = threading.Thread(
        target=_run, args=(policy, started_by, started, embedder, directory, provider), daemon=True
    )
    job.start()
    if wait:
        job.join()
    return True, f"Rebuilding… started {started:%H:%M}"
