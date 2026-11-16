"""The Overview tab (fix 11-1, L2): Rulebook panel on the left 2/3, Needs attention and Health
numbers stacked on the right 1/3. Read only. Imports da_admin_common, never da_admin_page."""

import dash_mantine_components as dmc
from dash import html

from agents.da_admin_metrics import WINDOW_ALL, WINDOW_LABELS
from layouts.da_admin_common import ADMIN_TABS, chips, goto_id, two_columns, version_pill
from styles import da_admin_styles as admin_styles
from styles import da_styles

HEALTH_ID = "adm-health"
WINDOW_ID = "adm-window"
STATUS_COLORS = {"green": "green", "amber": "yellow", "red": "red"}

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


def _card(title: str, body):
    return dmc.Paper(
        [dmc.Text(title, fw=700, c=da_styles.NAVY, mb="xs"), body],
        withBorder=True,
        p="md",
        radius="md",
    )


def overview_view(version, overview, report, active: bool = True):
    """The Overview tab. `overview` is an Overview (da_admin_overview), `report` a HealthReport."""
    right = dmc.Stack(
        [
            _card("⚠️ Needs attention", _attention_list(overview.attention)),
            _card("📈 Health numbers", health_block(report)),
        ],
        gap="md",
    )
    return html.Div(
        [
            version_pill(version, active),
            two_columns(_card("📚 Rulebook", _areas_table(overview.areas)), right),
        ]
    )


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
                            "overflow": "visible",
                        },
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


def _attention_list(items):
    if not items:
        return dmc.Text("Nothing needs attention.", size="sm", c=da_styles.MUTED)
    return dmc.Stack(
        [
            dmc.Group(
                [
                    dmc.Badge(
                        STATUS_WORDS.get(item.level, "ℹ️ For your information"),
                        style=admin_styles.pill_style("red" if item.level == "red" else "amber"),
                        variant="light",
                        tt="none",
                    ),
                    dmc.Text(item.text, size="sm"),
                    dmc.Button(
                        "Assign" if item.filter else f"Open {item.area}",
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
    return dmc.SimpleGrid(tiles, cols=2, spacing="sm")
