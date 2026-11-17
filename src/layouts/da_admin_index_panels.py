"""Read-only panels of Repository and index: index health, recent refreshes, refresh tiles and the
fixed skips (fix 11-1, AF-6). The editable tables stay in da_admin_page (they need list_table)."""

from datetime import datetime

import dash_mantine_components as dmc
from dash import dcc

from agents.da_admin_index import FIXED_SKIPS, NEEDS_BUILDING, IndexHealth, run_line
from styles import da_admin_styles as admin_styles
from styles import da_styles

REFRESH_MODES = (
    ("merge", "On every merge to main", "Not connected yet"),
    ("nightly", "Nightly", "Not connected yet"),
    ("manual", "Manual", "Runs when you press Rebuild index"),
)


REBUILD_BTN = "adm-rebuild-btn"
REBUILD_CONFIRM = "adm-rebuild-confirm"
REBUILD_LATER = "adm-rebuild-later"
REBUILD_MODAL = "adm-rebuild-modal"
REBUILD_STATUS = "adm-rebuild-status"
REBUILD_POLL = "adm-rebuild-poll"
REBUILD_ASK = "Rebuild the index now?"
REBUILD_EXPLAIN = (
    "Re-reads the folder scope and rebuilds the index. Takes a few minutes. "
    "Discovery keeps using the old index until the new one is saved."
)


def rebuild_status(started: datetime | None, runs: list[dict]) -> str:
    """The line next to the button: running since, else the newest refresh."""
    if started is not None:
        return f"Rebuilding… started {started:%H:%M}"
    return run_line(runs[0]) if runs else ""


def rebuild_controls(started: datetime | None, runs: list[dict], ask_now: bool = False):
    """Rebuild index button, its confirm box (open at once after a scope or exclusion save), the
    status line and a poll that refreshes the status while a build runs."""
    return dmc.Group(
        [
            dmc.Button("Rebuild index", id=REBUILD_BTN, disabled=started is not None, size="xs"),
            dmc.Text(rebuild_status(started, runs), id=REBUILD_STATUS, size="sm"),
            dcc.Interval(id=REBUILD_POLL, interval=3000),
            dmc.Modal(
                dmc.Stack(
                    [
                        dmc.Text(REBUILD_EXPLAIN, size="sm"),
                        dmc.Group(
                            [
                                dmc.Button("Later", id=REBUILD_LATER, variant="default"),
                                dmc.Button("Rebuild", id=REBUILD_CONFIRM),
                            ]
                        ),
                    ]
                ),
                id=REBUILD_MODAL,
                title=REBUILD_ASK if ask_now else "Rebuild the index?",
                opened=ask_now,
            ),
        ]
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
            )
            for name, value in tiles
        ],
        cols=2,
        spacing="xs",
    )


def recent_refreshes(runs: list[dict]):
    if not runs:
        return dmc.Text("No refreshes yet.", style=da_styles.EMPTY_TEXT)
    lines = []
    for run in runs:
        lines.append(dmc.Text(run_line(run), size="sm"))
        # Path and symbol only, never the code text.
        if run.get("skipped"):
            lines.append(dmc.Text("Skipped: " + "; ".join(run["skipped"]), size="xs", c="dimmed"))
    return dmc.Stack(lines, gap=2)


def refresh_tiles(mode: str):
    """Three tiles, the chosen one marked. Only Manual runs today (the others are saved only)."""
    return dmc.Group(
        [
            dmc.Paper(
                [
                    dmc.Text(("✔ " if key == mode else "") + title, fw=600, size="sm"),
                    dmc.Text(note, size="xs", c="dimmed"),
                ],
                withBorder=True,
                p="xs",
            )
            for key, title, note in REFRESH_MODES
        ]
    )


def fixed_skip_rows():
    return dmc.Stack(
        [dmc.Text(f"🔒 {name}: {why}. Always skipped.", size="sm") for name, why in FIXED_SKIPS],
        gap=2,
    )
