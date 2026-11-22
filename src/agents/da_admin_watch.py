"""Fix G5 N1: one job watcher for the whole Admin page. Plain code, no AI.

AS400 picture: a data-queue "something changed" message. The page polls the job status file; when a
job goes from running to finished (done or failed) the shared version number goes up by one, and
every list that depends on the job's result redraws itself when it sees the new number.
"""

RUNNING_MS = 2000  # fast while a job runs, so the bar moves
IDLE_MS = 15000  # slow when nothing runs, so the idle page costs next to nothing
START_STATE = {"n": 0, "running": False}


def watch_step(previous: dict | None, running: bool) -> tuple[dict, int]:
    """(new store value, poll interval in ms). The number goes up only when a job just ended."""
    before = previous or START_STATE
    ended = bool(before.get("running")) and not running
    return {"n": int(before.get("n", 0)) + (1 if ended else 0), "running": running}, (
        RUNNING_MS if running else IDLE_MS
    )
