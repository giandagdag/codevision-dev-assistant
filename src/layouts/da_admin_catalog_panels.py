"""Catalog edit panels (Fix G4 L2, L3): the patterns side panel and the Add modules pop-up.

Both are drawn from the server on a click and closed by the next re-draw, like the queue dialogs.
"""

import dash_mantine_components as dmc
from dash import html

from agents.da_admin_modules import (
    count_matches,
    example_pattern,
    first_matches,
    is_exact,
    module_rows,
    split_patterns,
)
from layouts.da_admin_common import pat_id
from pydantic_classes.da_rulebook_models import Capability
from styles import da_styles

MOD_TYPE = "adm-mod"  # inputs read back when Add pattern or Add modules is clicked
NEW_PATTERN_ID = {"type": MOD_TYPE, "name": "newpat"}
HINT_ID = "adm-pat-hint"  # live "matches N modules" under the Add pattern field
MOD_CAP_ID = {"type": MOD_TYPE, "name": "cap"}
MOD_PICKED_ID = {"type": MOD_TYPE, "name": "picked"}
MOD_SEARCH_ID, MOD_UNASSIGNED_ID = "adm-modf-search", "adm-modf-unassigned"
MOD_SUMMARY_ID, MOD_ALL_ID = "adm-modf-summary", "adm-modf-all"
MOD_TABLE_ID = "adm-modf-table"
PATTERN_HELP = (
    "Paths start inside the source folder. Use / between folders. "
    "* matches anything, including sub-folders. Case does not matter."
)


def hint_text(pattern: str, paths: list[str]) -> str:
    """The live hint under the Add pattern field."""
    if not (pattern or "").strip():
        return ""
    n = count_matches(pattern, paths)
    if n == 0:
        return "Matches nothing yet. Use Save anyway to keep it."
    shown = ", ".join(first_matches(pattern, paths))
    return f"matches {n} module{'' if n == 1 else 's'}: {shown}" + (" ..." if n > 5 else "")


def patterns_panel(tab: str, index: int, name: str, patterns_text: str, paths: list[str]):
    """Side panel for one capability: a row per pattern, then the Add pattern field and Save."""
    rows = [
        # A grid, not a flowing group: Remove sits at the same left in every row (G5 L2, L4).
        html.Div(
            [
                dmc.Badge("Exact file" if is_exact(p) else "Pattern", variant="light", tt="none"),
                dmc.Code(p, style={"overflowWrap": "anywhere"}),
                dmc.Text(f"{count_matches(p, paths)} modules", size="xs", c=da_styles.MUTED),
                dmc.Button(
                    "Remove",
                    id=pat_id(tab, "remove", index, p),
                    variant="subtle",
                    color="red",
                    size="compact-xs",
                ),
            ],
            style={
                "display": "grid", "gridTemplateColumns": "90px 1fr 90px 80px",
                "gap": "8px", "alignItems": "center", "marginBottom": "4px",
            },
        )
        for p in split_patterns(patterns_text)
    ]
    body = [
        *(rows or [dmc.Text("No patterns yet.", style=da_styles.EMPTY_TEXT)]),
        dmc.TextInput(
            id=NEW_PATTERN_ID,
            label="Add pattern",
            placeholder=example_pattern(paths),
            description=PATTERN_HELP,
            size="xs",
            mt="sm",
        ),
        dmc.Text("", id=HINT_ID, size="xs", c=da_styles.MUTED),
        dmc.Group(
            [
                dmc.Button(
                    "Add pattern", id=pat_id(tab, "add", index), size="xs", variant="default"
                ),
                dmc.Button("Save", id=pat_id(tab, "save", index), size="xs"),
                dmc.Button(
                    "Save anyway", id=pat_id(tab, "force", index), size="xs", variant="default"
                ),
                dmc.Button("Close", id=pat_id(tab, "close", index), size="xs", variant="subtle"),
            ],
            mt="sm",
        ),
    ]
    return dmc.Drawer(
        html.Div(body), opened=True, position="right", size="lg", title=f"Patterns: {name}"
    )


def modules_table(
    capabilities: list[Capability],
    paths: list[str],
    summaries: dict[str, str],
    target: str,
    search: str = "",
    unassigned_only: bool = True,
    show_summary: bool = False,
    picked: list[str] | None = None,
):
    """The module rows as a check list. A module that belongs to another capability says so."""
    rows = module_rows(capabilities, paths, summaries, target, search, unassigned_only)
    shown = {r["path"] for r in rows}
    body = []
    for r in rows:
        where = f"moves from {r['moves_from']}" if r["moves_from"] else r["current"]
        cells = [
            dmc.TableTd(dmc.Checkbox(value=r["path"], size="xs")),
            dmc.TableTd(dmc.Code(r["path"]), style={"wordBreak": "break-all"}),  # never cut
            dmc.TableTd(dmc.Text(where or "unassigned", size="xs", c=da_styles.MUTED)),
        ]
        if show_summary:
            cells.append(dmc.TableTd(dmc.Text(r["summary"], size="xs")))
        body.append(dmc.TableTr(cells))
    heads = ["", "Module", "Capability", *(["AI summary"] if show_summary else [])]
    table = dmc.Table(
        [dmc.TableThead(dmc.TableTr([dmc.TableTh(h) for h in heads])), dmc.TableTbody(body)]
    )
    keep = [p for p in (picked or []) if p in shown]
    empty = [] if rows else [dmc.Text("No modules match.", style=da_styles.EMPTY_TEXT)]
    return html.Div([dmc.CheckboxGroup(table, id=MOD_PICKED_ID, value=keep), *empty])


MOVE_LABEL = "Move here"  # M3: moves the exact pattern from its old capability
ALSO_ADD_LABEL = "Also add here"  # M3: keeps the other capability


def add_label(count: int, target: str) -> str:
    return f"{MOVE_LABEL}: {count} module{'' if count == 1 else 's'} to {target or '...'}"


def modules_modal(
    tab: str,
    capabilities: list[Capability],
    paths: list[str],
    summaries: dict[str, str],
    target: str,
):
    """The Add modules pop-up (about 70% wide): picker, search, two switches, the module table."""
    names = [c.name for c in capabilities]
    controls = dmc.Group(
        [
            dmc.Select(
                id=MOD_CAP_ID,
                data=names,
                value=target or None,
                label="Add to",
                size="xs",
                searchable=True,
            ),
            dmc.TextInput(
                id=MOD_SEARCH_ID,
                placeholder="Search path or summary",
                size="xs",
                debounce=True,
                w=260,
            ),
            dmc.Switch(id=MOD_UNASSIGNED_ID, label="Unassigned only", checked=True, size="xs"),
            dmc.Switch(id=MOD_SUMMARY_ID, label="Show AI summary", checked=False, size="xs"),
            dmc.Button("Select all shown", id=MOD_ALL_ID, size="xs", variant="default"),
        ],
        align="end",
        mb="sm",
    )
    return dmc.Modal(
        [
            controls,
            html.Div(
                modules_table(capabilities, paths, summaries, target),
                id=MOD_TABLE_ID,
                style={"maxHeight": "55vh", "overflowY": "auto"},
            ),
            dmc.Group(
                [
                    dmc.Button(add_label(0, target), id=pat_id(tab, "addmods"), size="xs"),
                    dmc.Button(
                        ALSO_ADD_LABEL, id=pat_id(tab, "alsomods"), size="xs", variant="default"
                    ),
                    dmc.Button("Close", id=pat_id(tab, "close"), size="xs", variant="subtle"),
                ],
                mt="sm",
            ),
        ],
        opened=True,
        size="70%",
        title="Browse modules",
    )
