"""Fix G5 N2: the one progress bar every Admin screen shows while a job runs (index, tagging,
re-check): step name, "x of y", percent, time left and Stop. Plain layout code, no AI."""

from datetime import datetime

import dash_mantine_components as dmc
from dash import html

from agents.da_admin_job import percent, progress_line, read_status, step_title
from agents.da_admin_rebuild import running_since

JOB_STOP_TYPE = "adm-job-stop"
BAR_CATALOG = "adm-job-bar-catalog"
BAR_QUEUE = "adm-job-bar-queue"


def job_bar(status: dict, started: datetime | None, where: str, now: datetime | None = None):
    """The bar parts, or [] when no job runs. `where` keeps the Stop button ids apart; the Index
    card has its own Stop button, so it asks for where="index" and gets none."""
    if started is None:  # a finished re-check leaves its end line until the next job starts
        end = status.get("end_line")
        return [dmc.Text(end, size="sm", mb=8)] if end and where != "index" else []
    stop = []
    if where != "index":
        stop = [
            dmc.Button(
                "Stop", id={"type": JOB_STOP_TYPE, "where": where}, size="compact-xs",
                color="red", variant="light",
            )
        ]
    return [
        dmc.Text(step_title(status), fw=600, size="sm"),
        dmc.Text(progress_line(status, now), size="sm"),
        dmc.Progress(value=percent(status), size="sm"),
        dmc.Group(
            [
                dmc.Text(
                    f"Started by {status.get('started_by', '')} at {started:%H:%M}",
                    size="xs", c="dimmed",
                ),
                *stop,
            ],
            gap="xs",
            mb=0 if where == "index" else 8,
        ),
    ]


LOCK_NAMES = ("delta", "full", "recheck", "try", "usebuild")


def lock_id(name: str) -> str:
    return f"adm-lock-{name}"


def locked(name: str, button, own_disabled: bool = False):
    """Fix G5 N3: wraps a job-starting button so a running job can grey it and explain why in the
    tooltip (a disabled button gets no hover of its own). `data-own` remembers the screen's own
    reason to disable it (for example "the catalog is being edited") so the end of a job does not
    enable it by mistake."""
    own = "1" if own_disabled else ""
    return html.Span(button, id=lock_id(name), title="", **{"data-own": own})


def lock_state(status: dict, started: datetime | None, own: str | None) -> tuple[bool, str]:
    """(disabled, tooltip). The server lock stays the second guard."""
    if started is None:
        return bool(own), ""
    done, total = int(status.get("done") or 0), int(status.get("total") or 0)
    count = f", {done} of {total}" if total else ""
    return True, f"A job is running: {step_title(status)}{count}. Wait for it or stop it."


def current_bar(where: str):
    """The bar for a screen drawn right now (the watcher keeps it fresh afterwards)."""
    return html.Div(job_bar(read_status(), running_since(), where), id=BAR_IDS[where])


BAR_IDS = {"catalog": BAR_CATALOG, "queue": BAR_QUEUE}
