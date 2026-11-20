"""What every Admin tab shares (fix 11-1, section 14): tab names, ids, the version pill, the grid.

Tab files (da_admin_*_tab.py) import this file and never da_admin_page.py, so the two never wait
for each other to load (a circular import). Presentation only, like the rest of layouts/.
"""

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
        **{"style": {"flex": 1}, **paper},  # fills its aligned_row cell
    )


def aligned_row(left, right):
    """One row of a read view: two windows, left 2/3 and right 1/3, the same height. Every row of a
    tab uses the same split, so the window edges line up from top to bottom (Gian, 17 Nov)."""
    cell = {"minWidth": 0, "display": "flex", "flexDirection": "column", "gap": "16px"}
    return html.Div(
        [html.Div(left, style=cell), html.Div(right, style=cell)],  # right may be a list: stacked
        style={
            "display": "grid",
            "gridTemplateColumns": "minmax(0, 2fr) minmax(0, 1fr)",
            "gap": "16px",
            "alignItems": "stretch",
            "marginTop": "16px",
        },
    )


def full_row(content):
    """A full-width row under aligned rows: the same outer edges, for wide tables."""
    return html.Div(content, style={"marginTop": "16px"})


def chips(summary: str):
    """A summary line such as "3 capabilities, 2 Unassigned" as small chips."""
    parts = [p.strip() for p in summary.replace(";", ",").split(",") if p.strip()]
    return dmc.Group([dmc.Badge(p, variant="outline", tt="none") for p in parts], gap=4)


def word_chips(words: list[str], style: dict | None = None, variant: str = "light"):
    """One small chip per word (folders, markers, libraries). `style` colours them; paths use
    variant "outline" (the code-chip look the label scan skips)."""
    if not words:
        return dmc.Text("None.", style=da_styles.EMPTY_TEXT)
    return dmc.Group([dmc.Badge(w, variant=variant, tt="none", style=style) for w in words], gap=4)


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


HEADER_VERSION_ID = "da-admin-header-version"


def _version_text(version, active: bool) -> html.Span:
    """Dot, "Active rulebook vN" and "Published <when>, <who>" on one quiet line."""
    saved: datetime = version.saved_at
    dot = admin_styles.GREEN if active else da_styles.MUTED
    title = (
        f"Active rulebook v{version.version_number}"
        if active
        else (f"Started from v{version.version_number}")
    )
    return dmc.Group(
        [
            html.Span(
                style={
                    "width": "8px",
                    "height": "8px",
                    "borderRadius": "50%",
                    "background": dot,
                    "display": "inline-block",
                }
            ),
            dmc.Text(title, size="sm", fw=600, c=da_styles.NAVY),
            dmc.Text(
                f"Published {saved:%Y-%m-%d %H:%M}, {version.saved_by}",
                size="xs",
                c=da_styles.MUTED,
            ),
        ],
        gap=8,
        wrap="nowrap",
    )


def header_version(version) -> html.Div:
    """The active version, once, on the right of the "Admin console" title (Gian, 18 Nov).

    No View history button: the Version history tab is right there. A callback redraws it after
    every save or restore, so it never shows an old number."""
    return html.Div(_version_text(version, True), id=HEADER_VERSION_ID)


def version_pill(version, active: bool = True):
    """Inside a tab only when it matters: a stale edit form says "Started from vN" (grey dot).
    The active version lives in the page header (header_version), so this returns None then."""
    if active:
        return None
    right = {"display": "flex", "justifyContent": "flex-end", "marginBottom": "8px"}
    return html.Div(_version_text(version, False), style=right)


TEXT_COLUMN = "text"  # a one-column table holds a list of plain strings
MOVE_TYPE = "adm-move"
SEVERITY_WORDS = {"must_fix": "Must fix", "should_fix": "Should fix", "fyi": "FYI"}


def _plain(text: str) -> str:
    return SEVERITY_WORDS.get(text, text)


# --- Shared list table (zones, protected files, glossary, charter lists; 11b reuses it) ---


CODE_COLUMNS = ("good_example", "bad_example", "code")  # drawn in a code box in the read view
READONLY = "readonly"  # a cell kind: a disabled input that is still read back like any cell
PAT_TYPE = "adm-pat"  # id type of the patterns panel and Add modules buttons
PATTERNS = "patterns"  # a cell kind: a count chip that opens the patterns side panel


def list_table(
    tab: str,
    table_id: str,
    columns: tuple[str, ...],
    rows: list[dict],
    editable: bool,
    kinds: dict | None = None,
    static: tuple[str, ...] = (),
    movable: bool = False,
    widths: dict[str, str] | None = None,
    input_height: str = "",
    marker: str = "",
):
    """A table drawn from column names. Read mode is plain text; edit mode adds Add row and Remove.

    `marker` ("tick", "dot" or "number") turns a one-column list into rows with thin dividers and
    no header (Fix G4 L6); edit mode keeps the same inputs, Add row and Remove.

    Edit cells carry pattern-matching ids so the callbacks can read them back.
    `kinds` says a column is READONLY, PATTERNS or a dropdown (a list of choices). A `static`
    column is plain text in both modes and is never read back (the Cited counts).
    `widths` (column -> "18%", "actions" for the buttons) fixes the layout; `input_height` gives
    every edit input the same height (Fix G4 L1).
    """
    kinds = kinds or {}
    heads = [
        dmc.TableTh(col.replace("_", " ").capitalize(), w=(widths or {}).get(col))
        for col in columns
    ]
    if widths and editable:
        heads.append(dmc.TableTh("", w=widths.get("actions")))
    head = dmc.TableThead(dmc.TableTr(heads))
    if marker and not editable:
        return html.Div(_marker_rows(rows, marker) or _empty_note())
    body = dmc.TableTbody(
        [
            _table_row(
                tab, table_id, columns, i, row, editable, kinds, static, movable, input_height
            )
            for i, row in enumerate(rows)
        ]
    )
    style = {"tableLayout": "fixed"} if widths else None
    table = [body] if marker else [head, body]  # a marker list has no "Text" header
    parts: list = [dmc.Table(table, withTableBorder=True, withColumnBorders=True, style=style)]
    if not rows:
        parts.append(_empty_note())
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


def _empty_note():
    return dmc.Text("Nothing here yet.", style=da_styles.EMPTY_TEXT)


def _marker_rows(rows: list[dict], marker: str) -> list:
    """Read-only list rows: a green tick, a red dot or a small number, then the text."""
    out = []
    for i, row in enumerate(rows, 1):
        if marker == "tick":
            mark = html.Span("✓", style={"color": "#2B8A3E", "fontWeight": 700})
        elif marker == "dot":
            mark = html.Span("●", style={"color": "#C92A2A"})
        else:
            mark = html.Span(str(i), style={"color": "#667085", "fontSize": "12px"})
        out.append(
            html.Div(
                [
                    html.Span(mark, style={"width": "24px", "flexShrink": 0}),
                    dmc.Text(_cell_text(row.get(TEXT_COLUMN, "")), size="sm"),
                ],
                style={
                    "display": "flex",
                    "gap": "8px",
                    "padding": "8px 0",
                    "borderBottom": "1px solid #E3E7EE",
                },
            )
        )
    return out


def pat_id(tab: str, action: str, index: int = 0, pat: str = "") -> dict:
    """A button of the patterns side panel (Fix G4 L2). One id shape for one callback."""
    return {"type": PAT_TYPE, "tab": tab, "action": action, "index": index, "pat": pat}


def _table_row(
    tab, table_id, columns, index, row, editable, kinds, static, movable=False, input_height=""
):
    cells = []
    same = {"styles": {"input": {"height": input_height, "minHeight": input_height}}}
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
            extra = same if input_height else {}
            if kind == READONLY:
                widget = dmc.TextInput(value=value, id=cell_id, disabled=True, size="xs", **extra)
            elif kind == PATTERNS:
                # The text stays in a hidden box so Save still reads it; the chip opens the panel.
                count = len([line for line in value.splitlines() if line.strip()])
                widget = html.Div(
                    [
                        dmc.Button(
                            f"{count} pattern{'' if count == 1 else 's'}",
                            id=pat_id(tab, "open", index),
                            variant="light",
                            size="compact-xs",
                        ),
                        html.Div(dmc.Textarea(value=value, id=cell_id), style={"display": "none"}),
                    ]
                )
            elif kind:
                widget = dmc.Select(
                    data=kind, value=value or None, id=cell_id, size="xs", searchable=True, **extra
                )
            elif input_height:
                widget = dmc.Textarea(value=value, id=cell_id, autosize=False, size="xs", **extra)
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
