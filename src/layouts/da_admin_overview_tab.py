"""The Overview tab (fix 11-1, L2 and section 15): Rulebook panel on the left 2/3, Needs attention
on the right 1/3, and Health numbers as one full-width row of tiles underneath (Gian, 16 Nov: no
empty space at the lower left). Read only. Imports da_admin_common, never da_admin_page."""

import dash_mantine_components as dmc
from dash import html

from agents.da_admin_metrics import WINDOW_ALL, WINDOW_LABELS
from layouts.da_admin_card import admin_card, card_grid
from layouts.da_admin_common import ADMIN_TABS, chips, goto_id, version_pill
from styles import da_admin_styles as admin_styles
from styles import da_styles

HEALTH_ID = "adm-health"
HEALTH_ROW_ID = "adm-health-row"
ATTENTION_SCROLL_ID = "adm-attention-scroll"
ATTENTION_SCROLL = {"maxHeight": "480px", "overflowY": "auto", "paddingRight": "4px"}
# Section 15: the tiles run across the page, 5 per row on a 1366 wide screen.
HEALTH_COLS = {"base": 2, "md": 3, "lg": 5}
WINDOW_ID = "adm-window"
STOP_ACT_TYPE = "adm-stop-act"
STOP_NOTE_TYPE = "adm-stop-note"
STATUS_COLORS ={"green": "green", "amber": "yellow", "red": "red"}

# The status colour is a code value; an Admin reads these words, not "green" or "amber".
STATUS_WORDS = {"green": "✅ Up to date", "amber": "⚠️ To review", "red": "❌ Needs fixing"}
AREA_ICONS = {
    "Project charter": "📜",
    "Repository and index": "🗂",
    "Capability catalog": "🧩",
    "UI standards": "🎨",
    "Coding standards": "📏",
    "Build and test": "🛠",
}


def _tab_of_area(area: str) -> str:
    return next(tab for tab, label, _ in ADMIN_TABS if label == area)


def overview_view(version, overview, report, active: bool = True):
    """The Overview tab. `overview` is an Overview (da_admin_overview), `report` a HealthReport.
    Rulebook and Health numbers on the left, Needs attention (it scrolls) on the right."""
    attention = html.Div(
        _attention_list(overview.attention), id=ATTENTION_SCROLL_ID, style=ATTENTION_SCROLL
    )
    main = [
        admin_card(
            "Rulebook", _areas_table(overview.areas), "📚", actions=version_pill(version, active)
        ),
        admin_card("Health numbers", health_block(report), "📈", id=HEALTH_ROW_ID),
    ]
    side = [admin_card("Needs attention", attention, "⚠️", count=len(overview.attention))]
    return card_grid(main, side)


def _areas_table(areas):
    head = dmc.TableThead(
        dmc.TableTr([dmc.TableTh(name) for name in ("Area", "Summary", "Status", "Updated")])
    )
    rows = [
        dmc.TableTr(
            [
                dmc.TableTd(
                    dmc.Group(
                        [
                            dmc.Text(AREA_ICONS.get(row.area, "•")),
                            dmc.Button(
                                row.area,
                                id=goto_id(_tab_of_area(row.area), 1000 + index),
                                variant="subtle",
                                size="xs",
                            ),
                        ],
                        gap=4,
                    )
                ),
                dmc.TableTd(chips(row.summary)),
                dmc.TableTd(
                    dmc.Badge(
                        STATUS_WORDS.get(row.status, row.status),
                        # The pill grows to its text; the cell never wraps (it was cut at 1366).
                        style={
                            **admin_styles.pill_style(row.status),
                            "maxWidth": "none",
                            "width": "max-content",
                            "overflow": "visible",
                        },
                        # Mantine clips the inner label with "..." unless told not to.
                        styles={"label": {"overflow": "visible", "textOverflow": "clip"}},
                        variant="light",
                        tt="none",
                    ),
                    style={"whiteSpace": "nowrap"},
                ),
                dmc.TableTd(row.last_changed),
            ]
        )
        for index, row in enumerate(areas)
    ]
    return dmc.Table([head, dmc.TableTbody(rows)])


def _jump_label(item) -> str:
    if item.filter == "review_queue":
        return "Open Review queue"
    return "Assign" if item.filter else f"Open {item.area}"


def _stopped_panel(item):
    """Fix G5: the request, the reason, a note box, Release and Keep stopped."""
    rid = item.request_id

    def button(action, label, **kwargs):
        return dmc.Button(label, id={"type": STOP_ACT_TYPE, "action": action, "rid": rid},
                          size="xs", **kwargs)

    return dmc.Paper(
        [
            dmc.Badge("Stopped", style=admin_styles.pill_style("red"), variant="light"),
            dmc.Text(f"{item.text} ({rid})", size="sm", fw=600),
            dmc.Text(item.detail, size="xs", style={"whiteSpace": "pre-wrap"}),
            dmc.Textarea(id={"type": STOP_NOTE_TYPE, "rid": rid}, size="xs", autosize=True,
                         placeholder="Note (required to release)"),
            dmc.Group([button("release", "Release"),
                       button("keep", "Keep stopped", variant="default")], gap="xs"),
        ],
        withBorder=True, p="xs",
    )


def _attention_list(items, message: str = ""):
    if not items:
        return dmc.Text("Nothing needs attention.", size="sm", c=da_styles.MUTED)
    return dmc.Stack(
        ([dmc.Alert(message, color="red")] if message else []) + [
            _stopped_panel(item) if item.request_id else dmc.Group(
                [
                    dmc.Badge(
                        STATUS_WORDS.get(item.level, "ℹ️ For your information"),
                        style=admin_styles.pill_style("red" if item.level == "red" else "amber"),
                        variant="light",
                        tt="none",
                    ),
                    dmc.Text(item.text, size="sm"),
                    dmc.Button(
                        _jump_label(item),
                        # n carries the catalog filter: the callback reads only "tab" for now.
                        id=goto_id(
                            _tab_of_area(item.area),
                            f"{item.filter}-{index}" if item.filter else index,
                        ),
                        variant="subtle",
                        size="xs",
                    ),
                ]
            )
            for index, item in enumerate(items)
        ],
        gap="xs",
    )


def health_block(report, window: str = WINDOW_ALL):
    """The window chooser plus the numbers. The chooser re-draws only the part inside adm-health."""
    return html.Div(
        [
            dmc.SegmentedControl(
                id=WINDOW_ID,
                value=window,
                data=[{"value": key, "label": label} for key, label in WINDOW_LABELS.items()],
                size="xs",
                mb="xs",
            ),
            html.Div(health_numbers(report), id=HEALTH_ID),
        ]
    )


def health_numbers(report):
    tiles = []
    for metric in report.all_metrics:
        parts = [dmc.Text(f"{metric.label}: {metric.text}", size="sm")]
        if metric.items:
            shown = ", ".join(f"{name} {count}" for name, count in metric.items)
            parts.append(dmc.Text(shown, size="xs", c=da_styles.MUTED))
        if metric.note:
            parts.append(dmc.Text(metric.note, size="xs", c=da_styles.MUTED))
        tiles.append(dmc.Paper(parts, withBorder=True, p="sm"))
    return dmc.SimpleGrid(tiles, cols=HEALTH_COLS, spacing="sm")
