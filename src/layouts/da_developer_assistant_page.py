"""What is on the Developer Assistant screen: the Home page and the request workspace.

Presentation only (rule R12). Every function here turns data that the 2A engine already
prepared into components; nothing here decides a status, a question or a check. Think of it as
the display file (DDS) of a 5250 program: it says where each field goes, not what it means.
"""

import dash_mantine_components as dmc
from dash import dcc
from dash_iconify import DashIconify

from agents.da_discover_flow import (
    CONFIRM_OPTION,
    ESCALATE_OPTION,
    FAKE_INDEX_NOTICE,
    HINT_OPTION,
    HINT_QUESTION,
    outcome_status,
)
from agents.da_refine_screen import RefineBox, RefineBuildPanel, VersionHistory
from agents.da_understand_checks import MAX_MESSAGE_LENGTH
from agents.da_understand_flow import (
    ALWAYS_VISIBLE,
    FORM_BOXES,
    FORM_OPTIONAL_BOX,
    HELP_OPTION,
    OPTIONAL_QUESTION,
    PROCEED_OPTION,
)
from layouts.da_approach_panel import approach_panel
from layouts.da_build_panel import build_tab, poll_interval, tests_tab
from layouts.da_refine_panels import (
    approach_version_blocks,
    refine_build_blocks,
    version_history_blocks,
)
from layouts.da_workspace_panel import (
    RECONNECT_KEY,
    USE_KEY,
    USE_LABEL,
    WS_BUSY_TEXT,
    build_panel,
    workspace_chip,
    workspace_hop_stores,
    workspace_stores,
    ws_button_id,
)
from pydantic_classes.da_approach_models import ApproachView
from pydantic_classes.da_build_models import BuildView
from pydantic_classes.da_discovery_models import DiscoveryView
from pydantic_classes.da_models import (
    STATUS_CONFIRMED,
    STATUS_DISCOVERY_CONFIRMED,
    STATUS_ESCALATION,
    STATUS_NO_MATCH,
    STATUS_READY_TO_BUILD,
    STATUS_SEARCHING,
    STATUS_SIMILAR_FOUND,
    Request,
    display_status,
)
from pydantic_classes.da_request_record_models import AcceptanceCriterion, UnderstandView
from pydantic_classes.da_workspace_models import WorkspaceView
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
REFINE_TYPE = "da-refine"  # Phase 8 step 16: the Refine buttons, the id index is the action key
REFINE_MAIN_KEYS = (
    "confirm_v2", "findings_ok", "repro_yes", "own_add", "bug_fix", "apply", "check_edits",
)
KEYS_ID = "da-keys-ready"  # target of the Enter-to-send script; holds nothing
BUSY_ID = "da-busy"  # the "searching" line, shown only while a Discover action runs
# The 4-box form (Phase 6 fixes). Pattern ids, so the page can have none of them (all other
# screens) and one callback still reads all five boxes in order.
FORM_BOX_TYPE = "da-form-box"
FORM_ERROR_TYPE = "da-form-error"
FORM_SUBMIT_TYPE = "da-form-submit"
FORM_SUBMIT_LABEL = "Submit"
FORM_OPTIONAL_HINT = "This box may stay empty."
FORM_BUSY_TEXT = "⏳ Reading your answers…"
FORM_COMPOSER_TEXT = "Fill in the form above, then press Submit"

CODE_BANNER = "No code is written yet"
CODE_WRITTEN_BANNER = "Code is written to your folder"
DEMO_BANNER = "Demo mode: replies are scripted"
EMPTY_TEXT = "Waiting for your answer"
OTHER_PLACEHOLDER = "Other, type here"
CRITERIA_TITLE = "Acceptance criteria (each one gets tested)"
CRITERIA_EMPTY = "Each success or negative case becomes a testable criterion"
# What the developer reads for a "failure" criterion. The record keeps the kind "failure".
NEGATIVE_LABEL = "Negative scenario"
NEGATIVE_MARK = "*"
CRITERIA_LEGEND = f"{NEGATIVE_MARK} {NEGATIVE_LABEL} testing"
# Mantine cuts a badge's text with "..." when the badge is squeezed in a row. The ID must always
# show in full: no shrinking, and the label may not be clipped.
ID_BADGE_STYLE = {"flexShrink": 0, "overflow": "visible", "width": "auto"}
ID_BADGE_STYLES = {"label": {"overflow": "visible", "textOverflow": "clip"}}
UNDERSTAND_STEP = 1
DISCOVER_STEP = 2
APPROACH_STEP = 3
BUILD_STEP = 4
# The Discover buttons use the same pattern id as the Understand choices (the callbacks tell them
# apart by the workspace state). Their ids are plain ASCII keys, never the label: Dash cannot read
# the click count of a button whose id holds an emoji (it matches ids as escaped text).
START_KEY = "start"
CONFIRM_KEY = "confirm"
ESCALATE_KEY = "escalate"
TRY_DISCOVERY_OPTION = "Try again"  # the only start button: Discover starts by itself
SEARCH_AGAIN_OPTION = "Search again"
BUSY_TEXT = "⏳ Searching approved sources…"
APPROACH_BUSY_TEXT = "⏳ Working on it…"
# Approach buttons that are real main actions (filled). A design choice is NOT one of them.
MAIN_ACTION_KEYS = ("start", "accept", "accept_plan", "write_plan", "keep")
BUILD_LABEL = "Build"
BUILD_KEY = "build"
# What the note above the workspace buttons says at each step.
BUILD_NOTES: dict[str, str] = {
    "b_running": "The build is running on the server. You can leave this page",
    "b_round_failed": "The build is running on the server. You can leave this page",
    "b_interrupted": "The build paused. Resume it, cancel it, or get help",
    "b_unable": "I could not write tests. Resume the build, change the approach, or get help",
    "b_done": "The build is finished. Your code files are being written to your folder",
    "b_written": "The build is finished and written to your folder",
    "b_write_stopped": "The write stopped because you changed a file",
    "escalated": "This request was handed to a senior developer",
}
WORKSPACE_NOTES: dict[str, str] = {
    "start": "Choose your local CodeVision folder. Your browser asks you to allow it",
    "ws_blocked": "This folder doesn't match the plan yet. Choose another folder or get help",
    "ws_ready": "Your workspace is ready",
    "ws_fallback": "Your browser cannot reach the folder. Use the ZIP and upload instead",
}
# What the note above the Approach buttons says at each step.
APPROACH_NOTES: dict[str, str] = {
    "choices": "Choose an option to continue, or type your own answer",
    "review": "Review the Approach tab, then choose how to continue",
    "limit_reason": "Type a reason to accept this many files, or choose another option",
    "tests_pending": "The Tester has not written the test plan yet",
    "tests": "Review the test plan, then choose how to continue",
    "case_check": "Keep this test case or discard it",
}

# The other tabs exist on the demo but belong to later phases: shown greyed out.
PANEL_TABS: tuple[tuple[str, str], ...] = (
    ("Summary", "tabler:clipboard-list"),
    ("Discovery", "tabler:search"),
    ("Approach", "tabler:compass"),
    ("Build", "tabler:hammer"),
    ("Tests", "tabler:test-pipe"),
    ("Audit", "tabler:receipt"),
)


def layout() -> list:
    """The page itself. The content is filled in by the callbacks, from the URL."""
    return [
        dcc.Store(id=REFRESH_ID, data=0),
        dcc.Store(id=KEYS_ID),
        *workspace_hop_stores(),
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
        messages=[parts.chat_bubble(message) for message in view.messages]
        + ([_form()] if view.input_mode == "form" else []),
        composer=_composer(
            view.input_mode,
            view.choices,
            view.can_skip,
            view.prompt,
            view.custom_choice_allowed,
            view.send_label,
            view.text_prompt,
        ),
        panel=_summary_panel(view),
        state={"request_id": view.request.request_id, "revision": view.revision},
        busy_text=_understand_busy_text(view),
    )


def _understand_busy_text(view: UnderstandView) -> str:
    """The line shown while an action runs: reading the form, or (at the checkpoint, where
    Proceed also starts Discover) a general "working" line."""
    if view.input_mode == "form":
        return FORM_BUSY_TEXT
    return APPROACH_BUSY_TEXT if view.send_label != "Send" else ""


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


def _workspace(
    title,
    request_id,
    status,
    demo_mode,
    messages,
    composer,
    panel,
    state,
    step: int = UNDERSTAND_STEP,
    discovery: list | None = None,
    busy_text: str = "",
    approach: list | None = None,
    chip=None,
    build: list | None = None,
    stores: list | None = None,
    tests: list | None = None,
    poll=None,
    open_tab: str | None = None,
    code_written: bool = False,
) -> list:
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
            dmc.Group([chip, parts.status_pill(status)], gap="sm")
            if chip
            else parts.status_pill(status),
        ],
        justify="space-between",
        mb="sm",
    )
    chat_head = dmc.Group(
        [
            dmc.Text("Developer Assistant chat", fw=600, c=da_styles.NAVY),
            # Follows the real write state of the build (Phase 6 fixes, F9c).
            dmc.Badge(
                CODE_WRITTEN_BANNER if code_written else CODE_BANNER,
                color="green" if code_written else "orange",
                variant="light",
                leftSection=_lock(),
                id="da-code-badge",
            ),
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
            dmc.Text(busy_text, id=BUSY_ID, size="sm", px="md", style={"display": "none"}),
            composer,
        ],
        withBorder=True,
        radius="md",
        style=da_styles.COLUMN,
    )
    tab_list = dmc.TabsList(
        [
            dmc.TabsTab(
                name,
                value=name.lower(),
                leftSection=DashIconify(icon=icon, width=16),
                disabled=not (
                    name == "Summary"
                    or (name == "Discovery" and discovery)
                    or (name == "Approach" and approach)
                    or (name == "Build" and build)
                    or (name == "Tests" and tests)
                ),
                px="xs",
            )
            for name, icon in PANEL_TABS
        ],
        # All six tabs stay on one line; a narrow window scrolls them sideways.
        style={"flexWrap": "nowrap", "overflowX": "auto", "flexShrink": 0},
    )
    if discovery:
        # Discover or Approach is under way: those tabs can be used. The newest one opens first.
        panels = [_tab_panel(panel, "summary"), _tab_panel(discovery, "discovery")]
        if approach:
            panels.append(_tab_panel(approach, "approach"))
        if build:
            panels.append(_tab_panel(build, "build"))
        if tests:
            panels.append(_tab_panel(tests, "tests"))
        tabs = dmc.Tabs(
            [tab_list, *panels],
            value=open_tab or ("approach" if approach else "discovery"),
            style={**da_styles.COLUMN, "flex": 1},
        )
        side_children = [tabs]
    else:
        side_children = [
            dmc.Tabs(tab_list, value="summary"),
            dmc.Box(panel, style=da_styles.PANEL_BODY),
        ]
    side = dmc.Paper(side_children, withBorder=True, radius="md", style=da_styles.COLUMN)
    return [
        dcc.Store(id=STATE_ID, data=state),
        *(stores or []),
        *([poll] if poll is not None else []),
        parts.stepper(step),
        dmc.Box(top, mt="sm"),
        dmc.Box([chat, side], style=da_styles.WORKSPACE_GRID),
    ]


def _tab_panel(content: list, value: str) -> dmc.TabsPanel:
    """One right-panel tab: the same scrolling body as the plain Summary, inside a tab panel that
    is limited to the height left in the column (see da_styles.TAB_PANEL)."""
    return dmc.TabsPanel(
        dmc.Box(content, style=da_styles.PANEL_BODY), value=value, style=da_styles.TAB_PANEL
    )


def _lock():
    return DashIconify(icon="tabler:lock", width=12)


# --- Discover (Phase 3) ---


def render_discover_workspace(
    understand: UnderstandView,
    view: DiscoveryView,
    approach: ApproachView | None = None,
    refine: RefineBox | None = None,
) -> list:
    """The workspace once the request is confirmed: Discover is step 2, the chat carries on, and
    the Discovery tab opens as soon as there is a round to show. Once Discover is confirmed, the
    approach view brings the active Proceed to Approach button (Phase 4)."""
    # SEARCHING with no saved round also opens the tab, to say the round did not finish.
    show_tab = view.result is not None or view.request.status == STATUS_SEARCHING
    confirmed = view.request.status == STATUS_DISCOVERY_CONFIRMED and approach is not None
    request_id = view.request.request_id
    state = {"request_id": request_id, "revision": view.revision, "discover": True}
    if confirmed:
        # Once Discover is confirmed the buttons belong to Approach, with its own revision.
        state = {"request_id": request_id, "revision": approach.revision, "approach": True}
    in_lane = refine is not None and refine.offered
    if in_lane:
        # A requirement lane runs Discover again: its buttons are Refine's (step 16).
        state["refine"], state["refine_revision"] = True, refine.refine_revision
    if in_lane:
        composer = _discover_composer(view, refine)
    else:
        composer = _approach_composer(approach) if confirmed else _discover_composer(view)
    return _workspace(
        title=view.request.title,
        request_id=view.request.request_id,
        status=view.request.status,
        demo_mode=view.demo_mode,
        messages=[parts.chat_bubble(message) for message in view.messages],
        composer=composer,
        panel=_summary_panel(understand),
        state=state,
        step=DISCOVER_STEP,
        discovery=_discovery_panel(view) if show_tab else None,
        # After a round, "Findings look right" also starts Approach, so the line is a general one.
        busy_text=BUSY_TEXT if view.request.status == STATUS_CONFIRMED else APPROACH_BUSY_TEXT,
    )


def render_approach_workspace(
    understand: UnderstandView,
    discovery: DiscoveryView,
    view: ApproachView,
    workspace: WorkspaceView | None = None,
    build: BuildView | None = None,
    refine: RefineBox | None = None,
    history: VersionHistory | None = None,
    refine_panel: RefineBuildPanel | None = None,
) -> list:
    """The workspace from APPROACH_PROPOSED on: Approach is step 3 and its tab opens first.

    From READY_TO_BUILD on, `workspace` (Phase 5) adds the header chip, the folder buttons, and
    the Build tab once the check has passed. The page state then carries the WORKSPACE revision,
    because every button on this screen belongs to the workspace."""
    if workspace is not None:
        # Once a build has started, every button on this screen belongs to the BUILD (its own
        # revision); before that, to the workspace.
        building = build is not None and build.state.step != "start"
        state = {
            "request_id": view.request.request_id,
            "revision": build.revision if building else workspace.revision,
            "approach": True,
            "workspace": True,
        }
        if building:
            state["build"] = True
        if refine is not None and refine.offered:
            # Send and the Refine buttons are Refine's now; they carry the Refine revision.
            state["refine"], state["refine_revision"] = True, refine.refine_revision
        if building:
            build_content = build_tab(
                build,
                refine.hint if refine and refine.offered else "",
                refine_build_blocks(refine_panel),
            )
        else:
            build_content = build_panel(workspace) if workspace.step == "ws_ready" else None
        return _workspace(
            title=view.request.title,
            request_id=view.request.request_id,
            status=view.request.status,
            demo_mode=view.demo_mode,
            messages=[parts.chat_bubble(message) for message in view.messages],
            composer=_approach_composer(view, workspace, build if building else None, refine),
            panel=[*_summary_panel(understand), *version_history_blocks(history)],
            state=state,
            step=BUILD_STEP if building else APPROACH_STEP,
            discovery=_discovery_panel(discovery),
            busy_text=WS_BUSY_TEXT,
            approach=[*approach_panel(view, workspace.check), *approach_version_blocks(history)],
            chip=workspace_chip(workspace),
            build=build_content,
            stores=workspace_stores(
                workspace, build, refine.restore_build if refine is not None else 0
            ),
            tests=tests_tab(build) if building else None,
            poll=poll_interval(build) if building else None,
            open_tab="build" if building else None,
            code_written=building and any(row.status == "Written" for row in build.rows),
        )
    return _workspace(
        title=view.request.title,
        request_id=view.request.request_id,
        status=view.request.status,
        demo_mode=view.demo_mode,
        messages=[parts.chat_bubble(message) for message in view.messages],
        composer=_approach_composer(view),
        panel=_summary_panel(understand),
        state={"request_id": view.request.request_id, "revision": view.revision, "approach": True},
        step=APPROACH_STEP,
        discovery=_discovery_panel(discovery),
        busy_text=APPROACH_BUSY_TEXT,
        approach=approach_panel(view),
    )


def approach_buttons(view: ApproachView) -> list[tuple[str, str]]:
    """The Approach choice buttons as (key, label) pairs, in screen order. The button id holds
    the position (P19); the callback calls this again to turn a position back into a key."""
    return view.buttons


def _approach_composer(
    view: ApproachView | None,
    workspace: WorkspaceView | None = None,
    build: BuildView | None = None,
    refine: RefineBox | None = None,
) -> dmc.Box:
    """The bottom of the chat in Approach: the buttons of the step, and a text box that opens
    only at the steps that take typed text (rule G1). The Refine box (Phase 8) opens the text
    box at `b_written`, or closes it with the cap message."""
    buttons = view.buttons if view else []
    prompt = view.text_prompt if view else ""
    text_open = bool(prompt)
    send_label = view.send_label if view else "Send"
    if refine is not None and refine.offered:
        prompt, text_open = refine.placeholder, refine.text_open
        send_label = refine.send_label
    controls = dmc.Box(
        [
            dmc.Textarea(
                id=TEXT_ID,
                # A box that is closed because a limit was reached says so (the cap message).
                placeholder=prompt
                or (view.note if view and view.note else "Text input is paused until you choose"),
                disabled=not text_open,
                autosize=True,
                minRows=2,
                maxRows=6,
                inputProps={"maxLength": MAX_MESSAGE_LENGTH},
            ),
            dmc.Group(
                [
                    dmc.Button("Skip", id=SKIP_ID, style={"display": "none"}),
                    dmc.Button(
                        send_label,
                        id=SEND_ID,
                        disabled=not text_open,
                        leftSection=DashIconify(icon="tabler:send", width=16),
                    ),
                ],
                justify="flex-end",
                mt="xs",
            ),
        ],
        style=da_styles.COMPOSER if text_open else {**da_styles.COMPOSER, "opacity": 0.6},
    )
    if build is not None and not (view is not None and view.step == "escalated"):
        return dmc.Box([_build_bar(build, workspace, refine), controls])
    if view is not None and view.request.status == STATUS_READY_TO_BUILD:
        done = dmc.Box(
            [
                dmc.Alert(
                    "READY TO BUILD", color="green", variant="light", mb="xs", id="da-ready-chat"
                ),
                _workspace_buttons(workspace) if workspace is not None else None,
            ],
            style=da_styles.CHOICES_BAR,
            pb="xs",
        )
        return dmc.Box([done, controls])
    if view is not None and view.step == "escalated":
        done = dmc.Box(
            [dmc.Text(view.open_item, size="sm"), _hidden_reconnect(workspace)],
            style=da_styles.CHOICES_BAR,
            pb="xs",
        )
        return dmc.Box([done, controls])
    if not buttons:
        return controls
    note = (view.note if view else "") or APPROACH_NOTES.get(view.step if view else "", "")
    return dmc.Box([_approach_bar(buttons, note), controls])


def _hidden_reconnect(workspace: WorkspaceView | None):
    """The Reconnect button, drawn hidden; the browser shows it only when it needs your OK again
    (D-E, W4). It must exist whenever the workspace step is ws_ready: the browser script sets its
    style on every redraw, and Dash refuses an Output on a button that is not on the page."""
    if workspace is None or workspace.step != "ws_ready" or workspace.mode != "picker":
        return None
    button = parts.choice_button("Reconnect", ws_button_id(RECONNECT_KEY, "bar"), parts.NORMAL)
    button.style = {"display": "none"}
    return button


def _build_bar(
    build: BuildView, workspace: WorkspaceView | None = None, refine: RefineBox | None = None
) -> dmc.Box:
    """The buttons under the chat once a build has started (spec section 1). Browser-run ones
    (Re-scan and build again) start JavaScript; server-run ones use the normal choice path.
    At `b_written` the Refine buttons (Re-scan, Check my edits, Restore) are added."""
    offered = bool(refine and refine.offered)
    extra_browser = refine.browser_buttons if offered else []
    # While a Refine lane is open its buttons replace the Build ones (the build is finished).
    lane = offered and refine.lane
    shown = [
        parts.choice_button(label, ws_button_id(key, "bar"), parts.PRIMARY)
        for key, label in [*([] if lane else build.browser_buttons), *extra_browser]
    ]
    # Position in this list is the button id (P19) for the Build buttons.
    shown += [
        parts.choice_button(
            label,
            {"type": CHOICE_TYPE, "index": number},
            parts.SECONDARY if key == "help" else parts.NORMAL,
        )
        for number, (key, label) in enumerate([] if lane else build.buttons)
    ]
    shown += refine_buttons(refine) if offered else []
    reconnect = _hidden_reconnect(workspace)
    if reconnect is not None:
        shown.append(reconnect)
    if build.auto_write and build.mode == "download":
        download = ws_button_id("build_download", "bar")
        shown.append(parts.choice_button("Download ZIP", download, parts.PRIMARY))
    status = dmc.Alert(
        display_status(build.request_status),
        color="red" if build.request_status == "NOT_PASSING" else "blue",
        variant="light",
        mb="xs",
        id="da-build-chat-status",
    )
    note = (refine.note if offered and refine.note else "") or BUILD_NOTES.get(build.state.step, "")
    return dmc.Box(
        [
            status,
            dmc.Group([_lock(), dmc.Text(note, size="xs", fw=600)]),
            dmc.Group(shown, mt="xs", mb="xs"),
        ],
        style=da_styles.CHOICES_BAR,
        pb="xs",
    )


def refine_buttons(refine: RefineBox) -> list:
    """The server-run Refine buttons. The id holds the key (ASCII, never the label), so a click
    names its own action; the engine refuses an unknown key or an old window (step 16)."""
    return [
        parts.choice_button(
            label,
            {"type": REFINE_TYPE, "index": key},
            parts.PRIMARY
            if key in REFINE_MAIN_KEYS
            else parts.SECONDARY
            if key == "help"
            else parts.NORMAL,
        )
        for key, label in refine.buttons
    ]


def _workspace_buttons(workspace: WorkspaceView) -> dmc.Box:
    """The folder buttons of this workspace step. Browser-run buttons start JavaScript; the
    server-run ones (Change the approach, Get help) use the normal choice-button path."""
    shown = [
        parts.choice_button(label, ws_button_id(key, "bar"), parts.PRIMARY)
        for key, label in workspace.browser_buttons
    ]
    if workspace.step == "start":
        # Hidden until the browser finds a remembered folder; then it reads "Use <name>" (D-B).
        use = parts.choice_button(USE_LABEL, ws_button_id(USE_KEY, "bar"), parts.NORMAL)
        use.style = {"display": "none"}
        shown.insert(0, use)
    shown += [
        parts.choice_button(
            label,
            {"type": CHOICE_TYPE, "index": number},
            parts.SECONDARY if key == "help" else parts.NORMAL,
        )
        for number, (key, label) in enumerate(workspace.buttons)
    ]
    if workspace.step == "ws_ready" and workspace.mode == "picker":
        # Drawn hidden; the browser shows it only when it needs your OK again (W4).
        reconnect = parts.choice_button(
            "Reconnect", ws_button_id(RECONNECT_KEY, "bar"), parts.NORMAL
        )
        reconnect.style = {"display": "none"}
        shown.append(reconnect)
    if workspace.step == "ws_ready":
        # Browser-run: the page re-scans your folder first (B1), then the server starts the build.
        shown.append(
            parts.choice_button(BUILD_LABEL, ws_button_id(BUILD_KEY, "bar"), parts.PRIMARY)
        )
    note = workspace.note or WORKSPACE_NOTES.get(workspace.step, "")
    return dmc.Box(
        [
            dmc.Group([_lock(), dmc.Text(note, size="xs", fw=600)]),
            dmc.Group(shown, mt="xs", mb="xs"),
        ]
    )


def approach_button_kind(key: str) -> str:
    """The style of an Approach button: filled for the real main actions, outlined for help and
    for going back, light for the rest. Position does not matter, so the options of a design
    choice all look equal (Phase 6 fixes, section 4)."""
    if key in ("help", "decide_help", "change_approach"):
        return parts.SECONDARY
    if key in MAIN_ACTION_KEYS:
        return parts.PRIMARY
    return parts.NORMAL


def _approach_bar(buttons: list[tuple[str, str]], note: str) -> dmc.Box:
    shown = [
        parts.choice_button(
            label, {"type": CHOICE_TYPE, "index": number}, approach_button_kind(key)
        )
        for number, (key, label) in enumerate(buttons)
    ]
    return dmc.Box(
        [
            dmc.Group([_lock(), dmc.Text(note, size="xs", fw=600)]),
            dmc.Group(shown, mt="xs", mb="xs"),
        ],
        style=da_styles.CHOICES_BAR,
    )


def _discovery_panel(view: DiscoveryView) -> list:
    result = view.result
    record = view.record
    parts_list: list = [
        dmc.Text(
            f"Input: request {view.request.request_id}, record version {record.version}",
            size="xs",
            c=da_styles.MUTED,
            id="da-discovery-input",
        ),
        parts.search_rows(),
    ]
    if result is None:
        # SEARCHING with no saved round: the app stopped mid-round (spec section 2).
        parts_list.append(
            dmc.Alert(
                "A search round did not finish. Press Search again to start it over.",
                color="orange",
                variant="light",
                id="da-outcome-banner",
            )
        )
        return parts_list
    if result.search_provider == "fake":
        parts_list.append(
            dmc.Alert(FAKE_INDEX_NOTICE, color="violet", variant="light", id="da-fake-index-banner")
        )
    outcome = outcome_status(result.findings)
    parts_list.append(parts.outcome_banner(outcome))
    if view.request.status == STATUS_DISCOVERY_CONFIRMED:
        parts_list.append(
            dmc.Alert("Discovery confirmed.", color="green", variant="light", id="da-state-banner")
        )
    if view.request.status == STATUS_ESCALATION:
        parts_list.append(
            dmc.Alert(view.open_item, color="red", variant="light", id="da-state-banner")
        )
    if result.summary_source == "fallback" and result.hits:
        parts_list.append(parts.fallback_banner())
    hits_by_id = {hit.hit_id: hit for hit in result.hits}
    parts_list += [parts.finding_card(finding, hits_by_id) for finding in result.findings]
    if not result.findings:
        parts_list.append(dmc.Text("No findings in this round.", style=da_styles.EMPTY_TEXT))
    if result.limitations:
        parts_list.append(parts.limitations_card(result.limitations))
    parts_list.append(parts.round_label(view.rounds_used, view.max_rounds))
    return parts_list


def discover_buttons(view: DiscoveryView) -> list[tuple[str, str]]:
    """The Discover choice buttons as (key, label) pairs, in screen order.

    The button id holds the position (P19); the callback calls this again to turn a position
    back into a key, so the screen and the callback cannot disagree.
    """
    status = view.request.status
    if status in (STATUS_CONFIRMED, STATUS_SEARCHING):
        label = TRY_DISCOVERY_OPTION if status == STATUS_CONFIRMED else SEARCH_AGAIN_OPTION
        return [(START_KEY, label)]
    if status in (STATUS_SIMILAR_FOUND, STATUS_NO_MATCH):
        keys = {CONFIRM_OPTION: CONFIRM_KEY, ESCALATE_OPTION: ESCALATE_KEY}
        return [(keys[option], option) for option in view.choices if option in keys]
    return []


def _discover_composer(view: DiscoveryView, refine: RefineBox | None = None) -> dmc.Box:
    """The bottom of the chat in Discover. The text box, Send and Skip always exist (the
    callbacks name them). Send is the hint button while a hint can be given. In a Refine
    lane the Refine buttons replace the Discover ones and no hint is given."""
    status = view.request.status
    can_hint = view.can_hint and refine is None
    controls = dmc.Box(
        [
            dmc.Textarea(
                id=TEXT_ID,
                label=HINT_QUESTION if can_hint else None,
                placeholder="Type your hint..." if can_hint else "",
                disabled=not can_hint,
                autosize=True,
                minRows=2,
                maxRows=4,
                inputProps={"maxLength": MAX_MESSAGE_LENGTH},
            ),
            dmc.Group(
                [
                    dmc.Button("Skip", id=SKIP_ID, style={"display": "none"}),
                    dmc.Button(
                        HINT_OPTION,
                        id=SEND_ID,
                        variant="light",
                        disabled=not can_hint,
                        style={} if can_hint else {"display": "none"},
                    ),
                ],
                justify="flex-end",
                mt="xs",
            ),
        ],
        style=da_styles.COMPOSER if can_hint else {"display": "none"},
    )
    buttons = discover_buttons(view)
    if refine is not None:
        shown = refine_buttons(refine)
        bar = dmc.Box(
            [
                dmc.Group([_lock(), dmc.Text(refine.note, size="xs", fw=600)]),
                dmc.Group(shown, mt="xs", mb="xs"),
            ],
            style=da_styles.CHOICES_BAR,
        )
        return dmc.Box([bar, controls])
    if status in (STATUS_CONFIRMED, STATUS_SEARCHING):
        note = (
            f"Discovery did not start. Press {buttons[0][1]} to search approved sources"
            if status == STATUS_CONFIRMED
            else f"Press {buttons[0][1]} to search approved sources"
        )
        return dmc.Box([_discover_bar(buttons, note), controls])
    if status in (STATUS_SIMILAR_FOUND, STATUS_NO_MATCH):
        note = view.cap_message or "Choose an option to continue"
        return dmc.Box([_discover_bar(buttons, note), controls])
    # Confirmed or escalated: nothing more to do in this phase.
    done = dmc.Box(
        [
            dmc.Button("Proceed to Approach", disabled=True)
            if status == STATUS_DISCOVERY_CONFIRMED
            else dmc.Text(view.open_item, size="sm"),
        ],
        style=da_styles.CHOICES_BAR,
        pb="xs",
    )
    return dmc.Box([done, controls])


def _discover_bar(buttons: list[tuple[str, str]], note: str) -> dmc.Box:
    """The choice buttons as (key, label) pairs. The first one is the main action."""
    shown = [
        parts.choice_button(
            label,
            {"type": CHOICE_TYPE, "index": number},
            parts.SECONDARY
            if key == ESCALATE_KEY
            else (parts.PRIMARY if number == 0 else parts.NORMAL),
        )
        for number, (key, label) in enumerate(buttons)
    ]
    return dmc.Box(
        [
            dmc.Group([_lock(), dmc.Text(note, size="xs", fw=600)]),
            dmc.Group(shown, mt="xs", mb="xs"),
        ],
        style=da_styles.CHOICES_BAR,
    )


# --- The composer: text, locked choices, waiting, done ---


def _composer(
    mode: str,
    choices: list[str],
    can_skip: bool,
    prompt: str,
    custom_allowed: bool = False,
    send_label: str = "Send",
    typing_prompt: str = "",
) -> dmc.Box:
    """The bottom of the chat. The text box, Send and Skip always exist (the callbacks name
    them); the mode decides which ones can be used. At a decision the buttons stay and the text
    box opens too, for "Other, type here" (W3). At the checkpoint the box is open too and Send is
    "Correct something" (send_label, typing_prompt: Phase 6 fixes, section 2)."""
    text_open = mode == "text" or custom_allowed or bool(typing_prompt)
    paused = {
        "form": FORM_COMPOSER_TEXT,
        "choices": "Text input is paused until you choose",
        "waiting": prompt,
        "done": "This request is confirmed. It cannot be changed in this phase.",
    }.get(mode, "")
    controls = dmc.Box(
        [
            dmc.Textarea(
                id=TEXT_ID,
                placeholder=(
                    typing_prompt
                    if typing_prompt
                    else OTHER_PLACEHOLDER
                    if custom_allowed
                    else "Type your message..."
                    if text_open
                    else paused
                ),
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
                        send_label,
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
    return controls


def _form() -> dmc.Box:
    """The 4-box form: the 4 mandatory questions in their wording, then the optional area (it may
    stay empty), one Submit. A failing box shows its message on the line under it."""
    boxes = [_form_box(number, f"{number}. {title}") for number, title in FORM_BOXES]
    boxes.append(_form_box(FORM_OPTIONAL_BOX, OPTIONAL_QUESTION, FORM_OPTIONAL_HINT))
    return dmc.Paper(
        [
            *boxes,
            dmc.Group(
                dmc.Button(
                    FORM_SUBMIT_LABEL,
                    id={"type": FORM_SUBMIT_TYPE, "index": 0},
                    leftSection=DashIconify(icon="tabler:send", width=16),
                ),
                justify="flex-end",
            ),
        ],
        withBorder=True,
        radius="md",
        p="sm",
        id="da-form",
    )


def _form_box(number: int, label: str, description: str | None = None) -> dmc.Box:
    return dmc.Box(
        [
            dmc.Textarea(
                id={"type": FORM_BOX_TYPE, "index": number},
                label=label,
                description=description,
                autosize=True,
                minRows=2,
                maxRows=6,
                inputProps={"maxLength": MAX_MESSAGE_LENGTH},
            ),
            dmc.Text(
                "",
                id={"type": FORM_ERROR_TYPE, "index": number},
                c="red",
                size="xs",
                **{"aria-live": "assertive"},
            ),
        ],
        mb="sm",
    )


def _choices_bar(choices: list[str]) -> dmc.Box:
    # The id holds the position, not the text: AI-written options can hold curly quotes, long
    # dashes, accents or emoji, which are not safe inside a component id. The callback looks the
    # text up again from the saved request (P19).
    buttons = [
        parts.choice_button(
            option,
            {"type": CHOICE_TYPE, "index": index},
            parts.SECONDARY
            if option == HELP_OPTION
            else (parts.PRIMARY if option == PROCEED_OPTION else parts.NORMAL),
        )
        for index, option in enumerate(choices)
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
    """The live summary. Fields changed by the last answer are highlighted. A field the screen
    does not show yet says "Waiting for your answer" (W5); the record already holds its value."""
    record = view.record if view else None
    shown = set(view.visible_fields) if view else set(ALWAYS_VISIBLE)
    changed = set(view.changed_fields) & shown if view else set()
    text = view.progress_text if view else "0 of 4 mandatory questions answered"
    answered = view.answered_count if view else 0
    warn = text.startswith("Clarification required")

    def value(name: str) -> str:
        return getattr(record, name) if record and name in shown else ""

    def items(name: str) -> list:
        return list(getattr(record, name)) if record and name in shown else []

    def empty(name: str, text: str) -> str:
        return text if name in shown else EMPTY_TEXT

    assumptions = (
        [f"{a.text} (basis: {a.basis})" for a in record.assumptions]
        if record and "assumptions" in shown
        else []
    )
    criteria = list(record.acceptance_criteria) if record and "acceptance_criteria" in shown else []
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
            CRITERIA_TITLE,
            [
                _criteria_field(
                    criteria,
                    "acceptance_criteria" in changed,
                    empty("acceptance_criteria", CRITERIA_EMPTY),
                )
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
            "Functional flow",
            [
                _list_field(
                    None,
                    items("functional_flow"),
                    "functional_flow" in changed,
                    numbered=True,
                    empty=empty("functional_flow", "Appears once the expected behaviour is clear"),
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
                    empty=empty("references", "None provided (optional)"),
                )
            ],
        ),
    ]


def _criteria_field(
    criteria: list[AcceptanceCriterion], changed: bool, empty: str
) -> dmc.Box:
    """One line each: the ID as a small badge, an asterisk after it on negative (failure)
    criteria, then Given / when / then in words. A muted legend explains the asterisk."""
    if not criteria:
        return _field_box([_empty(empty)], changed)
    lines = [dmc.Text(CRITERIA_LEGEND, size="xs", c=da_styles.MUTED, id="da-criteria-legend")]
    for criterion in criteria:
        sentence = f"Given {criterion.given}, when {criterion.when}, then {criterion.then}."
        lines.append(
            dmc.Group(
                [
                    dmc.Badge(
                        criterion.id,
                        size="sm",
                        variant="light",
                        color="blue",
                        style=ID_BADGE_STYLE,
                        styles=ID_BADGE_STYLES,
                    ),
                    _negative_mark() if criterion.kind == "failure" else None,
                    dmc.Text(sentence, size="sm"),
                ],
                gap=6,
                wrap="nowrap",
                align="flex-start",
            )
        )
    return _field_box(lines, changed)


def _negative_mark() -> dmc.Tooltip:
    """The asterisk after the ID of a negative scenario: hover text and aria-label."""
    mark = dmc.Text(
        NEGATIVE_MARK, size="sm", fw=700, **{"aria-label": NEGATIVE_LABEL}
    )
    return dmc.Tooltip(mark, label=NEGATIVE_LABEL)


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
