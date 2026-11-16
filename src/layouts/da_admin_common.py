"""What every Admin tab shares (fix 11-1, section 14): tab names, ids, the version pill, the grid.

Tab files (da_admin_*_tab.py) import this file and never da_admin_page.py, so the two never wait
for each other to load (a circular import). Presentation only, like the rest of layouts/.
"""

import itertools
from datetime import datetime

import dash_mantine_components as dmc
from dash import html

from styles import da_admin_styles as admin_styles
from styles import da_styles

TAB_OVERVIEW = "overview"
TAB_CHARTER = "charter"
TAB_REPO = "repo"
TAB_CAPABILITY = "capability"
TAB_UI = "ui"
TAB_CODING = "coding"
TAB_BUILD = "build"
TAB_HISTORY = "history"

# (id, label, the phase that builds it). Overview comes first (spec section 3).
ADMIN_TABS: tuple[tuple[str, str, str], ...] = (
    (TAB_OVERVIEW, "Overview", "11c"),
    (TAB_CHARTER, "Project charter", "11a"),
    (TAB_REPO, "Repository and index", "11c"),
    (TAB_CAPABILITY, "Capability catalog", "11b"),
    (TAB_UI, "UI standards", "11b"),
    (TAB_CODING, "Coding standards", "11b"),
    (TAB_BUILD, "Build and test", "11a"),
    (TAB_HISTORY, "Version history", "11a"),
)

GOTO_TYPE = "adm-goto"
_HISTORY_LINK_COUNTER = itertools.count(5000)  # each button needs its own id (all tabs are drawn)


def goto_id(tab: str, n) -> dict:
    # n keeps every id unique; the callback reads only "tab" from the clicked button.
    return {"type": GOTO_TYPE, "tab": tab, "n": n}


def body_id(tab: str) -> str:
    return f"adm-body-{tab}"


def act_id(tab: str, action: str) -> dict:
    return {"type": "adm-act", "tab": tab, "action": action}


def section(title: str, body):
    return html.Div(
        [dmc.Text(title, fw=600, c=da_styles.NAVY, size="sm"), body], style=da_styles.PANEL_SECTION
    )


def chips(summary: str):
    """A summary line such as "3 capabilities, 2 Unassigned" as small chips."""
    parts = [p.strip() for p in summary.replace(";", ",").split(",") if p.strip()]
    return dmc.Group([dmc.Badge(p, variant="outline", tt="none") for p in parts], gap=4)


def word_chips(words: list[str], style: dict | None = None, variant: str = "light"):
    """One small chip per word (folders, markers, libraries). `style` colours them; paths use
    variant "outline" (the code-chip look the label scan skips)."""
    if not words:
        return dmc.Text("None.", style=da_styles.EMPTY_TEXT)
    return dmc.Group(
        [dmc.Badge(w, variant=variant, tt="none", style=style) for w in words], gap=4
    )


def two_columns(left, right, left_share: int = 2):
    """Left `left_share`/3, right the rest (spec 14.1: 2/3 and 1/3). Inline style only."""
    columns = f"minmax(0, {left_share}fr) minmax(0, {3 - left_share}fr)"
    return html.Div(
        [html.Div(left, style={"minWidth": 0}), html.Div(right, style={"minWidth": 0})],
        style={
            "display": "grid",
            "gridTemplateColumns": columns,
            "gap": "16px",
            "alignItems": "start",
        },
    )


def version_pill(version, active: bool = True) -> html.Div:
    """The pill on the right of every tab header (L1): dot, version, who and when, View history.

    `version` is anything with version_number, saved_at and saved_by (a RulebookVersion or a
    timeline row). After a stale save the form shows the version the Admin started from, which is
    not active, so it says "Started from vN" with a grey dot."""
    saved: datetime = version.saved_at
    dot = admin_styles.GREEN if active else da_styles.MUTED
    title = f"Active rulebook v{version.version_number}" if active else (
        f"Started from v{version.version_number}"
    )
    pill = dmc.Paper(
        dmc.Group(
            [
                html.Span(
                    style={
                        "width": "10px",
                        "height": "10px",
                        "borderRadius": "50%",
                        "background": dot,
                        "display": "inline-block",
                    }
                ),
                dmc.Stack(
                    [
                        dmc.Text(title, size="sm", fw=700, c=da_styles.NAVY),
                        dmc.Text(
                            f"Published {saved:%Y-%m-%d %H:%M}, {version.saved_by}",
                            size="xs",
                            c=da_styles.MUTED,
                        ),
                    ],
                    gap=0,
                ),
                dmc.Button(
                    "View history",
                    id=goto_id(TAB_HISTORY, next(_HISTORY_LINK_COUNTER)),
                    size="compact-xs",
                    variant="default",
                ),
            ],
            gap="sm",
            wrap="nowrap",
        ),
        withBorder=True,
        radius="xl",
        px="md",
        py=6,
    )
    right = {"display": "flex", "justifyContent": "flex-end", "marginBottom": "8px"}
    return html.Div(pill, style=right)
