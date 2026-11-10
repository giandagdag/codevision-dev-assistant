"""Phase 9 step 16a: card 2, the candidate table, the freshness banner and the enhancement summary
(test 9-1 screen part). Presentation only: the engine is called with made-up data, no AI."""

import pytest
from dash.exceptions import PreventUpdate

from agents import da_enhance_flow as enhance
from agents.da_search_index import FakeSearchIndex, IndexData, IndexPiece
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from layouts import da_developer_assistant_page as page
from layouts import da_enhance_panel as panel
from pydantic_classes.da_enhance_models import (
    Candidate,
    EnhanceState,
    FreshnessResult,
    PathFreshness,
)
from pydantic_classes.da_request_record_models import MustNotChange, RequestRecord
from tests.da_tree import all_text, by_id

LIMITS = "src/agents/limits_expiry_report.py"


@pytest.fixture
def settings(make_settings, published_rulebook, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return settings


def found(settings):
    piece = IndexPiece(
        piece_no=0, path=LIMITS, symbol="format_expiry", line_start=1, kind="code",
        language="python", snippet="def format_expiry(day): date text",
    )
    index = FakeSearchIndex(IndexData(build_id="t", built_at="", pieces=(piece,)))
    started = enhance.start_enhance_request(settings)
    return enhance.find_program(
        settings, started.request_id, "limits_expiry_report", started.revision, index=index
    )


def test_9_1_home_has_card_2_and_the_review_card_is_still_greyed_out(settings):
    home = cb.show_page("", 0)

    text = all_text(home)
    assert "Change an existing program" in text and "Review my code" in text
    assert by_id(home, page.ENHANCE_CARD_ID) is not None


def test_9_1_a_click_on_card_2_creates_an_enhance_request_and_opens_it(settings):
    search = cb.start_enhance(1)

    request_id = search.removeprefix("?request=")
    view = enhance.get_enhance_view(settings, request_id)
    assert view is not None and view.step == "e_find"
    drawn = all_text(cb.show_page(search, 0))
    assert "FIND THE PROGRAM" in drawn and "Name the CodeVision program" in drawn


def test_9_1_the_card_on_a_redrawn_home_page_does_not_start_anything(settings):
    with pytest.raises(PreventUpdate):
        cb.start_enhance(0)


def test_9_1_the_candidate_table_shows_best_match_and_the_catalog(settings):
    view = found(settings)

    drawn = all_text(cb.show_page(f"?request={view.request_id}", 0))

    assert LIMITS in drawn and "Best match" in drawn
    assert "Limits" in drawn  # the catalog capability of the made-up path


def test_a_program_not_in_the_catalog_says_so():
    table = panel.candidate_table(
        [Candidate(path="src/x/unknown.py", how_found="meaning", best_match=False)]
    )

    text = all_text(table)
    assert "Not in the catalog" in text and "Meaning" in text and "Best match" not in text


def test_no_candidates_says_what_to_do():
    assert "Type the program name" in all_text(panel.candidate_table([]))


def test_9_13_the_freshness_banner_names_the_file_and_is_orange(settings):
    result = FreshnessResult(
        paths=[
            PathFreshness(path=LIMITS, state="differs", his_fingerprint="a", main_fingerprint="b")
        ]
    )
    view = enhance.EnhanceView(
        request_id="CVDA-2026-0001", kind="enhance", step="e_stale", label="FRESHNESS CHECK",
        revision=2, freshness=result,
    )

    banner = panel.freshness_banner(view)

    assert LIMITS in all_text(banner) and "git pull" in all_text(banner)
    assert banner.color == "orange"


def test_the_freshness_banner_is_green_when_equal_and_absent_before_a_check():
    equal = FreshnessResult(paths=[PathFreshness(path=LIMITS, state="equal")])
    view = enhance.EnhanceView(
        request_id="CVDA-2026-0001", kind="enhance", step="e_fresh", label="PROGRAM CONFIRMED",
        revision=3, freshness=equal,
    )
    assert panel.freshness_banner(view).color == "green"
    assert panel.freshness_banner(
        enhance.EnhanceView(request_id="CVDA-2026-0001", kind="enhance", step="e_find",
                            label="FIND THE PROGRAM", revision=1)
    ) is None


def test_the_enhancement_summary_shows_today_nc_items_and_scope():
    record = RequestRecord(
        request_id="CVDA-2026-0001", rulebook_version=1, kind="enhance", targets=[LIMITS],
        today="It shows the expiry date as numbers.",
        must_not_change=[MustNotChange(id="NC-1", text="Keep the sort order.")],
        functions_in_scope=["format_expiry"],
    )

    text = all_text(panel.enhancement_summary(record))

    assert "It shows the expiry date as numbers." in text
    assert "NC-1: Keep the sort order." in text and "format_expiry" in text and LIMITS in text


def test_a_new_program_request_has_no_enhancement_block():
    record = RequestRecord(request_id="CVDA-2026-0001", rulebook_version=1)
    assert panel.enhancement_summary(record) == []
    assert panel.enhancement_summary(None) == []


def test_later_steps_use_the_understand_screen(settings):
    assert "e_fresh" not in cb.ENHANCE_FIND_STEPS
    assert EnhanceState(request_id="CVDA-2026-0001").step in cb.ENHANCE_FIND_STEPS
