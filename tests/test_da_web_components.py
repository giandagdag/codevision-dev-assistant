from datetime import UTC, datetime

import pytest

from pydantic_classes.da_models import STATUSES, display_status
from pydantic_classes.da_request_record_models import ChatMessage
from tests.da_tree import all_text, components, texts
from web import da_web_components as parts


@pytest.mark.parametrize("status", STATUSES)
def test_every_status_has_a_pill_with_spaces(status):
    pill = parts.status_pill(status)
    assert pill.children == display_status(status)
    assert "_" not in pill.children


def test_only_confirmed_is_green_and_unknown_is_grey():
    assert parts.status_pill("CONFIRMED_FOR_DISCOVERY").color == "green"
    assert parts.status_pill("SOMETHING_NEW").color == "gray"


def test_stepper_shows_six_steps_with_the_first_highlighted():
    bar = parts.stepper(1)
    steps = [c for c in components(bar) if isinstance(getattr(c, "id", None), dict)]
    assert len(steps) == 6
    assert [c.style.get("fontWeight") for c in steps] == [600, None, None, None, None, None]
    assert "Understand" in all_text(bar) and "Handoff" in all_text(bar)


def test_time_is_shown_in_singapore_time():
    # 16:30 UTC is 00:30 the next day in Singapore (UTC+8).
    moment = datetime(2026, 10, 29, 16, 30, tzinfo=UTC)
    assert parts.format_singapore_time(moment) == "30 Oct 2026 00:30"


def test_html_in_a_message_stays_plain_text():
    # Rule R11: markup is shown as characters, never turned into HTML.
    text = "<b>bold</b> <script>alert(1)</script>"
    message = ChatMessage(
        request_id="CVDA-2026-0001",
        sent_at=datetime(2026, 10, 29, 1, 0, tzinfo=UTC),
        speaker="developer",
        text=text,
    )
    bubble = parts.chat_bubble(message)
    assert text in texts(bubble)
    assert [c for c in components(bubble) if c._type in ("Markdown", "Html")] == []


def test_progress_has_four_segments_and_warn_colour():
    bar = parts.progress_segments(2, "2 of 4 mandatory questions answered")
    grid = components(bar, "SimpleGrid")[0]
    colours = [segment.style["background"] for segment in grid.children]
    assert len(colours) == 4
    assert colours[:2] == [parts.da_styles.BLUE] * 2
    assert colours[2:] == [parts.da_styles.SEGMENT_OFF] * 2
    warned = parts.progress_segments(1, "Clarification required: 1 open item", warn=True)
    assert components(warned, "SimpleGrid")[0].children[0].style["background"] == (
        parts.da_styles.SEGMENT_WARN
    )


def test_system_messages_have_their_own_style():
    assert set(parts.da_styles.BUBBLE) == {"developer", "assistant", "system"}
