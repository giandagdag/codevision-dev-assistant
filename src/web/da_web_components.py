"""Our own building blocks for the Developer Assistant screen (decision D-H).

Pure functions that turn data into Dash Mantine components (version 2.5.1). They never read the
database. All developer and interpreter text goes in as plain string children, never as HTML
or Markdown (rule R11): React shows a string as text, whatever characters it contains.
"""

from datetime import datetime

import dash_mantine_components as dmc
from dash_iconify import DashIconify

from agents.da_discover_flow import DISCOVER_DIVIDER
from agents.da_inbox import CLOSED_BY_SENIOR
from db_table_functions.db_tbl_da_requests import SINGAPORE_TIME
from pydantic_classes.da_discovery_models import Finding, SearchHit
from pydantic_classes.da_models import (
    STATUS_APPROACH_PROPOSED,
    STATUS_BUILDING,
    STATUS_CLARIFICATION,
    STATUS_CONFIRMED,
    STATUS_DECISION_REQUIRED,
    STATUS_DISCOVERY_CONFIRMED,
    STATUS_DRAFT,
    STATUS_ESCALATION,
    STATUS_HANDED_OFF,
    STATUS_NO_MATCH,
    STATUS_NOT_PASSING,
    STATUS_READY,
    STATUS_READY_FOR_REVIEW,
    STATUS_READY_TO_BUILD,
    STATUS_SEARCHING,
    STATUS_SIMILAR_FOUND,
    STATUS_TESTER_REVIEW,
    display_status,
)
from pydantic_classes.da_request_record_models import ChatMessage
from styles import da_styles

# A senior's chat line starts like this (agents/da_senior_actions.py); the screen marks it.
SENIOR_LINE_START = "Senior "

# The developer's 6 steps, as on the demo. On screen Understand is step 1.
STEPS: tuple[str, ...] = (
    "Understand",
    "Discover",
    "Approach",
    "Build & Test",
    "Your review",
    "Handoff",
)

# Same colour meaning as the demo pills.
_PILL_COLOURS: dict[str, str] = {
    STATUS_DRAFT: "gray",
    STATUS_CLARIFICATION: "blue",
    STATUS_DECISION_REQUIRED: "orange",
    STATUS_READY: "violet",
    STATUS_CONFIRMED: "green",
    STATUS_SEARCHING: "blue",
    STATUS_SIMILAR_FOUND: "green",
    STATUS_NO_MATCH: "orange",
    STATUS_DISCOVERY_CONFIRMED: "green",
    STATUS_ESCALATION: "red",
    STATUS_APPROACH_PROPOSED: "violet",
    STATUS_READY_TO_BUILD: "green",
    STATUS_BUILDING: "blue",
    STATUS_READY_FOR_REVIEW: "yellow",
    STATUS_NOT_PASSING: "red",
    STATUS_TESTER_REVIEW: "blue",
    STATUS_HANDED_OFF: "teal",
}

FALLBACK_BANNER = "AI summary unavailable. Showing plain search results."
# Label, icon and colour for each kind of finding (spec 3.8).
FINDING_KINDS: dict[str, tuple[str, str, str]] = {
    "existing_capability": ("Existing capability", "tabler:circle-check", "green"),
    "similar_implementation": ("Similar implementation", "tabler:copy", "blue"),
    "relevant_standard": ("Relevant standard", "tabler:book", "violet"),
    "affected_area": ("Affected area", "tabler:target", "orange"),
}
CONFIDENCE_COLOURS = {"high": "green", "medium": "yellow", "low": "gray"}
# The search rows on the Discovery tab: (name, ready). Structural search comes later (D-A).
SEARCH_ROWS: tuple[tuple[str, bool], ...] = (
    ("Exact", True),
    ("Meaning", True),
    ("Filters", True),
    ("Structural", False),
)


def format_singapore_time(moment: datetime) -> str:
    """Stored times are UTC; the screen shows Singapore time (spec 3.10)."""
    return moment.astimezone(SINGAPORE_TIME).strftime("%d %b %Y %H:%M")


def status_pill(status: str, note: str = "") -> dmc.Badge:
    """`note` (Phase 10): "with <label>" after ESCALATION REQUIRED, or "Closed by senior"."""
    if note == CLOSED_BY_SENIOR:
        return dmc.Badge(CLOSED_BY_SENIOR, color="gray", variant="light")
    text = display_status(status) + (f", {note}" if note and status == STATUS_ESCALATION else "")
    return dmc.Badge(text, color=_PILL_COLOURS.get(status, "gray"), variant="light")


def stepper(current_step: int) -> dmc.Box:
    """The 6 steps with the current one highlighted."""
    items = []
    for number, name in enumerate(STEPS, start=1):
        current = number == current_step
        look = da_styles.STEP_CURRENT if current else da_styles.STEP_OTHER
        style = {**da_styles.STEP_PILL, **look}
        items.append(
            dmc.Box(
                [dmc.Text(f"{number}", fw=700, size="sm"), dmc.Text(name, size="sm")],
                id={"type": "da-step", "step": number},
                style=style,
                px="sm",
                py=4,
            )
        )
        if number < len(STEPS):
            items.append(DashIconify(icon="tabler:chevron-right", width=14, color="#B7BECB"))
    return dmc.Box(items, style=da_styles.STEPPER)


PRIMARY, NORMAL, SECONDARY, CANCEL = "primary", "normal", "secondary", "cancel"


def choice_button(label: str, button_id: dict, kind: str = NORMAL, disabled: bool = False):
    """The one place a choice button is built, for every screen (P21).

    primary: filled blue, the main action. normal: light blue. secondary: the help and escalation
    path (I need help deciding, Get help, Escalate): outlined, white with dark text and a thin
    border, so it never looks disabled. A disabled button keeps Mantine's greyed-out look, so the
    border colour is only added while the button can be clicked.
    """
    secondary = kind == SECONDARY
    if kind == CANCEL:  # B2 S2: a plain grey outline, never looks like a lane button
        return dmc.Button(
            label, id=button_id, variant="outline", color="gray", radius="xl", size="sm",
            disabled=disabled,
        )
    return dmc.Button(
        label,
        id=button_id,
        variant="filled" if kind == PRIMARY else ("default" if secondary else "light"),
        color="blue",
        radius="xl",
        size="sm",
        disabled=disabled,
        style=da_styles.SECONDARY_BUTTON_BORDER if secondary and not disabled else None,
    )


def chat_bubble(message: ChatMessage) -> dmc.Box:
    """One chat message with its time in Singapore time. The Discover marker is a divider."""
    if message.speaker == "system" and message.text == DISCOVER_DIVIDER:
        return dmc.Divider(label=DISCOVER_DIVIDER, labelPosition="center")
    from_senior = message.speaker == "assistant" and message.text.startswith(SENIOR_LINE_START)
    return dmc.Box(
        [
            dmc.Text(message.text, size="sm"),
            dmc.Text(format_singapore_time(message.sent_at), size="xs", opacity=0.7),
        ],
        style=da_styles.BUBBLE_SENIOR if from_senior else da_styles.BUBBLE[message.speaker],
        p="sm",
        bdrs="md",
    )


def panel_section(title: str, children: list) -> dmc.Box:
    return dmc.Box(
        [dmc.Text(title, fw=700, size="sm", c=da_styles.NAVY, mb=6), *children],
        style=da_styles.PANEL_SECTION,
    )


def progress_segments(answered: int, text: str, warn: bool = False) -> dmc.Box:
    """4 segments (one per mandatory question) and the progress text under them."""
    on_colour = da_styles.SEGMENT_WARN if warn else da_styles.BLUE
    segments = [
        dmc.Box(
            style={
                **da_styles.PROGRESS_SEGMENT,
                "background": on_colour if index < answered else da_styles.SEGMENT_OFF,
            }
        )
        for index in range(4)
    ]
    return dmc.Box(
        [
            dmc.SimpleGrid(segments, cols=4, spacing=4),
            dmc.Text(text, size="xs", c=da_styles.MUTED, mt=4),
        ],
        mb=6,
    )


# --- Discovery tab (Phase 3, spec 3.8) ---


def source_line(hit: SearchHit) -> str:
    """Where a finding comes from: path, then the function or class, then the version if known."""
    line = f"{hit.source_path} · {hit.symbol}" if hit.symbol else hit.source_path
    line = f"{line} @ {hit.version}" if hit.version else line
    return f"{line} · In capability: {hit.capability}" if hit.capability else line


def search_rows() -> dmc.Box:
    rows = []
    for name, ready in SEARCH_ROWS:
        status = (
            DashIconify(icon="tabler:circle-check", width=16, color=da_styles.BLUE)
            if ready
            else dmc.Text("Coming later", size="xs")
        )
        rows.append(
            dmc.Group(
                [dmc.Text(name, size="sm"), status],
                gap=6,
                opacity=1 if ready else 0.5,
                id=f"da-search-{name.lower()}",
            )
        )
    return dmc.Group(rows, gap="lg")


def outcome_banner(outcome: str) -> dmc.Alert:
    """Green when something reusable was found, amber when not (spec 3.8)."""
    if outcome == STATUS_SIMILAR_FOUND:
        return dmc.Alert(
            "Similar implementation found. Check the findings below before writing new code.",
            color="green",
            variant="light",
            id="da-outcome-banner",
        )
    return dmc.Alert(
        "No reliable match found. That is not proof it does not exist.",
        color="orange",
        variant="light",
        id="da-outcome-banner",
    )


def fallback_banner() -> dmc.Alert:
    return dmc.Alert(FALLBACK_BANNER, color="orange", variant="light", id="da-fallback-banner")


def finding_card(finding: Finding, hits_by_id: dict[int, SearchHit]) -> dmc.Paper:
    """One finding: kind, title, explanation, where it comes from, and how sure the AI is."""
    label, icon, colour = FINDING_KINDS[finding.kind]
    sources = [
        dmc.Text(source_line(hits_by_id[hit_id]), size="xs", c=da_styles.MUTED, ff="monospace")
        for hit_id in finding.hit_ids
        if hit_id in hits_by_id
    ]
    return dmc.Paper(
        [
            dmc.Group(
                [
                    dmc.Group(
                        [
                            DashIconify(icon=icon, width=18),
                            dmc.Text(label, size="xs", fw=600, c=colour),
                        ],
                        gap=4,
                    ),
                    dmc.Badge(
                        f"{finding.confidence} confidence",
                        color=CONFIDENCE_COLOURS[finding.confidence],
                        variant="light",
                    ),
                ],
                justify="space-between",
            ),
            dmc.Text(finding.title, fw=700, size="sm", c=da_styles.NAVY, mt=4),
            dmc.Text(finding.explanation, size="sm"),
            *sources,
        ],
        withBorder=True,
        radius="md",
        p="sm",
        mb="xs",
    )


def limitations_card(limitations: list[str]) -> dmc.Paper:
    lines = [
        dmc.Group(
            [DashIconify(icon="tabler:info-circle", width=16, color=da_styles.MUTED),
             dmc.Text(text, size="sm")],
            gap=6,
            wrap="nowrap",
        )
        for text in limitations
    ]
    return dmc.Paper(
        [dmc.Text("Limitations", fw=700, size="sm", c=da_styles.NAVY, mb=4), *lines],
        withBorder=True,
        radius="md",
        p="sm",
        id="da-limitations",
    )


# --- PR summary box (Phase 10, Handoff) ---

SUMMARY_BOX_ID = "da-pr-summary"
COPY_BUTTON_ID = "da-copy-summary"
COPY_NOTE_ID = "da-copy-note"
COPY_LABEL = "Copy summary"
COPY_FALLBACK = "Your browser would not copy. The text is selected: press Ctrl+C."
COPIED_TEXT = "Copied."


def summary_box(text: str) -> dmc.Box:
    """The PR summary as read-only text with a Copy summary button. The text is a plain string
    (rule R11). The button is wired by a clientside callback (da_handoff_callbacks)."""
    return dmc.Box(
        [
            dmc.Text("PR summary", fw=700, size="sm", c=da_styles.NAVY, mb=6),
            dmc.Textarea(
                id=SUMMARY_BOX_ID,
                value=text,
                readOnly=True,
                autosize=True,
                minRows=8,
                maxRows=24,
            ),
            dmc.Group(
                [
                    dmc.Button(COPY_LABEL, id=COPY_BUTTON_ID, size="sm"),
                    dmc.Text("", id=COPY_NOTE_ID, size="xs", c=da_styles.MUTED),
                ],
                mt="xs",
            ),
        ],
        style=da_styles.PANEL_SECTION,
    )


def round_label(rounds_used: int, max_rounds: int) -> dmc.Text:
    return dmc.Text(f"Round {rounds_used} of {max_rounds}", size="xs", c=da_styles.MUTED)
