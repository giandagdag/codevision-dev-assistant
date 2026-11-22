"""Index job status and Stop (fix 11-3, D-G; AH-7). Plain code, no AI.

AS400 picture: the job's status record (like WRKACTJOB) is a small JSON file next to the index. The
page can be closed and reopened, or another server process can look: both read the same file.
Stop is a second small file ("a request to end the job"), checked between pieces.
Nothing here holds code text.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from agents.da_admin_index import index_dir

STATUS_NAME = "da_index_job.json"
STOP_NAME = "da_index_job.stop"
STALE_AFTER = timedelta(minutes=30)  # a live job writes a heartbeat before and after every item
SHOW_TIME_LEFT_AFTER = 20  # items; the speed is only believable after a few
STEP_LABELS = {1: "reading the code", 2: "reading code links", 3: "tagging programs"}
STEP_NOUNS = {1: "pieces", 2: "files", 3: "programs"}
TOTAL_STEPS = 3


def _path(directory: Path | None, name: str) -> Path:
    return (directory or index_dir()) / name


def read_status(directory: Path | None = None) -> dict:
    """The newest job status, or an empty dict. A damaged file is treated as no status."""
    try:
        status = json.loads(_path(directory, STATUS_NAME).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return status if isinstance(status, dict) else {}


def _write(directory: Path | None, status: dict) -> None:
    path = _path(directory, STATUS_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, indent=1), encoding="utf-8")


def _stamp(now: datetime | None) -> str:
    return (now or datetime.now()).isoformat(timespec="seconds")


def begin(
    directory: Path | None, started: datetime, who: str, mode: str, trigger: str, build: int = 0
) -> None:
    clear_stop(directory)
    _write(directory, {
        "started": _stamp(started), "started_by": who, "mode": mode, "trigger": trigger,
        "build": build,
        "step": 1, "done": 0, "total": 0, "step_started": _stamp(started),
        "updated": _stamp(None), "error": "",
    })


def progress(
    directory: Path | None, done: int, total: int, step: int = 1, now: datetime | None = None
) -> None:
    """Heartbeat plus the counters. A new step restarts the clock used for "time left"."""
    status = read_status(directory)
    if not status:
        return
    if status.get("step") != step:
        status["step_started"] = _stamp(now)
    status.update(step=step, done=done, total=total, updated=_stamp(now))
    _write(directory, status)


def fail(directory: Path | None, message: str) -> None:
    status = read_status(directory)
    status.update(error=message, updated=_stamp(None))
    _write(directory, status)


def set_end_line(directory: Path | None, text: str) -> None:
    """Fix G5 N4: the sentence a finished job leaves behind ("Re-check done: ...")."""
    status = read_status(directory)
    status["end_line"] = text
    _write(directory, status)


def last_heartbeat(directory: Path | None, started: datetime) -> datetime:
    """When the job last showed life. Falls back to its start when there is no status file."""
    status = read_status(directory)
    try:
        if status.get("started") == _stamp(started):  # only this job's own status counts
            return max(started, datetime.fromisoformat(status["updated"]))
    except KeyError, ValueError:
        pass
    return started


def request_stop(directory: Path | None = None) -> None:
    path = _path(directory, STOP_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("stop", encoding="utf-8")


def stop_requested(directory: Path | None = None) -> bool:
    return _path(directory, STOP_NAME).exists()


def clear_stop(directory: Path | None = None) -> None:
    _path(directory, STOP_NAME).unlink(missing_ok=True)


def percent(status: dict) -> int:
    total = int(status.get("total") or 0)
    return min(100, int(status.get("done", 0) * 100 / total)) if total else 0


def time_left(status: dict, now: datetime | None = None) -> timedelta | None:
    """Estimate from the measured speed of the current step; None until 20 items are done."""
    done, total = int(status.get("done") or 0), int(status.get("total") or 0)
    if done < SHOW_TIME_LEFT_AFTER or total <= done:
        return None
    elapsed = (now or datetime.now()) - datetime.fromisoformat(status["step_started"])
    return elapsed / done * (total - done)


def _duration_text(span: timedelta) -> str:
    minutes = max(1, round(span.total_seconds() / 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min" if hours else f"{minutes} min"


BAR_STEP_NAMES = {1: "Reading code", 2: "Linking code", 3: "Tagging programs"}


def set_step_name(directory: Path | None, name: str, step: int) -> None:
    """Fix G6: a job with its own step names (Suggest capabilities) says which one is running."""
    status = read_status(directory)
    status.update(step=step, step_name=name, done=0, total=0, updated=_stamp(None))
    _write(directory, status)


def step_title(status: dict) -> str:
    """Fix G5 N2: the bar's heading. A re-check is step 3 work under its own name."""
    if status.get("mode") == "suggest":
        return str(status.get("step_name", ""))
    if status.get("mode") == "recheck":
        return "Re-checking programs"
    return BAR_STEP_NAMES.get(int(status.get("step") or 1), "")


def progress_line(status: dict, now: datetime | None = None) -> str:
    """"Build 7. Step 1 of 3: reading the code, 340 of 1,200 pieces (28%)" plus "About 2 h left"."""
    step = int(status.get("step") or 1)
    if status.get("mode") == "suggest":
        return f"Step {step} of 3: {str(status.get('step_name', '')).lower()}"
    build = f"Build {status['build']}. " if status.get("build") else ""
    line = (
        f"{build}Step {step} of {TOTAL_STEPS}: {STEP_LABELS.get(step, '')}, "
        f"{status.get('done', 0):,} of {status.get('total', 0):,} {STEP_NOUNS.get(step, '')} "
        f"({percent(status)}%)"
    )
    left = time_left(status, now)
    return line if left is None else f"{line}. About {_duration_text(left)} left"
