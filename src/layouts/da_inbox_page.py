"""What is on the senior Inbox screen (Phase 10 spec sections 9 and 14).

Presentation only (rule R12), like a display file (DDS) in RPG. The shell below is drawn once at
start-up (so its buttons always exist); the list and the detail are filled in by callbacks.
The detail reuses the developer page layout functions, then `read_only` takes every control
out of the result, so no developer button can work from the inbox (test 10-35).
"""

import dash_mantine_components as dmc
from dash import dcc, html

from agents.da_inbox import UNASSIGNED_HEADING, InboxRow
from agents.da_senior_access import NOT_SENIOR_MESSAGE
from pydantic_classes.da_escalation_models import UNASSIGNED
from styles import da_styles
from web import da_web_components as parts

INBOX_PATH = "/inbox"
INBOX_SHELL_ID = "da-inbox-shell"
INBOX_LIST_ID = "da-inbox-list"
INBOX_DETAIL_ID = "da-inbox-detail"
INBOX_FILTER_ID = "da-inbox-filter"
INBOX_CLOSED_ID = "da-inbox-closed"
INBOX_NOTICE_ID = "da-inbox-notice"
INBOX_REFRESH_ID = "da-inbox-refresh"
INBOX_TARGET_ID = "da-inbox-target"  # Store: the row the senior is looking at and its revision
INBOX_MODAL_ID = "da-inbox-modal"
INBOX_MODE_ID = "da-inbox-mode"  # Store: which of the four actions the dialog is for
INBOX_FINDING_ID = "da-inbox-finding"
INBOX_OUTCOME_ID = "da-inbox-outcome"
INBOX_TEXT_ID = "da-inbox-text"
INBOX_SUBMIT_ID = "da-inbox-submit"
INBOX_CANCEL_ID = "da-inbox-cancel"
INBOX_ERROR_ID = "da-inbox-error"
INBOX_ACT_TYPE = "da-inbox-act"
MENU_LINK_ID = "da-inbox-menu"
BANNER_ID = "da-inbox-banner"

FILTER_MINE, FILTER_ALL = "mine", "all"
MODE_OVERRULE, MODE_GUIDANCE, MODE_TAKE_OVER, MODE_CLOSE = (
    "overrule", "guidance", "take_over", "close",
)  # fmt: skip
ACTIONS: tuple[tuple[str, str], ...] = (
    (MODE_OVERRULE, "Overrule a finding"),
    (MODE_GUIDANCE, "Send guidance"),
    (MODE_TAKE_OVER, "Take over"),
    (MODE_CLOSE, "Close"),
)
MODE_TITLES = {
    MODE_OVERRULE: "Overrule a finding",
    MODE_GUIDANCE: "Send guidance to the developer",
    MODE_CLOSE: "Close this escalation",
}
OUTCOME_RETURN, OUTCOME_ABANDON = "returned", "abandoned"
OUTCOME_CHOICES = [
    {"value": OUTCOME_RETURN, "label": "Return to developer"},
    {"value": OUTCOME_ABANDON, "label": "Abandon request"},
]
READ_ONLY_LINE = "Read-only view. Use the buttons above."
NO_ROWS_TEXT = "Nothing is waiting."

# Components that let a user press, type or pick something. The senior's view has none of them.
_CONTROL_TYPES = frozenset(
    {
        "Button", "ActionIcon", "Textarea", "TextInput", "Select", "MultiSelect", "Checkbox",
        "CheckboxGroup", "Radio", "RadioGroup", "Switch", "SegmentedControl", "NumberInput",
        "NativeSelect", "ChipGroup", "Chip", "Store", "Interval", "Link", "Upload", "FileInput",
        "PasswordInput", "Input",
    }
)  # fmt: skip


def inbox_shell() -> html.Div:
    """Drawn once. Hidden by a callback everywhere but on /inbox."""
    return html.Div(
        [
            dcc.Store(id=INBOX_REFRESH_ID, data=0),
            dcc.Store(id=INBOX_TARGET_ID, data=None),
            dcc.Store(id=INBOX_MODE_ID, data=None),
            dmc.Title("Inbox", order=3, c=da_styles.NAVY),
            dmc.Text(
                "Escalations waiting for a capability senior.",
                c=da_styles.MUTED,
                size="sm",
                mb="sm",
            ),
            dmc.Group(
                [
                    dmc.SegmentedControl(
                        id=INBOX_FILTER_ID,
                        data=[
                            {"value": FILTER_MINE, "label": "Mine"},
                            {"value": FILTER_ALL, "label": "All"},
                        ],
                        value=FILTER_MINE,
                    ),
                    dmc.Switch(id=INBOX_CLOSED_ID, label="Show closed", checked=False),
                ],
                mb="sm",
            ),
            dmc.Text("", id=INBOX_NOTICE_ID, c="green", size="sm", mb="xs"),
            html.Div(id=INBOX_LIST_ID),
            html.Div(id=INBOX_DETAIL_ID),
            _action_dialog(),
        ],
        id=INBOX_SHELL_ID,
        style={**da_styles.PAGE, "display": "none"},
    )


def _action_dialog() -> dmc.Modal:
    """One small dialog for all four actions; the callback shows only the parts the action needs."""
    return dmc.Modal(
        id=INBOX_MODAL_ID,
        opened=False,
        title="",
        children=[
            dmc.Select(
                id=INBOX_FINDING_ID, label="Finding", data=[], placeholder="Pick a finding", mb="sm"
            ),
            dmc.SegmentedControl(
                id=INBOX_OUTCOME_ID, data=OUTCOME_CHOICES, value=OUTCOME_RETURN, mb="sm"
            ),
            dmc.Textarea(id=INBOX_TEXT_ID, label="Text", autosize=True, minRows=3, mb="sm"),
            dmc.Text("", id=INBOX_ERROR_ID, c="red", size="sm", mb="xs"),
            dmc.Group(
                [
                    dmc.Button("Cancel", id=INBOX_CANCEL_ID, variant="default"),
                    dmc.Button("Send", id=INBOX_SUBMIT_ID),
                ],
                justify="flex-end",
            ),
        ],
    )


def refusal_page() -> html.Div:
    return html.Div(dmc.Text(NOT_SENIOR_MESSAGE, c="red"), style=da_styles.PAGE)


def inbox_list(rows: list[InboxRow], link_extra: str = "") -> list:
    """The table, newest first. Rows with nobody named sit under their own heading.
    `link_extra` (for example "&as=ann" in the home shell) is added to every row link."""
    if not rows:
        return [dmc.Text(NO_ROWS_TEXT, c=da_styles.MUTED, size="sm")]
    unassigned = [row for row in rows if row.senior_label == UNASSIGNED]
    named = [row for row in rows if row.senior_label != UNASSIGNED]
    blocks = []
    if named:
        blocks.append(_table(named, link_extra))
    if unassigned:
        blocks.append(dmc.Text(UNASSIGNED_HEADING, fw=700, c=da_styles.NAVY, mt="md", mb="xs"))
        blocks.append(_table(unassigned, link_extra))
    return blocks


def _table(rows: list[InboxRow], link_extra: str) -> dmc.Table:
    head = dmc.TableThead(
        dmc.TableTr(
            [
                dmc.TableTh(name)
                for name in (
                    "Request", "Developer", "Capability", "Why", "When", "Status before",
                    "Open item", "Taken over by", "State",
                )
            ]  # fmt: skip
        )
    )
    return dmc.Table(
        [head, dmc.TableTbody([_row(row, link_extra) for row in rows])], highlightOnHover=True
    )


def _row(row: InboxRow, link_extra: str) -> dmc.TableTr:
    href = f"{INBOX_PATH}?escalation={row.escalation_id}{link_extra}"
    when = parts.format_singapore_time(row.opened_at) if row.opened_at else ""

    def cell(content):
        return dmc.TableTd(
            dcc.Link(
                content,
                href=href,
                style={"textDecoration": "none", "color": "inherit", "display": "block"},
            )
        )

    return dmc.TableTr(
        [
            cell(dmc.Stack([dmc.Code(row.request_id), dmc.Text(row.title, size="sm")], gap=2)),
            cell(row.developer_id),
            cell(row.capability or "-"),
            cell(row.triggers),
            cell(when),
            cell(row.from_status.replace("_", " ")),
            cell(row.open_item),
            cell(row.taken_over_by or "-"),
            cell("Open" if row.outcome == "open" else row.outcome.capitalize()),
        ]
    )


def action_bar(row: InboxRow, closed: bool) -> dmc.Paper:
    """The senior's four buttons, above the read-only request. A closed row has none."""
    summary = [
        dmc.Text(f"{row.request_id}: {row.title}", fw=700, c=da_styles.NAVY),
        dmc.Text(f"Why: {row.triggers}. {row.open_item}", size="sm", c=da_styles.MUTED),
    ]
    if row.taken_over_by:
        summary.append(dmc.Text(f"Taken over by {row.taken_over_by}", size="sm"))
    if closed:
        summary.append(dmc.Text(f"This escalation is {row.outcome}.", size="sm", fw=600))
    buttons = (
        []
        if closed
        else [
            dmc.Button(
                label,
                id={"type": INBOX_ACT_TYPE, "action": key},
                variant="filled" if key == MODE_CLOSE else "light",
                radius="xl",
                size="sm",
            )
            for key, label in ACTIONS
        ]
    )
    return dmc.Paper(
        [dmc.Stack(summary, gap=2), dmc.Group(buttons, mt="sm")],
        withBorder=True, radius="md", p="md", mb="md",
    )  # fmt: skip


def read_only(node):
    """Take every control out of a built page and every id off what is left.

    The developer page is built for one person who presses things; the senior only reads it.
    Removing the controls (and the ids the developer callbacks listen to) is what makes
    "no developer button works from the inbox" true. Returns the cleaned node, or None when the
    node itself is a control."""
    if isinstance(node, list | tuple):
        kept = [read_only(item) for item in node]
        return [item for item in kept if item is not None]
    if not hasattr(node, "to_plotly_json"):
        return node
    if type(node).__name__ in _CONTROL_TYPES:
        return None
    for name in getattr(node, "_prop_names", []):
        value = getattr(node, name, None)
        if name == "id":
            node.id = None
        elif isinstance(value, list | tuple) or hasattr(value, "to_plotly_json"):
            setattr(node, name, read_only(value))
    return node


def all_controls(node) -> list:
    """Every control left in a tree (used by tests to prove there is none)."""
    found = []
    if isinstance(node, list | tuple):
        for item in node:
            found.extend(all_controls(item))
    elif hasattr(node, "to_plotly_json"):
        if type(node).__name__ in _CONTROL_TYPES or getattr(node, "id", None) is not None:
            found.append(node)
        for name in getattr(node, "_prop_names", []):
            value = getattr(node, name, None)
            nested = isinstance(value, list | tuple) or hasattr(value, "to_plotly_json")
            if name != "id" and nested:
                found.extend(all_controls(value))
    return found
