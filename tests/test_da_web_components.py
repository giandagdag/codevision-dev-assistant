from datetime import UTC, datetime

import pytest

from pydantic_classes.da_models import STATUSES, display_status
from pydantic_classes.da_request_record_models import ChatMessage
from tests.da_tree import all_text, by_id, components, texts
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


# --- Discovery tab parts (Phase 3, spec 3.8) ---


def hit(**changes):
    from pydantic_classes.da_discovery_models import SearchHit

    values = {
        "hit_id": 1,
        "source_path": "app/ingestion/pdf_processor.py",
        "symbol": "PdfProcessor.extract_text",
        "version": "fake-index-001",
        "kind": "code",
        "score": 0.5,
        "mode": "exact",
    }
    return SearchHit(**(values | changes))


def finding(**changes):
    from pydantic_classes.da_discovery_models import Finding

    values = {
        "kind": "existing_capability",
        "title": "PDF text extraction exists",
        "explanation": "Already pulls text from pages.",
        "hit_ids": [1],
        "confidence": "high",
    }
    return Finding(**(values | changes))


def test_source_line_shows_path_symbol_and_version_when_known():
    assert parts.source_line(hit()) == (
        "app/ingestion/pdf_processor.py · PdfProcessor.extract_text @ fake-index-001"
    )
    assert parts.source_line(hit(version="")) == (
        "app/ingestion/pdf_processor.py · PdfProcessor.extract_text"
    )
    assert parts.source_line(hit(symbol="", version="")) == "app/ingestion/pdf_processor.py"


def test_search_rows_show_three_ready_and_structural_greyed_as_coming_later():
    rows = parts.search_rows()

    text = all_text(rows)
    for name in ("Exact", "Meaning", "Filters", "Structural"):
        assert name in text
    assert text.count("Coming later") == 1
    structural = by_id(rows, "da-search-structural")
    assert structural.opacity == 0.5 and "Coming later" in all_text(structural)
    assert by_id(rows, "da-search-exact").opacity == 1


def test_outcome_banner_is_green_for_similar_and_amber_otherwise():
    green = parts.outcome_banner("SIMILAR_IMPLEMENTATION_FOUND")
    amber = parts.outcome_banner("NO_RELIABLE_MATCH")

    assert green.color == "green" and "Similar implementation found" in all_text(green)
    assert amber.color == "orange" and "not proof" in all_text(amber)


def test_fallback_banner_has_the_exact_text():
    assert all_text(parts.fallback_banner()) == (
        "AI summary unavailable. Showing plain search results."
    )


def test_finding_card_shows_kind_title_explanation_sources_and_confidence():
    card = parts.finding_card(finding(), {1: hit()})

    text = all_text(card)
    assert "Existing capability" in text
    assert "PDF text extraction exists" in text and "Already pulls text from pages." in text
    assert "app/ingestion/pdf_processor.py · PdfProcessor.extract_text @ fake-index-001" in text
    assert "high confidence" in text


def test_finding_card_leaves_out_a_source_that_is_not_in_the_hits():
    card = parts.finding_card(finding(hit_ids=[1, 7]), {1: hit()})

    assert all_text(card).count("pdf_processor.py") == 1


@pytest.mark.parametrize(
    ("kind", "label"),
    [
        ("existing_capability", "Existing capability"),
        ("similar_implementation", "Similar implementation"),
        ("relevant_standard", "Relevant standard"),
        ("affected_area", "Affected area"),
    ],
)
def test_every_finding_kind_has_a_label(kind, label):
    assert label in all_text(parts.finding_card(finding(kind=kind), {1: hit()}))


def test_limitations_card_and_round_label():
    assert "Limitations" in all_text(parts.limitations_card(["One.", "Two."]))
    assert all_text(parts.limitations_card(["One.", "Two."])).count(".") >= 2
    assert all_text(parts.round_label(2, 3)) == "Round 2 of 3"


def test_discover_divider_is_a_divider_and_other_system_messages_are_bubbles():
    from agents.da_discover_flow import DISCOVER_DIVIDER

    def message(text):
        return ChatMessage(
            request_id="CVDA-2026-0001",
            sent_at=datetime(2026, 10, 30, tzinfo=UTC),
            speaker="system",
            text=text,
        )

    assert parts.chat_bubble(message(DISCOVER_DIVIDER)).label == DISCOVER_DIVIDER
    assert "hello" in all_text(parts.chat_bubble(message("hello")))


def test_discover_statuses_have_pill_colours():
    colours = {
        "SEARCHING": "blue",
        "SIMILAR_IMPLEMENTATION_FOUND": "green",
        "NO_RELIABLE_MATCH": "orange",
        "DISCOVERY_CONFIRMED": "green",
        "ESCALATION_REQUIRED": "red",
    }
    for status, colour in colours.items():
        assert parts.status_pill(status).color == colour
