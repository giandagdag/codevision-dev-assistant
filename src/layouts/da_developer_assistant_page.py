"""What is on the Developer Assistant screen: the Home page and the request workspace.

Presentation only (rule R12). Every function here turns data that the 2A engine already
prepared into components; nothing here decides a status, a question or a check. Think of it as
the display file (DDS) of a 5250 program: it says where each field goes, not what it means.
"""

import dash_mantine_components as dmc
from dash import dcc
from dash_iconify import DashIconify

from agents.da_understand_checks import MAX_MESSAGE_LENGTH
from agents.da_understand_flow import HELP_OPTION, PROCEED_OPTION
from pydantic_classes.da_models import Request
from pydantic_classes.da_request_record_models import UnderstandView
from styles import da_styles
from web import da_web_components as parts

# Ids the callbacks use. Dictionary ids are CodeVision's habit for repeated components.
LOCATION_ID = "url"  # the page's dcc.Location; at work this is CodeVision's own (spec Q6)
PAGE_CONTENT_ID = "da-page-content"
REFRESH_ID = "da-refresh"
STATE_ID = "da-workspace-state"
TEXT_ID = "da-text"
SEND_ID = "da-send"
SKIP_ID = "da-skip"
MESSAGE_ID = "da-message"
CHOICE_TYPE = "da-choice"
KEYS_ID = "da-keys-ready"  # target of the Enter-to-send script; holds nothing

CODE_BANNER = "No code is generated in Phase 1"  # the demo's wording (its own numbering)
DEMO_BANNER = "Demo mode: replies are scripted"
EMPTY_TEXT = "Waiting for your answer"
UNDERSTAND_STEP = 1

# The other tabs exist on the demo but belong to later phases: shown greyed out.
PANEL_TABS: tuple[tuple[str, str], ...] = (
    ("Summary", "tabler:clipboard-list"),
    ("Discovery", "tabler:search"),
    ("Gate", "tabler:traffic-lights"),
    ("Code", "tabler:settings"),
    ("Review", "tabler:shield-check"),
    ("Audit", "tabler:receipt"),
)


def layout() -> list:
    """The page itself. The content is filled in by the callbacks, from the URL."""
    return [
        dcc.Store(id=REFRESH_ID, data=0),
        dcc.Store(id=KEYS_ID),
        dmc.Box(id=PAGE_CONTENT_ID, style=da_styles.PAGE),
    ]


# --- Home ---


def render_home(requests: list[Request]) -> list:
    return [
        dmc.Title("Developer Assistant", order=2, c=da_styles.NAVY),
        dmc.Text("Start a new change, or get your own code reviewed.", c=da_styles.MUTED, mb="md"),
        dmc.SimpleGrid(
            [
                dcc.Link(
                    _entry_card(
                        "tabler:message-circle",
                        "Start a change request",
                        "Describe what you need in plain words. I'll clarify it step by step.",
                    ),
                    href="?new=1",
                    id="da-start-card",
                    style={"textDecoration": "none"},
                ),
                _entry_card(
                    "tabler:shield-check",
                    "Review my code",
                    "Coming in a later phase",
                    disabled=True,
                ),
            ],
            cols=2,
            mb="lg",
        ),
        dmc.Paper(
            [
                dmc.Text("My recent requests", fw=700, c=da_styles.NAVY, mb="sm"),
                _requests_table(requests),
            ],
            withBorder=True,
            radius="md",
            p="md",
        ),
    ]


def _entry_card(icon: str, title: str, text: str, disabled: bool = False) -> dmc.Paper:
    return dmc.Paper(
        [
            DashIconify(icon=icon, width=28, color=da_styles.MUTED if disabled else da_styles.BLUE),
            dmc.Text(title, fw=700, size="lg", c=da_styles.MUTED if disabled else da_styles.NAVY),
            dmc.Text(text, size="sm", c=da_styles.MUTED),
        ],
        withBorder=True,
        radius="md",
        p="lg",
        opacity=0.6 if disabled else 1,
    )


def _requests_table(requests: list[Request]):
    if not requests:
        return dmc.Text("No requests yet. Start one above.", c=da_styles.MUTED, size="sm")
    header = dmc.TableThead(
        dmc.TableTr([dmc.TableTh("Request"), dmc.TableTh("Title"), dmc.TableTh("Status")])
    )
    rows = [
        dmc.TableTr(
            [
                dmc.TableTd(_row_link(request, request.request_id)),
                dmc.TableTd(_row_link(request, request.title)),
                dmc.TableTd(_row_link(request, parts.status_pill(request.status))),
            ]
        )
        for request in requests
    ]
    return dmc.Table([header, dmc.TableTbody(rows)], highlightOnHover=True)


def _row_link(request: Request, content) -> dcc.Link:
    # Every cell links to the same request, so a click anywhere on the row resumes it.
    return dcc.Link(
        content,
        href=f"?request={request.request_id}",
        style={"textDecoration": "none", "color": "inherit", "display": "block"},
    )


def render_message_page(text: str) -> list:
    """A plain message with a way back, for example a request that does not exist."""
    return [
        dmc.Text(text, c="red", mb="md"),
        dcc.Link("Back to Home", href="?", id="da-back-home"),
    ]


# --- Workspace ---


def render_workspace(view: UnderstandView) -> list:
    return _workspace(
        title=view.request.title,
        request_id=view.request.request_id,
        status=view.request.status,
        demo_mode=view.demo_mode,
        messages=[parts.chat_bubble(message) for message in view.messages],
        composer=_composer(view.input_mode, view.choices, view.can_skip, view.prompt),
        panel=_summary_panel(view),
        state={"request_id": view.request.request_id, "revision": view.revision},
    )


def render_new_workspace(demo_mode: bool) -> list:
    """The blank workspace. The first message creates the request (spec 3.2 step 1)."""
    return _workspace(
        title="New change request",
        request_id=None,
        status="DRAFT",
        demo_mode=demo_mode,
        messages=[
            dmc.Text(
                "Describe the change you need in plain words. I'll ask a few short questions "
                "before anything is built.",
                c=da_styles.MUTED,
                size="sm",
                p="md",
            )
        ],
        composer=_composer("text", [], False, ""),
        panel=_summary_panel(None),
        state={"request_id": None, "revision": None},
    )


def _workspace(title, request_id, status, demo_mode, messages, composer, panel, state) -> list:
    top = dmc.Group(
        [
            dmc.Group(
                [
                    dcc.Link(
                        dmc.Group([DashIconify(icon="tabler:arrow-left", width=16), "Home"], gap=4),
                        href="?",
                        id="da-home-link",
                        style={"textDecoration": "none", "color": da_styles.MUTED},
                    ),
                    dmc.Text(title, fw=700, size="xl", c=da_styles.NAVY),
                    dmc.Code(request_id) if request_id else None,
                ]
            ),
            parts.status_pill(status),
        ],
        justify="space-between",
        mb="sm",
    )
    chat_head = dmc.Group(
        [
            dmc.Text("Developer Assistant chat", fw=600, c=da_styles.NAVY),
            dmc.Badge(CODE_BANNER, color="orange", variant="light", leftSection=_lock()),
        ],
        justify="space-between",
        p="sm",
        style={"borderBottom": f"1px solid {da_styles.LINE}"},
    )
    chat = dmc.Paper(
        [
            chat_head,
            dmc.Alert(DEMO_BANNER, color="violet", variant="light", m="sm", p="xs")
            if demo_mode
            else None,
            dmc.Box(
                dmc.Box(messages, style=da_styles.CHAT_MESSAGES),
                id="da-chat-scroll",
                style=da_styles.CHAT_SCROLL,
            ),
            dmc.Text("", id=MESSAGE_ID, c="red", size="sm", px="md", **{"aria-live": "assertive"}),
            composer,
        ],
        withBorder=True,
        radius="md",
        style=da_styles.COLUMN,
    )
    side = dmc.Paper(
        [
            dmc.Tabs(
                dmc.TabsList(
                    [
                        dmc.TabsTab(
                            name,
                            value=name.lower(),
                            leftSection=DashIconify(icon=icon, width=16),
                            disabled=name != "Summary",
                            px="xs",
                        )
                        for name, icon in PANEL_TABS
                    ],
                    # All six tabs stay on one line; a narrow window scrolls them sideways.
                    style={"flexWrap": "nowrap", "overflowX": "auto"},
                ),
                value="summary",
            ),
            dmc.Box(panel, style=da_styles.PANEL_BODY),
        ],
        withBorder=True,
        radius="md",
        style=da_styles.COLUMN,
    )
    return [
        dcc.Store(id=STATE_ID, data=state),
        parts.stepper(UNDERSTAND_STEP),
        dmc.Box(top, mt="sm"),
        dmc.Box([chat, side], style=da_styles.WORKSPACE_GRID),
    ]


def _lock():
    return DashIconify(icon="tabler:lock", width=12)


# --- The composer: text, locked choices, waiting, done ---


def _composer(mode: str, choices: list[str], can_skip: bool, prompt: str) -> dmc.Box:
    """The bottom of the chat. The text box, Send and Skip always exist (the callbacks name
    them); the mode decides which ones can be used."""
    text_open = mode == "text"
    paused = {
        "choices": "Text input is paused until you choose",
        "waiting": prompt,
        "done": "This request is confirmed. It cannot be changed in this phase.",
    }.get(mode, "")
    controls = dmc.Box(
        [
            dmc.Textarea(
                id=TEXT_ID,
                placeholder="Type your message..." if text_open else paused,
                disabled=not text_open,
                autosize=True,
                minRows=2,
                maxRows=6,
                inputProps={"maxLength": MAX_MESSAGE_LENGTH},
            ),
            dmc.Group(
                [
                    dmc.Button(
                        "Skip",
                        id=SKIP_ID,
                        variant="default",
                        style={} if can_skip else {"display": "none"},
                    ),
                    dmc.Button(
                        "Send",
                        id=SEND_ID,
                        disabled=not text_open,
                        leftSection=DashIconify(icon="tabler:send", width=16),
                    ),
                ],
                justify="flex-end",
                mt="xs",
            ),
        ],
        style=da_styles.COMPOSER,
    )
    if mode == "choices":
        return dmc.Box([_choices_bar(choices), controls])
    if mode == "done":
        return dmc.Box(
            [
                dmc.Box(
                    dmc.Button("Proceed to Discovery (coming in Phase 3)", disabled=True),
                    style=da_styles.CHOICES_BAR,
                    pb="xs",
                ),
                controls,
            ]
        )
    return controls


def _choices_bar(choices: list[str]) -> dmc.Box:
    buttons = [
        dmc.Button(
            option,
            id={"type": CHOICE_TYPE, "option": option},
            variant="filled" if option == PROCEED_OPTION else "light",
            color="gray" if option == HELP_OPTION else "blue",
            radius="xl",
            size="sm",
        )
        for option in choices
    ]
    return dmc.Box(
        [
            dmc.Group([_lock(), dmc.Text("Choose an option to continue", size="xs", fw=600)]),
            dmc.Group(buttons, mt="xs", mb="xs"),
        ],
        style=da_styles.CHOICES_BAR,
    )


# --- The Summary tab ---


def _summary_panel(view: UnderstandView | None) -> list:
    """The live summary. Fields changed by the last answer are highlighted."""
    record = view.record if view else None
    changed = set(view.changed_fields) if view else set()
    text = view.progress_text if view else "0 of 4 mandatory questions answered"
    answered = view.answered_count if view else 0
    warn = text.startswith("Clarification required")

    def value(name: str) -> str:
        return getattr(record, name) if record else ""

    def items(name: str) -> list:
        return list(getattr(record, name)) if record else []

    assumptions = [f"{a.text} (basis: {a.basis})" for a in record.assumptions] if record else []
    return [
        parts.progress_segments(answered, text, warn),
        parts.panel_section(
            "Requirement summary",
            [
                _text_field("Objective", value("objective"), "objective" in changed),
                _text_field("Reason", value("reason"), "reason" in changed),
                _text_field(
                    "Current behaviour", value("current_behaviour"), "current_behaviour" in changed
                ),
                _text_field(
                    "Expected behaviour",
                    value("expected_behaviour"),
                    "expected_behaviour" in changed,
                ),
            ],
        ),
        parts.panel_section(
            "Scope",
            [
                _list_field("In scope", items("in_scope"), "in_scope" in changed, "tabler:check"),
                _list_field(
                    "Out of scope", items("out_of_scope"), "out_of_scope" in changed, "tabler:ban"
                ),
            ],
        ),
        parts.panel_section(
            "Inputs and outputs",
            [
                _text_field("Input", value("inputs"), "inputs" in changed),
                _text_field("Output", value("outputs"), "outputs" in changed),
            ],
        ),
        parts.panel_section(
            "Important scenarios",
            [
                _list_field(
                    "Success",
                    items("success_scenarios"),
                    "success_scenarios" in changed,
                    "tabler:circle-check",
                ),
                _list_field(
                    "Failure",
                    items("failure_scenarios"),
                    "failure_scenarios" in changed,
                    "tabler:alert-circle",
                ),
            ],
        ),
        parts.panel_section(
            "Functional flow",
            [
                _list_field(
                    None,
                    items("functional_flow"),
                    "functional_flow" in changed,
                    numbered=True,
                    empty="Appears once the expected behaviour is clear",
                )
            ],
        ),
        parts.panel_section(
            "Assumptions",
            [
                _list_field(
                    None,
                    assumptions,
                    "assumptions" in changed,
                    "tabler:bookmark",
                    empty="None. Assumptions are always labelled here.",
                )
            ],
        ),
        parts.panel_section(
            "Open items",
            [
                _list_field(
                    None,
                    items("open_items"),
                    "open_items" in changed,
                    "tabler:alert-triangle",
                    empty="No open items",
                )
            ],
        ),
        parts.panel_section(
            "References",
            [
                _list_field(
                    None,
                    items("references"),
                    "references" in changed,
                    "tabler:paperclip",
                    empty="None provided (optional)",
                )
            ],
        ),
    ]


def _field_box(children: list, changed: bool) -> dmc.Box:
    return dmc.Box(children, style=da_styles.FIELD_CHANGED if changed else da_styles.FIELD)


def _label(label: str | None):
    return dmc.Text(label, size="xs", fw=600, c=da_styles.MUTED) if label else None


def _empty(text: str) -> dmc.Text:
    return dmc.Text(text, style=da_styles.EMPTY_TEXT)


def _text_field(label: str, value: str, changed: bool) -> dmc.Box:
    body = dmc.Text(value, size="sm") if value else _empty(EMPTY_TEXT)
    return _field_box([_label(label), body], changed)


def _list_field(
    label: str | None,
    items: list[str],
    changed: bool,
    icon: str = "",
    numbered: bool = False,
    empty: str = EMPTY_TEXT,
) -> dmc.Box:
    if not items:
        return _field_box([_label(label), _empty(empty)], changed)
    lines = []
    for number, item in enumerate(items, start=1):
        marker = (
            dmc.Text(f"{number}.", size="sm", c=da_styles.MUTED)
            if numbered
            else DashIconify(icon=icon, width=16, color=da_styles.MUTED)
        )
        lines.append(dmc.Group([marker, dmc.Text(item, size="sm")], gap=6, wrap="nowrap"))
    return _field_box([_label(label), *lines], changed)
