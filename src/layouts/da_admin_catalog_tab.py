"""Capability catalog tab: the table, the Unassigned queue cards and their dialogs."""

import dash_mantine_components as dmc
from dash import html

from agents.da_admin_forms import capability_rows
from agents.da_admin_modules import (
    matches_search,
    module_chips,
    modules_by_capability,
    share_counts,
)
from layouts.da_admin_common import (
    MOVE_TYPE,  # noqa: F401 (re-exported through the page)
    TAB_CAPABILITY,
    _draft,
    list_table,
    two_columns,
    version_pill,
)
from pydantic_classes.da_rulebook_models import RulebookVersion
from styles import da_admin_styles as admin_styles
from styles import da_styles

# --- Capability catalog and the Unassigned queue (Phase 11b) ---

CATALOG_TABLE = "capabilities"
CATALOG_COLUMNS = ("name", "description", "named_senior", "backup_senior", "path_patterns")
QUEUE_BUTTON_TYPE = "adm-q"
QUEUE_PICK_TYPE = "adm-q-pick"
QUEUE_NOTE_TYPE = "adm-q-note"
QUEUE_BLOCK_ID = "adm-queue"
Q_CONFIRM = "confirm"
Q_MOVE = "move"
Q_APPROVE = "approve"  # take the suggested capability (the id's `cap` carries it)
Q_REJECT = "reject"  # the file belongs in no capability: closes the row as rejected
Q_NEW = "new_capability"  # open the catalog in edit mode with one new row for this file
Q_APPLY = "apply"
Q_APPLY_PATTERN = "apply_pattern"
Q_CANCEL = "cancel"
Q_SHOW_RESOLVED = "show_resolved"
Q_HIDE_RESOLVED = "hide_resolved"
CATALOG_HINT = (
    "First match wins: a file goes to the first capability in this list whose pattern matches. "
    "Use Move up and Move down to change the order."
)


def queue_button_id(action: str, uid: int = 0, cap: str = "", state: str = "") -> dict:
    # Every queue button has the same four keys so one callback pattern matches them all.
    return {"type": QUEUE_BUTTON_TYPE, "action": action, "uid": uid, "cap": cap, "state": state}


def catalog_view(
    version: RulebookVersion,
    editable: bool = False,
    draft: dict | None = None,
    active: bool = True,
    queue: dict | None = None,
    modules: list[str] | None = None,
    missing_backup: bool = False,
):
    """The catalog table (editable) with the Unassigned queue under it (read view only).
    `modules` is every indexed path (da_admin_modules.module_paths)."""
    policy = version.rulebook.policy
    rows = _draft(draft, CATALOG_TABLE, capability_rows(policy))
    paths = modules or []
    if editable:
        table = html.Div(
            [
                list_table(
                    TAB_CAPABILITY, CATALOG_TABLE, CATALOG_COLUMNS, rows, editable, movable=True
                ),
                _add_module_panel([r["name"] for r in rows if r.get("name")], paths),
            ]
        )
    else:
        table = html.Div(
            [
                dmc.Group(
                    [
                        dmc.TextInput(
                            id=CAP_SEARCH_ID, placeholder="Search name or module", size="xs"
                        ),
                        dmc.Chip("Missing backup", id=CAP_MISSING_ID, checked=missing_backup),
                    ],
                    mb="xs",
                ),
                html.Div(
                    catalog_list(policy.capabilities, paths, "", missing_backup), id=CAP_LIST_ID
                ),
            ]
        )
    return html.Div(
        [
            version_pill(version, active),
            dmc.Text(CATALOG_HINT, size="xs", c=da_styles.MUTED),
            two_columns(
                table,
                queue_block(queue, [c.name for c in policy.capabilities], disabled=editable),
            ),
        ]
    )


CAP_SEARCH_ID = "adm-cat-search"
CAP_MISSING_ID = "adm-cat-missing"
CAP_LIST_ID = "adm-cat-list"
MODULE_TABLE = "capmodule"  # the Add module picker: one row, a capability and a path
MODULE_COLUMNS = ("capability", "path")


def catalog_list(capabilities, paths: list[str], search: str = "", missing_backup: bool = False):
    """The read-only catalog: one row per capability with its module chips (max 6, then +N more).
    A module claimed by two capabilities shows "×2". Search matches name, description or module."""
    by_capability = modules_by_capability(list(capabilities), paths)
    counts = share_counts(by_capability)
    rows = []
    for c in capabilities:
        mine = by_capability[c.name]
        if missing_backup and c.backup_senior.strip():
            continue
        if not matches_search(c.name, c.description, mine, search):
            continue
        labels, more = module_chips(mine, counts)
        chips = [dmc.Badge(label, variant="outline", tt="none") for label in labels]
        if more:
            chips.append(dmc.Badge(f"+{more} more", variant="light", tt="none"))
        backup = c.backup_senior.strip() or "none"
        rows.append(
            dmc.TableTr(
                [
                    dmc.TableTd(dmc.Text(c.name, fw=600, size="sm")),
                    dmc.TableTd(dmc.Text(c.description, size="sm")),
                    dmc.TableTd(_person(c.named_senior)),
                    dmc.TableTd(
                        _person(c.backup_senior)
                        if c.backup_senior.strip()
                        else dmc.Badge(
                            backup, variant="light", style=admin_styles.pill_style("amber")
                        )
                    ),
                    dmc.TableTd(
                        dmc.Group(chips or [dmc.Text("none", size="xs")], gap=4),
                        style={"minWidth": "240px"},  # keeps the chips from being clipped
                    ),
                ]
            )
        )
    head = dmc.TableThead(
        dmc.TableTr(
            [
                dmc.TableTh(h)
                for h in ("Capability", "Description", "Named senior", "Backup senior", "Modules")
            ]
        )
    )
    parts: list = [dmc.Table([head, dmc.TableTbody(rows)])]
    if not rows:
        parts.append(dmc.Text("No capability matches.", style=da_styles.EMPTY_TEXT))
    return html.Div(parts)


def _person(name: str):
    """A senior as a small initials circle and the full name (it wraps, never cut off)."""
    initials = "".join(word[0] for word in name.split()[:2]).upper()
    return dmc.Group(
        [dmc.Avatar(initials, size="sm", radius="xl", color="blue"), dmc.Text(name, size="sm")],
        gap="xs",
        wrap="nowrap",
    )


def _add_module_panel(names: list[str], paths: list[str]):
    """Edit mode: pick a capability and an indexed path; Add module makes it an exact pattern."""

    def cell(col, data):
        return dmc.Select(
            data=data,
            searchable=True,
            size="xs",
            id={
                "type": "adm-cell",
                "tab": TAB_CAPABILITY,
                "table": MODULE_TABLE,
                "row": 0,
                "col": col,
            },
        )

    return dmc.Group(
        [
            cell("capability", names),
            cell("path", paths),
            dmc.Button(
                "Add module",
                id={"type": "adm-add", "tab": TAB_CAPABILITY, "table": MODULE_TABLE, "index": 0},
                variant="default",
                size="xs",
            ),
        ],
        mt="xs",
    )


def _waiting_text(row) -> str:
    return row.waiting_since.strftime("%Y-%m-%d") if row.waiting_since else ""


def queue_block(queue: dict | None, capability_names: list[str], disabled: bool = False):
    """Open Unassigned files, what each would match today, and the buttons to resolve them.

    `queue` is {"rows": [QueueRow], "resolved": [UnassignedFile] or None, "dialog": dict or None,
    "notice": [component]}. While the catalog is edited the buttons are disabled (one change at
    a time)."""
    queue = queue or {"rows": [], "resolved": None, "dialog": None, "notice": []}
    rows = queue["rows"]
    parts: list = [
        dmc.Text("Unassigned queue", fw=600, c=da_styles.NAVY, size="sm"),
        *queue.get("notice", []),
    ]
    if queue.get("dialog"):
        parts.append(_pattern_dialog(queue["dialog"]))
    if rows:
        parts.extend(_queue_card(r, capability_names, disabled) for r in rows)
    else:
        parts.append(dmc.Text("No Unassigned files are waiting.", style=da_styles.EMPTY_TEXT))
    if queue.get("resolved") is None:
        parts.append(
            dmc.Button(
                "Show resolved",
                id=queue_button_id(Q_SHOW_RESOLVED),
                variant="default",
                size="xs",
                mt="xs",
                disabled=disabled,
            )
        )
    else:
        parts.append(_resolved_table(queue["resolved"]))
        parts.append(
            dmc.Button(
                "Hide resolved",
                id=queue_button_id(Q_HIDE_RESOLVED),
                variant="default",
                size="xs",
                disabled=disabled,
            )
        )
    return html.Div(parts, id=QUEUE_BLOCK_ID, style=da_styles.PANEL_SECTION)


def _queue_card(row, capability_names: list[str], disabled: bool):
    """One Unassigned file as a card (L6): facts on top, the same buttons below."""
    start = row.would_match or row.picked_capability
    return dmc.Paper(
        [
            dmc.Text(row.path, size="sm", fw=600),
            dmc.Text(f"Developer's pick: {row.picked_capability}", size="xs", c=da_styles.MUTED),
            dmc.Text(
                f"Request {row.request_id}, waiting since {_waiting_text(row)}",
                size="xs",
                c=da_styles.MUTED,
            ),
            dmc.Text(f"Would match: {row.would_match or '(none)'}", size="xs", c=da_styles.MUTED),
            dmc.Text(f"Suggestion: {row.suggested or '(none)'}", size="xs", fw=600),
            dmc.Text(row.reason, size="xs", style=da_styles.EMPTY_TEXT),
            html.Div(
                dmc.Group(
                    [
                        *(
                            [
                                dmc.Button(
                                    "Approve",
                                    id=queue_button_id(Q_APPROVE, row.unassigned_id, row.suggested),
                                    size="xs",
                                    disabled=disabled,
                                )
                            ]
                            if row.suggested
                            else []
                        ),
                        dmc.Button(
                            "Confirm",
                            id=queue_button_id(Q_CONFIRM, row.unassigned_id),
                            size="xs",
                            disabled=disabled,
                        ),
                        dmc.Select(
                            data=capability_names,
                            value=start if start in capability_names else None,
                            id={"type": QUEUE_PICK_TYPE, "uid": row.unassigned_id},
                            size="xs",
                            w=150,
                            disabled=disabled,
                        ),
                        dmc.Button(
                            "Move to...",
                            id=queue_button_id(Q_MOVE, row.unassigned_id),
                            size="xs",
                            variant="default",
                            disabled=disabled,
                        ),
                        dmc.Button(
                            "New capability",
                            id=queue_button_id(Q_NEW, row.unassigned_id),
                            size="xs",
                            variant="default",
                            disabled=disabled,
                        ),
                        dmc.Button(
                            "Reject",
                            id=queue_button_id(Q_REJECT, row.unassigned_id),
                            size="xs",
                            variant="default",
                            color="red",
                            disabled=disabled,
                        ),
                    ],
                    gap="xs",
                ),
                style={"marginTop": "8px"},
            ),
        ],
        withBorder=True,
        p="sm",
        mb="xs",
    )


def _pattern_dialog(dialog: dict):
    """Asked after Confirm or Move: close the row, and (if it helps) also add the path as a
    pattern. dialog: uid, state, capability, path, offer (True when a pattern helps), reason."""
    uid, state, cap = dialog["uid"], dialog["state"], dialog["capability"]
    verb = "Confirm" if state == "confirmed" else f"Move to {cap}"
    parts: list = [
        dmc.Text(f"{verb}: {dialog['path']}", size="sm", fw=600),
        dmc.TextInput(
            label="Change note (needed only if you add the pattern)",
            id={"type": QUEUE_NOTE_TYPE, "uid": uid},
            value="",
        ),
    ]
    buttons = []
    if dialog["offer"]:
        parts.insert(
            1, dmc.Text(f"Also add this path as a pattern to '{cap}'? Next files then match.")
        )
        buttons.append(
            dmc.Button(
                "Add pattern and resolve",
                id=queue_button_id(Q_APPLY_PATTERN, uid, cap, state),
                size="xs",
            )
        )
    else:
        parts.insert(1, dmc.Text(dialog["reason"], size="sm"))
    buttons.append(
        dmc.Button(
            "Resolve without pattern",
            id=queue_button_id(Q_APPLY, uid, cap, state),
            size="xs",
            variant="default",
        )
    )
    buttons.append(
        dmc.Button("Cancel", id=queue_button_id(Q_CANCEL, uid), size="xs", variant="subtle")
    )
    return dmc.Alert([*parts, dmc.Group(buttons, mt="xs")], color="blue", mb="sm")


def _resolved_table(rows):
    if not rows:
        return dmc.Text("Nothing resolved yet.", style=da_styles.EMPTY_TEXT)
    header = ("Path", "State", "By", "When", "Moved to")
    body = []
    for row in rows:
        when = row.resolved_at.strftime("%Y-%m-%d %H:%M") if row.resolved_at else ""
        values = (row.path, row.state, row.resolved_by, when, row.resolved_capability)
        body.append(dmc.TableTr([dmc.TableTd(dmc.Text(v, size="sm")) for v in values]))
    return dmc.Table(
        [dmc.TableThead(dmc.TableTr([dmc.TableTh(h) for h in header])), dmc.TableTbody(body)],
        withTableBorder=True,
    )
