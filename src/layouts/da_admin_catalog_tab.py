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
from agents.da_admin_review import (
    ReviewFilter,
    bulk_plan,
    filter_ai_cards,
    filter_requests,
    filter_suggestions,
    top_folders,
)
from agents.da_admin_starter import starter_at_work
from agents.da_admin_tag_store import last_tagged, read_tags
from layouts.da_admin_card import admin_card
from layouts.da_admin_catalog_meaning import CAP_MEANING_ID, SEARCH_PLACEHOLDER
from layouts.da_admin_catalog_panels import modules_modal, patterns_panel
from layouts.da_admin_common import (
    PATTERNS,
    TAB_CAPABILITY,
    TAB_REPO,
    _draft,
    goto_id,
    list_table,
    pat_id,
    version_pill,
)
from layouts.da_admin_queue_ids import (  # noqa: F401  (other modules import these from here)
    CAT_PANE_CAPS,
    CAT_PANE_QUEUE,
    CAT_VIEW_ID,
    Q_AI_ALL,
    Q_AI_ALL_DO,
    Q_AI_APPROVE,
    Q_AI_ASSIGN,
    Q_AI_REJECT,
    Q_APPLY,
    Q_APPLY_PATTERN,
    Q_APPROVE,
    Q_CANCEL,
    Q_CONFIRM,
    Q_HIDE_RESOLVED,
    Q_MOVE,
    Q_NEW,
    Q_RECHECK,
    Q_REJECT,
    Q_SG_ASSIGN,
    Q_SG_OPEN,
    Q_SG_REJECT,
    Q_SG_REMOVE,
    Q_SG_SAVE,
    Q_SHOW_RESOLVED,
    QUEUE_BLOCK_ID,
    QUEUE_BUTTON_TYPE,
    QUEUE_NOTE_TYPE,
    QUEUE_PICK_TYPE,
    RQ_SEL_TYPE,
    VIEW_CAPS,
    VIEW_QUEUE,
    queue_button_id,
)
from layouts.da_admin_review_view import bulk_bar, bulk_confirm, review_pane
from layouts.da_admin_starter_card import starter_card
from layouts.da_admin_tag_history_panel import tag_history_panel
from layouts.da_capability_map_view import map_link
from pydantic_classes.da_rulebook_models import RulebookVersion
from styles import da_admin_styles as admin_styles
from styles import da_styles

# --- Capability catalog and the Unassigned queue (Phase 11b) ---

CATALOG_TABLE = "capabilities"
CATALOG_COLUMNS = ("name", "description", "named_senior", "backup_senior", "path_patterns")
# Fix G4 L1: fixed column widths and one input height, so every row lines up.
CATALOG_WIDTHS = {
    "name": "18%",
    "description": "30%",
    "named_senior": "14%",
    "backup_senior": "14%",
    "path_patterns": "14%",
    "actions": "10%",
}
CATALOG_INPUT_HEIGHT = "56px"  # two lines of the xs text
SG_FIELDS = ("name", "desc", "named", "backup")  # dialog inputs: the id's uid is "<name>|<field>"
NO_CAPABILITIES = "No capabilities yet. Add one, or run an index build and let the AI suggest them."
CATALOG_HINT = (
    "First match wins: a file goes to the first capability in this list whose pattern matches. "
    "Use Move up and Move down to change the order."
)


def catalog_view(
    version: RulebookVersion,
    editable: bool = False,
    draft: dict | None = None,
    active: bool = True,
    queue: dict | None = None,
    modules: list[str] | None = None,
    missing_backup: bool = False,
    panel: dict | None = None,
):
    """The catalog table (editable) with the Unassigned queue under it (read view only).
    `modules` is every indexed path (da_admin_modules.module_paths). `panel` opens the patterns
    side panel ({"kind": "patterns", "index": n}) or the pop-up ({"kind": "modules"})."""
    policy = version.rulebook.policy
    rows = _draft(draft, CATALOG_TABLE, capability_rows(policy))
    paths = modules or []
    if editable:
        table = html.Div(
            [
                list_table(
                    TAB_CAPABILITY,
                    CATALOG_TABLE,
                    CATALOG_COLUMNS,
                    rows,
                    editable,
                    movable=True,
                    kinds={"path_patterns": PATTERNS},
                    widths=CATALOG_WIDTHS,
                    input_height=CATALOG_INPUT_HEIGHT,
                ),
                dmc.Button(
                    "Add modules",
                    id=pat_id(TAB_CAPABILITY, "openmods"),
                    variant="default",
                    size="xs",
                    mt="xs",
                ),
                *_open_panel(panel, rows, policy.capabilities, paths),
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
    queue = queue or {}
    open_cards = len(queue.get("rows", ())) + len(queue.get("ai_cards", ())) + len(
        queue.get("suggestions", ())
    )
    view = (queue.get("review") or {}).get("view") or VIEW_CAPS
    shown, hidden = {}, {"display": "none"}
    return html.Div(
        [
            dmc.SegmentedControl(
                id=CAT_VIEW_ID,
                data=[
                    {"value": VIEW_CAPS, "label": "Capabilities"},
                    {"value": VIEW_QUEUE, "label": f"Review queue ({open_cards})"},
                ],
                value=view,
                mb="sm",
            ),
            html.Div(
                html.Div(
                    [*([starter] if starter is not None else []), catalog],
                    style=admin_styles.CARD_STACK,
                ),
                id=CAT_PANE_CAPS,
                style=shown if view == VIEW_CAPS else hidden,
            ),
            html.Div(
                queue_block(queue, names, disabled=editable),
                id=CAT_PANE_QUEUE,
                style=shown if view == VIEW_QUEUE else hidden,
            ),
        ]
    )


def tagged_header():
    """ "Programs last tagged ..., with index build ..." and a link to Repository and index."""
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


def _open_panel(panel: dict | None, rows: list[dict], capabilities, paths: list[str]) -> list:
    """The side panel or pop-up a click asked for. Rows come from the draft (unsaved names show)."""
    if not panel:
        return []
    if panel["kind"] == "patterns" and 0 <= panel["index"] < len(rows):
        row = rows[panel["index"]]
        return [
            patterns_panel(
                TAB_CAPABILITY, panel["index"], row.get("name", ""), _patterns_text(row), paths
            )
        ]
    if panel["kind"] == "modules":
        summaries = {p: str(e.get("summary", "")) for p, e in read_tags().items()}
        # Owners come from the saved catalog (the filter callback cannot see the unsaved draft).
        return [
            modules_modal(
                TAB_CAPABILITY, list(capabilities), paths, summaries, panel.get("target", "")
            )
        ]
    return []


def _patterns_text(row: dict) -> str:
    text = row.get("path_patterns", "")
    return "\n".join(text) if isinstance(text, list) else text


def _waiting_text(row) -> str:
    return row.waiting_since.strftime("%Y-%m-%d") if row.waiting_since else ""


def queue_block(queue: dict | None, capability_names: list[str], disabled: bool = False):
    """Open Unassigned files, what each would match today, and the buttons to resolve them.

    `queue` is {"rows": [QueueRow], "resolved": [UnassignedFile] or None, "dialog": dict or None,
    "notice": [component]}. While the catalog is edited the buttons are disabled (one change at
    a time)."""
    queue = queue or {"rows": [], "resolved": None, "dialog": None, "notice": []}
    rows = queue["rows"]
    ai_cards = queue.get("ai_cards", [])
    suggested = queue.get("suggestions", [])
    review = queue.get("review") or {}
    rf = review.get("filter") or ReviewFilter()
    selected = review.get("selected", [])
    above: list = [*queue.get("notice", [])]
    if queue.get("dialog"):
        above.append(_pattern_dialog(queue["dialog"]))
    above.extend(_ai_confirm_box(ai_cards, queue.get("ai_confirm"), disabled))
    if review.get("bulk"):
        bulk = review["bulk"]
        above.append(bulk_confirm(bulk["kind"], bulk_plan(selected, ai_cards), len(selected),
                                  bulk.get("target", "")))
    if any(not c.capability for c in ai_cards):
        above.append(
            dmc.Button(
                "Re-check the No capability fits programs against the new list",
                id=queue_button_id(Q_RECHECK),
                size="xs",
                variant="default",
                disabled=disabled,
                mb="xs",
            )
        )
    items, shown, total = review_items(queue, capability_names, disabled, rf, selected)
    paths = [*(r.path for r in rows), *(c.path for c in ai_cards)]
    parts: list = [
        review_pane(
            rf, top_folders(paths), shown, total, items, above,
            bulk_bar(selected, ai_cards, capability_names, disabled), disabled,
        )
    ]
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
    waiting = len(rows) + len(ai_cards) + len(suggested)
    return admin_card("Review queue", html.Div(parts), "📥", count=waiting, id=QUEUE_BLOCK_ID)


def review_items(queue: dict, capability_names: list[str], disabled: bool, rf, selected: list):
    """The cards inside the scrolling box after the filter, and (shown, total)."""
    rows = queue["rows"]
    ai_cards = queue.get("ai_cards", [])
    suggested = queue.get("suggestions", [])
    open_name = queue.get("suggest_dialog")
    total = len(rows) + len(ai_cards) + len(suggested)
    if not total:
        return [dmc.Text("No Unassigned files are waiting.", style=da_styles.EMPTY_TEXT)], 0, 0
    shown_rows = filter_requests(rows, rf)
    shown_suggestions = filter_suggestions(suggested, rf)
    shown_cards = filter_ai_cards(ai_cards, rf)
    items: list = []
    if shown_rows:
        items.append(dmc.Text("From a request", size="xs", fw=600, c=da_styles.MUTED))
        items.extend(_queue_card(r, capability_names, disabled) for r in shown_rows)
    items.extend(
        _suggestion_card(s, capability_names, disabled, s.name == open_name)
        for s in shown_suggestions
    )
    if shown_cards:
        items.append(dmc.Text("From the AI scan", size="xs", fw=600, c=da_styles.MUTED))
    items.extend(
        _ai_card(c, capability_names, disabled, c.path in selected) for c in shown_cards
    )
    return items, len(shown_rows) + len(shown_suggestions) + len(shown_cards), total


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


def _ai_confirm_box(cards, confirm: dict | None, disabled: bool) -> list:
    """The Approve all button, or its confirm box, when sure proposals exist (above the list).
    A card's path rides in the button id's `uid` (rows from a request use a number there)."""
    sure = [c for c in cards if c.confidence == "high" and c.capability]
    parts: list = []
    if confirm:
        lines = ", ".join(f"{name}: {n}" for name, n in confirm["counts"].items())
        waiting = confirm.get("suggestions", 0)  # S5: suggestions are never approved in bulk
        extra = f". {waiting} new-capability suggestions wait for your review." if waiting else ""
        parts.append(
            dmc.Paper(
                [
                    dmc.Text(
                        f"Approve {sum(confirm['counts'].values())} programs? {lines}{extra}",
                        size="sm",
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
    return parts


def _ai_card(card, capability_names: list[str], disabled: bool, checked: bool = False):
    """One AI scan card, compact (L8): line 1 path, arrow, pills and actions; line 2 the summary
    on one line (full text on hover); the AI's reason only under "Why?"."""
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
    return html.Div(
        [
            dmc.Group(
                [
                    dmc.Checkbox(
                        id={"type": RQ_SEL_TYPE, "path": card.path}, checked=checked, size="xs",
                        disabled=disabled,
                    ),
                    dmc.Code(card.path, style=admin_styles.REVIEW_PATH),  # never cut, wraps
                    dmc.Text(f"→ {target}", size="sm", fw=600),
                    dmc.Badge(card.confidence, variant="light", tt="none"),
                    dmc.Group(buttons, gap="xs", ml="auto"),
                ],
                gap="xs",
            ),
            html.Div(card.summary, title=card.summary, style=admin_styles.REVIEW_SUMMARY),
            html.Details(
                [
                    html.Summary("Why?", style={"fontSize": "12px", "cursor": "pointer"}),
                    dmc.Text(card.reason, size="xs", style=da_styles.EMPTY_TEXT),
                ]
            ),
        ],
        style=admin_styles.REVIEW_ROW,
    )


def _suggestion_card(sug, capability_names: list[str], disabled: bool, dialog_open: bool):
    """S4: "New capability suggested: <name>" with its programs. Never created by itself."""
    chips = [
        dmc.Group(
            [
                _chip(path, summary),
                dmc.Button(
                    "Remove",
                    id=queue_button_id(Q_SG_REMOVE, path),
                    size="compact-xs",
                    variant="subtle",
                    disabled=disabled,
                ),
            ],
            gap=2,
        )
        for path, summary in sug.modules.items()
    ]
    key = sug.name
    buttons = [
        dmc.Button(
            "Create and assign", id=queue_button_id(Q_SG_OPEN, key), size="xs", disabled=disabled
        ),
        dmc.Select(
            data=capability_names,
            id={"type": QUEUE_PICK_TYPE, "uid": key},
            size="xs",
            w=150,
            disabled=disabled,
        ),
        dmc.Button(
            "Assign to",
            id=queue_button_id(Q_SG_ASSIGN, key),
            size="xs",
            variant="default",
            disabled=disabled,
        ),
        dmc.Button(
            "Reject",
            id=queue_button_id(Q_SG_REJECT, key),
            size="xs",
            variant="default",
            color="red",
            disabled=disabled,
        ),
    ]
    parts = [
        dmc.Group(
            [
                dmc.Badge("New capability suggested", variant="light", tt="none"),
                dmc.Text(sug.name, size="sm", fw=600),
                dmc.Badge(sug.confidence, variant="light", tt="none"),
            ],
            gap="xs",
        ),
        dmc.Text(sug.description, size="sm"),
        dmc.Group(chips, gap="xs"),
        html.Div(dmc.Group(buttons, gap="xs"), style={"marginTop": "8px"}),
    ]
    if dialog_open:
        parts.append(_suggestion_dialog(sug))
    return dmc.Paper(parts, withBorder=True, p="sm", mb="xs")


def _suggestion_dialog(sug):
    """Name and description to edit, senior and backup senior (empty allowed), then Save."""

    def field(name: str, label: str, value: str = ""):
        return dmc.TextInput(
            label=label,
            value=value,
            size="xs",
            id={"type": QUEUE_NOTE_TYPE, "uid": f"{sug.name}|{name}"},
        )

    return dmc.Alert(
        [
            field("name", "Capability name", sug.name),
            field("desc", "Description", sug.description),
            field("named", "Named senior"),
            field("backup", "Backup senior (optional)"),
            dmc.Group(
                [
                    dmc.Button(
                        f"Save ({len(sug.modules)} programs)",
                        id=queue_button_id(Q_SG_SAVE, sug.name),
                        size="xs",
                    ),
                    dmc.Button("Cancel", id=queue_button_id(Q_CANCEL), size="xs", variant="subtle"),
                ],
                mt="xs",
            ),
        ],
        color="blue",
        mt="xs",
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
