"""Rebuild index from Admin (fix 11-1, AF-7 and AF-8; closes parked item P23). Plain code, no AI.

AS400 picture: a submitted batch job. One job at a time (a lock file, like a *EXCL object lock),
it runs in the background and writes one line to the job log (da_code_index_runs.json).
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path

from agents import da_admin_job as job
from agents.da_admin_index import index_dir, record_run
from agents.da_code_clusters import write_suggestions
from agents.da_code_graph import load_graph
from agents.da_code_index import Embedder, FakeEmbedder, WorkEmbedder
from agents.da_index_builds import next_build_number, save_build
from configs.da_config import Settings, load_settings
from da_build_code_index import build_index
from da_logging import get_logger
from pydantic_classes.da_rulebook_models import Policy

logger = get_logger(__name__)

LOCK_NAME = "da_code_index.lock"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_FOLDER = Path(__file__).resolve().parents[1]  # B1's default source when nothing is set
SERVER_STARTED = datetime.now()  # when this server process started (tests age locks from it)
ALREADY_RUNNING = "A rebuild is already running. Wait for it to finish."
ONE_JOB_AT_A_TIME = "One job at a time: wait for the other one to finish."
MADE_UP_SCOPE_REFUSED = (
    "The made-up practice folder cannot be used at work. "
    "Clear Folder scope on Repository and index to use DA_CODEVISION_SRC."
)


def source_folder(policy: Policy, provider: str = "", settings: Settings | None = None) -> Path:
    """Folder scope first, then (at work) DA_CODEVISION_SRC, then B1's DA_CODE_INDEX_SOURCE and
    B1's default. The passed settings win over a fresh read of .env."""
    scope = policy.index_folder_scope.strip()
    if scope:
        return Path(scope) if Path(scope).is_absolute() else PROJECT_ROOT / scope
    if provider == "onprem" and (work_src := (settings or load_settings()).codevision_src):
        return Path(work_src)
    return Path(os.environ.get("DA_CODE_INDEX_SOURCE") or SRC_FOLDER)


def scope_refusal(policy: Policy, provider: str) -> str:
    """At work the made-up practice folder must never be indexed (G7); "" means fine."""
    if provider == "onprem" and "da_fake_codevision" in Path(policy.index_folder_scope).parts:
        return MADE_UP_SCOPE_REFUSED
    return ""


def pick_embedder(provider: str, settings: Settings | None = None) -> Embedder:
    """Work gets the real embedder, anything else the made-up one (never a fake index at work).

    The provider comes from the settings (they read .env), not from os.environ: .env values never
    reach os.environ, so reading it here would pick the made-up embedder at work."""
    if provider != "onprem":
        return FakeEmbedder()
    if settings is None:
        return WorkEmbedder()
    return WorkEmbedder(settings.codevision_src, settings.codevision_python)


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
    # The job (index and tagging) writes a heartbeat; no sign of life for 30 min means it is dead.
    # A long job (hours) and a job started by another server process both stay locked while alive.
    if current - job.last_heartbeat(directory, started) > job.STALE_AFTER:
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
    settings: Settings | None = None,
    tag_client=None,
) -> None:
    out = directory or index_dir()
    embedder = embedder or pick_embedder(provider, settings)
    number = next_build_number(out)
    job.begin(out, started, started_by, mode, trigger, number)
    extra = {"mode": mode, "trigger": trigger}
    try:
        summary = build_index(
            source_folder(policy, provider, settings),
            out,
            embedder,
            say=lambda _text: None,
            extra_exclusions=[e.pattern for e in policy.index_exclusions],
            mode=mode,
            progress=lambda done, total: job.progress(out, done, total),
            stop=lambda: job.stop_requested(out),
            build=number,
            graph_progress=lambda done, total: job.progress(out, done, total, step=2),
        )
        extra.update(mode=summary.mode, reread=summary.reread)
        message = summary.message
        message += _save_build_copy(summary, out, number, started_by, started, extra)
        if summary.saved and (settings is not None or tag_client is not None):
            message += _tag_step(
                policy, settings, started_by, summary, out, tag_client, extra, provider
            )
        if summary.saved:
            message += _cluster_step(out, policy.capabilities)
        record_run(
            started_by, started, summary.saved, summary.count, summary.skipped,
            message, out, _with_seconds(extra, started),
        )
        if not summary.saved and not summary.message.startswith("Stopped."):
            job.fail(out, summary.message)  # a Stop the user asked for is not a failure
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


def _save_build_copy(summary, out, number, started_by, started, extra) -> str:
    """Number the saved build and keep its copy. Never undoes the saved index; returns words."""
    if not summary.saved:
        return ""
    words = ""
    if summary.link_skipped:
        extra["link_skipped"] = summary.link_skipped
        words = f" {len(summary.link_skipped)} files had no code links read."
    try:
        saved = save_build(out, number, summary.mode, started_by, started)["build"]
    except (OSError, ValueError, KeyError) as error:
        logger.warning("Build copy failed: %s", type(error).__name__)
        return words + " The build copy was not saved."
    extra["build"] = saved
    if saved != number:
        words += f" Build {number} was already saved, so this is build {saved}."
    return words


def _tag_step(policy, settings, started_by, summary, out, tag_client, extra, provider) -> str:
    """Step 2: tag the programs. Never undoes the saved index; returns words for the run row."""
    from agents.da_admin_tagger_job import TAGS_NOT_SAVED, tag_programs  # AI use stays in that file

    try:
        result = tag_programs(
            policy, settings, started_by, summary.mode,
            source_folder(policy, provider, settings), out, tag_client,
        )
    except Exception as error:  # a tagging crash must not hide the saved index
        logger.warning("Tagging failed: %s", type(error).__name__)
        return f" {TAGS_NOT_SAVED}"
    extra["tagged"] = result.scanned if result.saved else 0
    if result.saved:
        return f" Tagged {result.scanned} programs."
    return f" {result.message}" if result.message.startswith("Stopped") else f" {TAGS_NOT_SAVED}"


def _cluster_step(out: Path, capabilities=()) -> str:
    """Refresh the capability suggestion cards from the saved graph. Never undoes the index."""
    graph = load_graph(out)
    if graph is None:
        return ""
    try:
        cards = write_suggestions(graph, out, capabilities)
    except (OSError, ValueError, KeyError) as error:
        logger.warning("Cluster suggestions failed: %s", type(error).__name__)
        return ""
    return f" {cards} capability suggestions from code links." if cards else ""


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
    settings: Settings | None = None,
    tag_client=None,
) -> tuple[bool, str]:
    """Start one background build. Returns (started, message). `wait` is for tests only.

    `provider` is the settings' llm_provider; empty (the default) means the made-up embedder.
    `mode` is "full" or "delta" (Delta runs full when the saved index cannot be trusted)."""
    started = now or datetime.now()
    if refusal := scope_refusal(policy, provider):
        return False, refusal
    if running_since(started, directory) is not None or not _take_lock(started, directory):
        return False, ALREADY_RUNNING
    args = (
        policy, started_by, started, embedder, directory, provider, mode, trigger, settings,
        tag_client,
    )
    thread = threading.Thread(target=_run, args=args, daemon=True)
    thread.start()
    if wait:
        thread.join()
    return True, f"Rebuilding… started {started:%H:%M}"
