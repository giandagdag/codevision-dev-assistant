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


def window(title: str, body, **paper):
    """A bordered card with a bold title: one per area of a read view (Gian, 17 Nov: "a window for
    each section" instead of everything on the white canvas)."""
    return dmc.Paper(
        [dmc.Text(title, fw=700, c=da_styles.NAVY, mb="xs"), body],
        withBorder=True,
        p="md",
        radius="md",
        **paper,
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


TEXT_COLUMN = "text"  # a one-column table holds a list of plain strings
MOVE_TYPE = "adm-move"
SEVERITY_WORDS = {"must_fix": "Must fix", "should_fix": "Should fix", "fyi": "FYI"}


def _plain(text: str) -> str:
    return SEVERITY_WORDS.get(text, text)


# --- Shared list table (zones, protected files, glossary, charter lists; 11b reuses it) ---


CODE_COLUMNS = ("good_example", "bad_example", "code")  # drawn in a code box in the read view
READONLY = "readonly"  # a cell kind: a disabled input that is still read back like any cell


def list_table(
    tab: str,
    table_id: str,
    columns: tuple[str, ...],
    rows: list[dict],
    editable: bool,
    kinds: dict | None = None,
    static: tuple[str, ...] = (),
    movable: bool = False,
):
    """A table drawn from column names. Read mode is plain text; edit mode adds Add row and Remove.

    Edit cells carry pattern-matching ids so the callbacks can read them back.
    `kinds` says a column is READONLY or a dropdown (a list of choices). A `static` column is plain
    text in both modes and is never read back (the Cited counts).
    """
    kinds = kinds or {}
    head = dmc.TableThead(
        dmc.TableTr([dmc.TableTh(col.replace("_", " ").capitalize()) for col in columns])
    )
    body = dmc.TableTbody(
        [
            _table_row(tab, table_id, columns, i, row, editable, kinds, static, movable)
            for i, row in enumerate(rows)
        ]
    )
    parts: list = [dmc.Table([head, body], withTableBorder=True, withColumnBorders=True)]
    if not rows:
        parts.append(dmc.Text("Nothing here yet.", style=da_styles.EMPTY_TEXT))
    if editable:
        parts.append(
            dmc.Button(
                "Add row",
                id={"type": "adm-add", "tab": tab, "table": table_id, "index": 0},
                variant="default",
                size="xs",
                mt="xs",
            )
        )
    return html.Div(parts)


def _table_row(tab, table_id, columns, index, row, editable, kinds, static, movable=False):
    cells = []
    for col in columns:
        value = _cell_text(row.get(col, ""))
        if editable and col not in static:
            cell_id = {
                "type": "adm-cell",
                "tab": tab,
                "table": table_id,
                "row": index,
                "col": col,
            }
            kind = kinds.get(col)
            if kind == READONLY:
                widget = dmc.TextInput(value=value, id=cell_id, disabled=True, size="xs")
            elif kind:
                widget = dmc.Select(
                    data=kind, value=value or None, id=cell_id, size="xs", searchable=True
                )
            else:
                widget = dmc.Textarea(value=value, id=cell_id, autosize=True, minRows=1, size="xs")
            cells.append(dmc.TableTd(widget))
        else:
            shown = _plain(value) if col == "severity" else value
            if col in CODE_COLUMNS or table_id == "protected_files":  # code and paths: code box
                cells.append(dmc.TableTd(dmc.Code(shown, block=True)))
            else:
                cells.append(
                    dmc.TableTd(dmc.Text(shown, size="sm", style={"whiteSpace": "pre-wrap"}))
                )
    if editable:
        buttons = [
            dmc.Button(
                "Remove",
                id={"type": "adm-remove", "tab": tab, "table": table_id, "index": index},
                variant="subtle",
                color="red",
                size="xs",
            )
        ]
        if movable:
            for label, step in (("Move up", -1), ("Move down", 1)):
                move_id = {
                    "type": MOVE_TYPE,
                    "tab": tab,
                    "table": table_id,
                    "index": index,
                    "step": step,
                }
                buttons.append(dmc.Button(label, id=move_id, variant="default", size="xs"))
        cells.append(dmc.TableTd(dmc.Group(buttons, gap="xs") if movable else buttons[0]))
    return dmc.TableTr(cells)


def _cell_text(value) -> str:
    # A list cell (examples, path patterns) is one item per line.
    return "\n".join(value) if isinstance(value, list) else str(value)


def _text_rows(items) -> list[dict]:
    return [{TEXT_COLUMN: item} for item in items]


def _draft(draft: dict | None, key: str, default):
    return default if draft is None or key not in draft else draft[key]
