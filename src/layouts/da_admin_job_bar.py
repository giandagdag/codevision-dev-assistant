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
    if started is None:
        return []
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
        ),
    ]


def current_bar(where: str):
    """The bar for a screen drawn right now (the watcher keeps it fresh afterwards)."""
    return html.Div(
        job_bar(read_status(), running_since(), where), id=BAR_IDS[where], style={"marginBottom": 8}
    )


BAR_IDS = {"catalog": BAR_CATALOG, "queue": BAR_QUEUE}
