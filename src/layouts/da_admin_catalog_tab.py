"""Capability catalog tab: the table, the Unassigned queue cards and their dialogs."""

import dash_mantine_components as dmc
from dash import html

from agents.da_admin_forms import capability_rows
from agents.da_admin_index import read_health
from agents.da_admin_modules import (
    SHOWN_MODULES,
    matches_search,
    module_chips,
    modules_by_capability,
    share_counts,
)
from agents.da_admin_starter import starter_at_work
from agents.da_admin_tag_store import last_tagged, read_tags
from layouts.da_admin_card import admin_card, card_grid
from layouts.da_admin_catalog_meaning import CAP_MEANING_ID, SEARCH_PLACEHOLDER
from layouts.da_admin_common import (
    TAB_CAPABILITY,
    TAB_REPO,
    _draft,
    goto_id,
    list_table,
    version_pill,
)
from layouts.da_admin_starter_card import starter_card
from layouts.da_admin_tag_history_panel import tag_history_panel
from layouts.da_capability_map_view import map_link
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
Q_AI_APPROVE, Q_AI_ASSIGN, Q_AI_REJECT = "ai_approve", "ai_assign", "ai_reject"  # fix 11-2
Q_AI_ALL, Q_AI_ALL_DO = "ai_all", "ai_all_do"  # ask first, then approve every sure proposal
Q_SHOW_RESOLVED = "show_resolved"
Q_HIDE_RESOLVED = "hide_resolved"
NO_CAPABILITIES = (
    "No capabilities yet. Add one, or run an index build and let the AI suggest them."
)
CATALOG_HINT = (
    "First match wins: a file goes to the first capability in this list whose pattern matches. "
    "Use Move up and Move down to change the order."
)


def queue_button_id(action: str, uid: int | str = 0, cap: str = "", state: str = "") -> dict:
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
                tagged_header(),
                dmc.Group(
                    [
                        dmc.TextInput(
                            id=CAP_SEARCH_ID,
                            placeholder=SEARCH_PLACEHOLDER,
                            debounce=True,  # Enter, not per key: meaning search calls the embedder
                            size="xs",
                            w=380,
                        ),
                        dmc.Chip("Missing backup", id=CAP_MISSING_ID, checked=missing_backup),
                    ],
                    mb="xs",
                ),
                html.Div(id=CAP_MEANING_ID),
                html.Div(
                    catalog_list(policy.capabilities, paths, "", missing_backup), id=CAP_LIST_ID
                ),
            ]
        )
    catalog = admin_card(
        "Capabilities",
        html.Div(
            [dmc.Text(CATALOG_HINT, size="xs", c=da_styles.MUTED, mb="xs"), map_link(), table]
        ),
        "🧩",
        count=len(rows),
        actions=version_pill(version, active),
    )
    names = [c.name for c in policy.capabilities]
    starter = None if editable else starter_card(starter_at_work(version.rulebook))
    return card_grid(
        [*([starter] if starter is not None else []), catalog],
        [queue_block(queue, names, disabled=editable)],
    )


def tagged_header():
    """"Programs last tagged ..., with index build ..." and a link to Repository and index (D-C)."""
    when, build = last_tagged(), read_health().build_id
    text = (
        f"Programs last tagged {when}, with index build {build or 'unknown'}."
        if when
        else "Programs have not been tagged yet. Tagging runs as step 2 of the index job."
    )
    return dmc.Group(
        [
            dmc.Text(text, size="xs", c=da_styles.MUTED),
            dmc.Button(
                "Repository and index",
                id=goto_id(TAB_REPO, "catalog-index"),
                variant="subtle",
                size="compact-xs",
            ),
        ],
        gap="xs",
        mb="xs",
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
    summaries = {p: str(e.get("summary", "")) for p, e in read_tags().items()}  # fix 11-2 tooltips
    rows = []
    for c in capabilities:
        mine = by_capability[c.name]
        if missing_backup and c.backup_senior.strip():
            continue
        if not matches_search(
            c.name, c.description, mine, search, (c.named_senior, c.backup_senior)
        ):
            continue
        labels, more = module_chips(mine, counts)
        chips = [
            _chip(label, summaries.get(path, ""))
            for label, path in zip(labels, mine[:SHOWN_MODULES], strict=False)
        ]
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
        text = NO_CAPABILITIES if not capabilities else "No capability matches."
        parts.append(dmc.Text(text, style=da_styles.EMPTY_TEXT))
    return html.Div(parts)


def _chip(label: str, summary: str):
    """A module chip; the AI summary (when the scan has one) shows as a tooltip."""
    badge = dmc.Badge(label, variant="outline", tt="none")
    return dmc.Tooltip(badge, label=summary, multiline=True, w=260) if summary else badge


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
    parts: list = [*queue.get("notice", [])]
    if queue.get("dialog"):
        parts.append(_pattern_dialog(queue["dialog"]))
    ai_cards = queue.get("ai_cards", [])
    if rows:
        parts.append(dmc.Text("From a request", size="xs", fw=600, c=da_styles.MUTED))
        parts.extend(_queue_card(r, capability_names, disabled) for r in rows)
    elif not ai_cards:
        parts.append(dmc.Text("No Unassigned files are waiting.", style=da_styles.EMPTY_TEXT))
    if ai_cards:
        parts.extend(_ai_section(ai_cards, capability_names, disabled, queue.get("ai_confirm")))
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
    parts.append(tag_history_panel())
    waiting = len(rows) + len(ai_cards)
    return admin_card("Unassigned queue", html.Div(parts), "📥", count=waiting, id=QUEUE_BLOCK_ID)


def _queue_card(row, capability_names: list[str], disabled: bool):
    """One Unassigned file as a card (L6): facts on top, the same buttons below."""
    start = row.would_match or row.picked_capability
    return dmc.Paper(
        [
            dmc.Code(row.path),
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


def _ai_section(cards, capability_names: list[str], disabled: bool, confirm: dict | None):
    """The "From the AI scan" cards, and the Approve all box when sure proposals exist.
    The card's path rides in the button id's `uid` (rows from a request use a number there)."""
    sure = [c for c in cards if c.confidence == "high" and c.capability]
    parts: list = [dmc.Text("From the AI scan", size="xs", fw=600, c=da_styles.MUTED)]
    if confirm:
        lines = ", ".join(f"{name}: {n}" for name, n in confirm["counts"].items())
        parts.append(
            dmc.Paper(
                [
                    dmc.Text(
                        f"Approve {sum(confirm['counts'].values())} programs? {lines}", size="sm"
                    ),
                    dmc.Group(
                        [
                            dmc.Button("Approve all", id=queue_button_id(Q_AI_ALL_DO), size="xs"),
                            dmc.Button(
                                "Cancel", id=queue_button_id(Q_CANCEL), size="xs", variant="default"
                            ),
                        ]
                    ),
                ],
                withBorder=True,
                p="sm",
                mb="xs",
            )
        )
    elif sure:
        parts.append(
            dmc.Button(
                f"Approve all high-confidence ({len(sure)})",
                id=queue_button_id(Q_AI_ALL),
                size="xs",
                disabled=disabled,
            )
        )
    parts.extend(_ai_card(c, capability_names, disabled) for c in cards)
    return parts


def _ai_card(card, capability_names: list[str], disabled: bool):
    target = card.capability or "No capability fits"
    buttons = []
    if card.capability:  # no Approve when the AI found no fit
        buttons.append(
            dmc.Button(
                "Approve",
                id=queue_button_id(Q_AI_APPROVE, card.path, card.capability),
                size="xs",
                disabled=disabled,
            )
        )
    buttons += [
        dmc.Select(
            data=capability_names,
            value=card.capability if card.capability in capability_names else None,
            id={"type": QUEUE_PICK_TYPE, "uid": card.path},
            size="xs",
            w=150,
            disabled=disabled,
        ),
        dmc.Button(
            "Assign to",
            id=queue_button_id(Q_AI_ASSIGN, card.path),
            size="xs",
            variant="default",
            disabled=disabled,
        ),
        dmc.Button(
            "Reject",
            id=queue_button_id(Q_AI_REJECT, card.path),
            size="xs",
            variant="default",
            color="red",
            disabled=disabled,
        ),
    ]
    return dmc.Paper(
        [
            dmc.Group(
                [
                    dmc.Code(card.path),
                    dmc.Text(f"→ {target}", size="sm", fw=600),
                    dmc.Badge(card.confidence, variant="light", tt="none"),
                ],
                gap="xs",
            ),
            dmc.Text(card.summary, size="sm"),
            dmc.Text(card.reason, size="xs", style=da_styles.EMPTY_TEXT),
            html.Div(dmc.Group(buttons, gap="xs"), style={"marginTop": "8px"}),
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
