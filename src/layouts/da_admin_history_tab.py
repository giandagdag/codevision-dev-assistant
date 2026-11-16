"""Version history tab (L7): a vertical timeline on the left, "What changed in vN" on the right.

Presentation only. Imports the shared helpers from da_admin_common, never from da_admin_page.
"""

import dash_mantine_components as dmc
from dash import html

from layouts.da_admin_common import two_columns, version_pill
from styles import da_admin_styles as admin_styles
from styles import da_styles

HIST_TYPE = "adm-hist"
HIST_PICK_TYPE = "adm-hist-pick"
HIST_RESTORE = "restore"
HIST_CONFIRM = "confirm"
HIST_CANCEL = "cancel"
HIST_VIEW = "view"

_DOT = {
    "width": "12px",
    "height": "12px",
    "borderRadius": "50%",
    "flex": "none",
    "marginTop": "4px",
}


def hist_id(action: str, version: int = 0) -> dict:
    return {"type": HIST_TYPE, "action": action, "version": version}


def pick_id(name: str) -> dict:
    return {"type": HIST_PICK_TYPE, "name": name}


def history_view(
    rows,
    restore_target: int | None = None,
    notice=None,
    selected: int | None = None,
    selected_changes=None,
):
    """Timeline on the left, the selected version's side panel on the right.

    `selected_changes` is the plain (kind, text) lines for the selected version (see
    plain_diff_lines). Rows come newest first."""
    chosen = next((row for row in rows if row.version_number == selected), None)
    active_row = next((row for row in rows if row.is_active), None)
    active = active_row.version_number if active_row else 0
    return html.Div(
        [
            *([version_pill(active_row)] if active_row else []),
            *(notice or []),
            *([_restore_dialog(restore_target, active)] if restore_target else []),
            two_columns(
                dmc.Stack([_timeline_row(row, row is chosen) for row in rows], gap=0),
                _side_panel(chosen, selected_changes),
            ),
        ]
    )


def _side_panel(row, changes):
    if row is None:
        return dmc.Text("Pick a version to see what changed.", style=da_styles.EMPTY_TEXT)
    number = row.version_number
    parts = [dmc.Text(f"What changed in v{number}", fw=600, size="sm", c=da_styles.NAVY)]
    parts.extend(_plain_diff(changes or []))
    parts.append(dmc.Text("Requests pinned", fw=600, size="sm", mt="sm"))
    chips = [dmc.Badge(r, variant="light", tt="none") for r in row.pinned_request_ids]
    none = dmc.Text("None", size="xs", c=da_styles.MUTED)
    parts.append(dmc.Group(chips, gap=4) if chips else none)
    if not row.is_active:
        parts.append(
            dmc.Button(f"Restore v{number}", id=hist_id(HIST_RESTORE, number), size="xs", mt="sm")
        )
    return html.Div(parts, style=da_styles.PANEL_SECTION)


def _plain_diff(changes):
    if not changes:
        return [dmc.Text("No changes.", size="sm")]
    style = {
        "area": {"color": admin_styles.BLUE, "fontWeight": 600},
        "+": {"color": admin_styles.GREEN, "background": admin_styles.GREEN_LIGHT},
        "-": {"color": admin_styles.RED, "background": admin_styles.RED_LIGHT},
    }
    marks = {"area": "", "+": "+ ", "-": "− "}
    return [dmc.Text(marks[k] + text, size="xs", style=style[k]) for k, text in changes]


def _timeline_row(row, selected: bool = False):
    """One dot on the line: green and filled for the active version, grey ring for the rest."""
    dot_style = (
        {**_DOT, "background": admin_styles.GREEN}
        if row.is_active
        else {**_DOT, "border": f"2px solid {da_styles.MUTED}"}
    )
    saved = row.saved_at.strftime("%Y-%m-%d %H:%M")
    tags = []
    if row.is_active:
        tags.append(dmc.Badge("Active", color="green", variant="light", tt="none"))
    if row.restored_from is not None:
        tags.append(
            dmc.Badge(f"Restored from v{row.restored_from}", variant="outline", tt="none")
        )
    head = dmc.Group(
        [dmc.Text(f"v{row.version_number}  {saved}  {row.saved_by}", fw=600, size="sm"), *tags],
        gap=6,
    )
    lines = [head, dmc.Text(row.change_note, size="sm")]
    if row.areas:
        lines.append(dmc.Text("Touched: " + ", ".join(row.areas), size="xs", c=da_styles.MUTED))
    lines.append(_pinned(row))
    lines.append(
        dmc.Button("View", id=hist_id(HIST_VIEW, row.version_number), size="xs", variant="subtle")
    )
    edge = f"2px solid {admin_styles.GREEN}" if selected else "2px solid transparent"
    card = {"flex": "1", "padding": "8px 0 12px 12px", "borderLeft": edge}
    return html.Div(
        [html.Span(style=dot_style), html.Div(lines, style=card)],
        style={"display": "flex", "gap": "8px", "alignItems": "flex-start"},
    )


def _pinned(row):
    count = row.pinned_count
    if not count:
        return dmc.Text("No requests pinned", size="xs", c=da_styles.MUTED)
    label = f"{count} request{'s' if count != 1 else ''} pinned"
    return dmc.Accordion(
        [
            dmc.AccordionItem(
                [
                    dmc.AccordionControl(label),
                    dmc.AccordionPanel(dmc.Text(", ".join(row.pinned_request_ids), size="xs")),
                ],
                value="pinned",
            )
        ],
        value=None,
    )


def _restore_dialog(number: int, active: int = 0):
    return dmc.Alert(
        [
            dmc.Text(f"Restore v{number} as a new version?", size="sm", fw=600),
            dmc.Text(
                f"v{active + 1} becomes active for new requests. Requests in progress keep "
                f"their version. v{active} stays in history.",
                size="xs",
            ),
            dmc.TextInput(
                label="Change note (required)",
                id=pick_id("note"),
                value=f"Restored from v{number}",
            ),
            dmc.Group(
                [
                    dmc.Button("Restore", id=hist_id(HIST_CONFIRM, number), size="xs"),
                    dmc.Button(
                        "Cancel", id=hist_id(HIST_CANCEL, number), size="xs", variant="default"
                    ),
                ],
                mt="xs",
            ),
        ],
        color="blue",
        mb="sm",
    )
