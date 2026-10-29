"""Our own building blocks for the Developer Assistant screen (decision D-H).

Pure functions that turn data into Dash Mantine components (version 2.5.1). They never read the
database. All developer and interpreter text goes in as plain string children, never as HTML
or Markdown (rule R11): React shows a string as text, whatever characters it contains.
"""

from datetime import datetime

import dash_mantine_components as dmc
from dash_iconify import DashIconify

from db_table_functions.db_tbl_da_requests import SINGAPORE_TIME
from pydantic_classes.da_models import (
    STATUS_CLARIFICATION,
    STATUS_CONFIRMED,
    STATUS_DECISION_REQUIRED,
    STATUS_DRAFT,
    STATUS_READY,
    display_status,
)
from pydantic_classes.da_request_record_models import ChatMessage
from styles import da_styles

# The developer's 6 steps, as on the demo. On screen Understand is step 1.
STEPS: tuple[str, ...] = (
    "Understand",
    "Discover",
    "Readiness Gate",
    "Generate + Check",
    "Preliminary Review",
    "Handoff",
)

# Same colour meaning as the demo pills.
_PILL_COLOURS: dict[str, str] = {
    STATUS_DRAFT: "gray",
    STATUS_CLARIFICATION: "blue",
    STATUS_DECISION_REQUIRED: "orange",
    STATUS_READY: "violet",
    STATUS_CONFIRMED: "green",
}


def format_singapore_time(moment: datetime) -> str:
    """Stored times are UTC; the screen shows Singapore time (spec 3.10)."""
    return moment.astimezone(SINGAPORE_TIME).strftime("%d %b %Y %H:%M")


def status_pill(status: str) -> dmc.Badge:
    return dmc.Badge(
        display_status(status), color=_PILL_COLOURS.get(status, "gray"), variant="light"
    )


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


def chat_bubble(message: ChatMessage) -> dmc.Box:
    """One chat message with its time in Singapore time."""
    return dmc.Box(
        [
            dmc.Text(message.text, size="sm"),
            dmc.Text(format_singapore_time(message.sent_at), size="xs", opacity=0.7),
        ],
        style=da_styles.BUBBLE[message.speaker],
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
