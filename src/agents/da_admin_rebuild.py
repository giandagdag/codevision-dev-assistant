"""Rebuild index from Admin (fix 11-1, AF-7 and AF-8; closes parked item P23). Plain code, no AI.

AS400 picture: a submitted batch job. One job at a time (a lock file, like a *EXCL object lock),
it runs in the background and writes one line to the job log (da_code_index_runs.json).
"""

import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path

from agents import da_admin_job as job
from agents.da_admin_index import index_dir, record_run
from agents.da_code_index import Embedder, FakeEmbedder, WorkEmbedder
from configs.da_config import load_settings
from da_build_code_index import build_index
from da_logging import get_logger
from pydantic_classes.da_rulebook_models import Policy

logger = get_logger(__name__)

LOCK_NAME = "da_code_index.lock"
TAGGER_LOCK_NAME = "da_tagger.lock"
TAGGER_LOCK_MAX_AGE = timedelta(hours=12)  # 500 modules on a slow model take hours
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_FOLDER = Path(__file__).resolve().parents[1]  # B1's default source when nothing is set
SERVER_STARTED = datetime.now()  # a lock from before this moment belongs to a dead server
ALREADY_RUNNING = "A rebuild is already running. Wait for it to finish."
ONE_JOB_AT_A_TIME = "One job at a time: wait for the other one to finish."
MADE_UP_SCOPE_REFUSED = "The made-up practice folder cannot be used at work"


def source_folder(policy: Policy, provider: str = "") -> Path:
    """Folder scope first, then (at work) DA_CODEVISION_SRC, then B1's DA_CODE_INDEX_SOURCE and
    B1's default."""
    scope = policy.index_folder_scope.strip()
    if scope:
        return Path(scope) if Path(scope).is_absolute() else PROJECT_ROOT / scope
    if provider == "onprem" and (work_src := load_settings().codevision_src):
        return Path(work_src)
    return Path(os.environ.get("DA_CODE_INDEX_SOURCE") or SRC_FOLDER)


def scope_refusal(policy: Policy, provider: str) -> str:
    """At work the made-up practice folder must never be indexed (G7); "" means fine."""
    if provider == "onprem" and "da_fake_codevision" in Path(policy.index_folder_scope).parts:
        return MADE_UP_SCOPE_REFUSED
    return ""


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
    current = now or datetime.now()
    if name == LOCK_NAME:
        # The index job writes a heartbeat; a job with no sign of life for 30 min is dead. A long
        # job (hours) and a job started by another server process both stay locked while alive.
        stale = current - job.last_heartbeat(directory, started) > job.STALE_AFTER
    else:
        stale = started < SERVER_STARTED or current - started > TAGGER_LOCK_MAX_AGE
    if stale:
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
    mode: str = "full",
    trigger: str = "Manual",
) -> None:
    out = directory or index_dir()
    embedder = embedder or pick_embedder(provider)
    job.begin(out, started, started_by, mode, trigger)
    extra = {"mode": mode, "trigger": trigger}
    try:
        summary = build_index(
            source_folder(policy, provider),
            out,
            embedder,
            say=lambda _text: None,
            extra_exclusions=[e.pattern for e in policy.index_exclusions],
            mode=mode,
            progress=lambda done, total: job.progress(out, done, total),
            stop=lambda: job.stop_requested(out),
        )
        extra.update(mode=summary.mode, reread=summary.reread)
        record_run(
            started_by, started, summary.saved, summary.count, summary.skipped,
            summary.message, out, _with_seconds(extra, started),
        )
        if not summary.saved:
            job.fail(out, summary.message)
    except Exception as error:  # a failed job must still free the lock and leave a log line
        logger.warning("Index rebuild failed: %s", type(error).__name__)
        message = f"Rebuild failed: {error}"
        record_run(started_by, started, False, 0, [], message, out, _with_seconds(extra, started))
        job.fail(out, message)
    finally:
        if isinstance(embedder, WorkEmbedder):
            embedder.close()  # ends the helper process
        job.clear_stop(out)
        _lock_path(out).unlink(missing_ok=True)


def _with_seconds(extra: dict, started: datetime) -> dict:
    return {**extra, "seconds": int((datetime.now() - started).total_seconds())}


def start_rebuild(
    policy: Policy,
    started_by: str,
    now: datetime | None = None,
    embedder: Embedder | None = None,
    directory: Path | None = None,
    wait: bool = False,
    provider: str = "",
    mode: str = "full",
    trigger: str = "Manual",
) -> tuple[bool, str]:
    """Start one background build. Returns (started, message). `wait` is for tests only.

    `provider` is the settings' llm_provider; empty (the default) means the made-up embedder.
    `mode` is "full" or "delta" (Delta runs full when the saved index cannot be trusted)."""
    started = now or datetime.now()
    if refusal := scope_refusal(policy, provider):
        return False, refusal
    if running_since(started, directory, TAGGER_LOCK_NAME) is not None:
        return False, ONE_JOB_AT_A_TIME
    if running_since(started, directory) is not None or not _take_lock(started, directory):
        return False, ALREADY_RUNNING
    args = (policy, started_by, started, embedder, directory, provider, mode, trigger)
    thread = threading.Thread(target=_run, args=args, daemon=True)
    thread.start()
    if wait:
        thread.join()
    return True, f"Rebuilding… started {started:%H:%M}"
