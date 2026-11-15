"""Read-only panels of Repository and index: index health, recent refreshes, refresh tiles and the
fixed skips (fix 11-1, AF-6). The editable tables stay in da_admin_page (they need list_table)."""

from datetime import datetime

import dash_mantine_components as dmc

from agents.da_admin_index import FIXED_SKIPS, NEEDS_BUILDING, IndexHealth, run_line
from styles import da_admin_styles as admin_styles
from styles import da_styles

REFRESH_MODES = (
    ("merge", "On every merge to main", "Not connected yet"),
    ("nightly", "Nightly", "Not connected yet"),
    ("manual", "Manual", "Runs when you press Rebuild index"),
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
    return dmc.Stack([dmc.Text(f"{name}: {value}", size="sm") for name, value in tiles], gap=2)


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
