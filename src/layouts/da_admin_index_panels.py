"""Read-only panels of Repository and index: index health, recent refreshes, refresh tiles and the
fixed skips (fix 11-1, AF-6). The editable tables stay in da_admin_page (they need list_table)."""

from datetime import datetime

import dash_mantine_components as dmc
from dash import dcc, html

from agents.da_admin_index import FIXED_SKIPS, NEEDS_BUILDING, IndexHealth, run_line
from agents.da_admin_job import percent, progress_line
from layouts.da_admin_builds_panel import builds_panel
from styles import da_admin_styles as admin_styles
from styles import da_styles

MERGE_DISABLED_REASON = "Needs Bitbucket to tell the server about merges (WF-12)"
REFRESH_MODES = (
    ("merge", "On every merge to main", MERGE_DISABLED_REASON),
    ("nightly", "Nightly", "Delta job every night"),
    ("manual", "Manual", "Runs when you press Rebuild index"),
)


REBUILD_BTN = "adm-rebuild-btn"
REBUILD_CONFIRM = "adm-rebuild-confirm"
REBUILD_LATER = "adm-rebuild-later"
REBUILD_MODAL = "adm-rebuild-modal"
REBUILD_STATUS = "adm-rebuild-status"
REBUILD_POLL = "adm-rebuild-poll"
REBUILD_ASK = "Rebuild the index now?"
REBUILD_FULL_BTN = "adm-rebuild-full-btn"
REBUILD_FULL_CONFIRM = "adm-rebuild-full-confirm"
REBUILD_FULL_LATER = "adm-rebuild-full-later"
REBUILD_FULL_MODAL = "adm-rebuild-full-modal"
REBUILD_STOP = "adm-rebuild-stop"
REBUILD_PROGRESS = "adm-rebuild-progress"
POLL_MS = 5000
DELTA_EXPLAIN = (
    "Reads only the new or changed programs, drops deleted ones, then tags those programs. "
    "Discovery keeps using the old index until the new one is saved."
)
FULL_EXPLAIN = (
    "Reads every program again and re-tags every program. It takes much longer than Delta. "
    "Discovery keeps using the old index until the new one is saved."
)
FIX_HINT = (
    "Set DA_CODEVISION_SRC (and DA_CODEVISION_PYTHON if CodeVision uses its own Python) "
    "in the .env file, restart the server, then try again."
)
OTHER_HINT = "Check the server settings, then run the job again."


def rebuild_status(started: datetime | None, runs: list[dict]) -> str:
    """The line next to the buttons: running since, else the newest refresh."""
    if started is not None:
        return f"Rebuilding… started {started:%H:%M}"
    return run_line(runs[0]) if runs else ""


def _span_text(seconds: int) -> str:
    minutes = max(1, round(seconds / 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min" if hours else f"{minutes} min"


def estimate_line(runs: list[dict], mode: str) -> str:
    """"Last full rebuild took about 3 h 10 min" from the newest saved run of that mode."""
    for run in runs:
        if run.get("saved") and run.get("mode") == mode and run.get("seconds"):
            return f"Last {mode} rebuild took about {_span_text(int(run['seconds']))}."
    return ""


def error_box(message: str):
    hint = FIX_HINT if "CodeVision" in message else OTHER_HINT
    return dmc.Alert(
        [dmc.Text(message, size="sm"), dmc.Text(hint, size="xs", fw=600)],
        title="The last job did not finish",
        color="red",
        style={"backgroundColor": admin_styles.RED_LIGHT},
    )


def job_panel(status: dict, started: datetime | None, now: datetime | None = None) -> list:
    """Progress while a job runs (step, count, bar, who and when, Stop), else the last error."""
    if started is None:
        return [error_box(status["error"])] if status.get("error") else []
    return [
        dmc.Text(progress_line(status, now), size="sm"),
        dmc.Progress(value=percent(status), size="sm"),
        dmc.Text(
            f"Started by {status.get('started_by', '')} at {started:%H:%M}", size="xs", c="dimmed"
        ),
    ]


def _confirm_modal(modal_id, title, explain, estimate, later_id, confirm_id, label, opened=False):
    return dmc.Modal(
        dmc.Stack(
            [
                dmc.Text(explain, size="sm"),
                dmc.Text(estimate, size="xs", c="dimmed") if estimate else None,
                dmc.Group(
                    [
                        dmc.Button("Later", id=later_id, variant="default"),
                        dmc.Button(label, id=confirm_id),
                    ]
                ),
            ]
        ),
        id=modal_id,
        title=title,
        opened=opened,
    )


def rebuild_controls(
    started: datetime | None,
    runs: list[dict],
    ask_now: bool = False,
    status: dict | None = None,
    now: datetime | None = None,
):
    """Delta and Full buttons with their confirm boxes (the Delta box opens at once after a scope or
    exclusion save), Stop, the status line, the progress panel and a 5 s poll."""
    running = started is not None
    return dmc.Stack(
        [
            dmc.Group(
                [
                    dmc.Button("Delta rebuild", id=REBUILD_BTN, disabled=running, size="xs"),
                    dmc.Button(
                        "Full rebuild",
                        id=REBUILD_FULL_BTN,
                        disabled=running,
                        size="xs",
                        variant="default",
                    ),
                    dmc.Button(
                        "Stop",
                        id=REBUILD_STOP,
                        disabled=not running,
                        size="xs",
                        color="red",
                        variant="light",
                    ),
                ],
                gap="xs",
            ),
            dmc.Text(rebuild_status(started, runs), id=REBUILD_STATUS, size="sm"),
            dmc.Stack(job_panel(status or {}, started, now), id=REBUILD_PROGRESS, gap="xs"),
            dcc.Interval(id=REBUILD_POLL, interval=POLL_MS),
            _confirm_modal(
                REBUILD_MODAL,
                REBUILD_ASK if ask_now else "Delta rebuild?",
                DELTA_EXPLAIN,
                estimate_line(runs, "delta"),
                REBUILD_LATER,
                REBUILD_CONFIRM,
                "Delta rebuild",
                ask_now,
            ),
            _confirm_modal(
                REBUILD_FULL_MODAL,
                "Full rebuild?",
                FULL_EXPLAIN,
                estimate_line(runs, "full"),
                REBUILD_FULL_LATER,
                REBUILD_FULL_CONFIRM,
                "Full rebuild",
            ),
            builds_panel(),
        ],
        gap="xs",
    )


def index_pill(health: IndexHealth, now: datetime):
    colour = "green" if health.is_fresh(now) else "amber"
    return dmc.Badge(health.pill(now), variant="light", style=admin_styles.pill_style(colour))


def health_tiles(health: IndexHealth):
    if not health.built:
        return dmc.Text(NEEDS_BUILDING + " (not built yet).", size="sm")
    built = health.built_at.strftime("%Y-%m-%d %H:%M") if health.built_at else ""
    tiles = (
        ("Built at", built),
        ("Modules indexed", str(health.modules)),
        ("Pieces (functions and classes)", str(health.pieces)),
        ("Source folder", health.source),
    )
    return dmc.SimpleGrid(
        [
            dmc.Paper(
                [
                    dmc.Text(name, size="xs", c="dimmed"),
                    # a path is shown as code, like every path on the console (AF-2)
                    dmc.Code(value, style={"wordBreak": "break-all"})
                    if name == "Source folder"
                    else dmc.Text(value, fw=600, size="sm"),
                ],
                withBorder=True,
                p="xs",
                style={"height": "100%"},  # V6: equal tiles
            )
            for name, value in tiles
        ],
        cols=2,
        spacing="xs",
    )


def recent_refreshes(runs: list[dict]):
    if not runs:
        return dmc.Text("No refreshes yet.", style=da_styles.EMPTY_TEXT)
    rows = []
    for run in runs:
        lines = [
            dmc.Text(run_line(run), size="sm"),
            dmc.Text(run_detail(run), size="xs", c="dimmed"),
        ]
        # Path and symbol only, never the code text.
        if run.get("skipped"):
            lines.append(dmc.Text("Skipped: " + "; ".join(run["skipped"]), size="xs", c="dimmed"))
        if run.get("link_skipped"):  # G1c: files whose code links could not be read, with reason
            text = "No code links: " + "; ".join(run["link_skipped"])
            lines.append(dmc.Text(text, size="xs", c="dimmed"))
        rows.append(html.Div(lines, style=admin_styles.ROW))  # V5: rows with thin dividers
    return html.Div(rows)


def run_detail(run: dict) -> str:
    """Full or Delta, Manual or Nightly, pieces re-read, programs tagged, duration."""
    parts = [str(run.get("mode", "full")).capitalize(), str(run.get("trigger", "Manual"))]
    if "reread" in run:
        parts.append(f"{run['reread']} pieces re-read")
    if "tagged" in run:
        parts.append(f"{run['tagged']} programs tagged")
    if run.get("seconds"):
        parts.append(_span_text(int(run["seconds"])))
    return " · ".join(parts)


def refresh_tiles(mode: str, nightly_time: str = "02:00"):
    """Three equal-width tiles, the chosen one marked. On every merge is disabled (AH-17)."""
    notes = {"nightly": f"Delta job at {nightly_time} Singapore time, while the server runs"}
    return dmc.SimpleGrid(
        [
            dmc.Paper(
                [
                    dmc.Text(("✔ " if key == mode else "") + title, fw=600, size="sm"),
                    dmc.Text(notes.get(key, note), size="xs", c="dimmed"),
                ],
                withBorder=True,
                p="xs",
                style={"height": "100%", **({"opacity": 0.5} if key == "merge" else {})},
            )
            for key, title, note in REFRESH_MODES
        ],
        cols=3,
        spacing="xs",
    )


def fixed_skip_rows():
    return dmc.Stack(
        [dmc.Text(f"🔒 {name}: {why}. Always skipped.", size="sm") for name, why in FIXED_SKIPS],
        gap=2,
    )
