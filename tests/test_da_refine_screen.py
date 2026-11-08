"""The Refine composer on screen (Phase 8 step 13a, rows 8-1, 8-2, 8-12)."""

import pytest

from agents import da_refine_screen as screen
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import read_approach_versions
from layouts import da_build_panel as bp
from layouts import da_refine_panels as rp
from layouts import da_workspace_panel as panel
from pydantic_classes.da_build_models import BuildState, BuildView, TestRow
from pydantic_classes.da_refine_models import RefineState, TestSet
from tests.da_refine_play import records_of, written_request
from tests.da_tree import all_text, by_id, components

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return settings


def draw(request_id):
    return cb.show_page(f"?request={request_id}", 0)


def button_labels(tree):
    return [all_text(b) for b in components(tree, "Button")]


def text_box(tree):
    return [t for t in components(tree, "Textarea") if getattr(t, "id", None) == cb.TEXT_ID][0]


def test_8_1_written_request_offers_refine_rescan_restore_and_help(settings):
    request_id, _ = written_request(settings)

    tree = draw(request_id)

    labels = button_labels(tree)
    assert "Re-scan" in labels
    assert "Restore an earlier version" in labels
    assert "Get help" in labels
    assert by_id(tree, panel.ws_button_id("rescan", "bar")) is not None
    assert not text_box(tree).disabled
    assert all_text(by_id(tree, bp.EDIT_HINT_ID)) == "Edit anything, then click Re-scan."
    assert "Check my edits" not in labels  # nothing re-scanned yet


def test_8_2_no_refine_box_while_building_or_handed_off():
    for status in ("BUILDING", "HANDED_OFF", "READY_TO_BUILD"):
        box = screen.make_refine_box(status, "b_written", 0, 5)
        assert not box.offered and not box.browser_buttons and not box.buttons
    running = screen.make_refine_box("READY_FOR_REVIEW", "b_running", 0, 5)
    assert not running.offered


def test_8_2_drawn_building_screen_has_no_refine_buttons(settings):
    request_id, _ = written_request(settings)
    box = screen.get_refine_box(settings, request_id, "BUILDING", "b_running", "picker")
    assert not box.offered


def test_8_12_cap_closes_the_box_but_rescan_and_check_stay(settings, monkeypatch):
    request_id, _ = written_request(settings)
    monkeypatch.setattr(
        screen, "get_refine_state", lambda s, r: RefineState(request_id=r, refine_count=5)
    )

    tree = draw(request_id)

    box = text_box(tree)
    assert box.disabled
    assert "refined 5 times" in box.placeholder
    assert "Re-scan" in button_labels(tree)
    capped = screen.make_refine_box("READY_FOR_REVIEW", "b_written", 5, 5, has_edits=True)
    assert ("check_edits", "Check my edits") in capped.buttons


def _two_versions(settings, request_id):
    first = records_of(settings, request_id)[-1]
    second = first.model_copy(update={"version": first.version + 1, "title": "A new title"})
    return first, second


def test_13b_one_record_version_shows_no_record_history_but_lists_approaches(settings):
    request_id, _ = written_request(settings)

    tree = draw(request_id)

    assert by_id(tree, rp.HISTORY_ID) is None
    assert "source proposal" in all_text(by_id(tree, rp.APPROACH_LIST_ID))


def test_13b_history_lists_each_diff_and_marks_criteria(settings):
    request_id, _ = written_request(settings)
    first, second = _two_versions(settings, request_id)

    history = screen.make_history([first, second], [])

    assert len(history.diffs) == 1
    assert history.diffs[0].fields[0].field == "title"
    text = all_text(rp.version_history_blocks(history)[0])
    assert "v1 to v2" in text
    assert "A new title" in text


def test_13b_approach_list_shows_the_source_of_each_version(settings):
    request_id, _ = written_request(settings)
    assert rp.approach_version_blocks(screen.VersionHistory()) == []
    with open_db(settings.db_path) as conn:
        one = read_approach_versions(conn, request_id)
    two = [one[-1], one[-1].model_copy(update={"approach_version": 2, "source": "revision"})]

    history = screen.make_history([], two)

    text = all_text(rp.approach_version_blocks(history)[0])
    assert "source revision" in text


def _view(tests):
    return BuildView(
        state=BuildState(request_id="CVDA-2026-0001"), revision=1, request_status="X", tests=tests
    )


def test_13c_tests_get_new_bug_and_yours_tags_and_a_version_line():
    rows = [
        TestRow(test_id="T-1", criterion_id="AC-1", description="old", result="pass"),
        TestRow(test_id="T-2", criterion_id="AC-2", description="fresh"),
        TestRow(test_id="T-3", criterion_id="AC-3", description="mine", yours=True),
    ]
    text = (
        "class T:\n"
        "    def test_T_90_AC_1(self):\n"
        '        """The bug test."""\n'
        "    def test_T_91_AC_1(self):\n"
        '        """My own test."""\n'
    )
    sets = [
        TestSet(
            request_id="CVDA-2026-0001",
            test_set_version=2,
            approach_version=2,
            added_case_ids=["T-90", "T-91"],
            text=text,
            fingerprint="x",
        ),
    ]

    tagged = screen.tag_tests(_view(rows), {"T-2"}, {"T-91"}, sets)

    tags = {row.test_id: row.tag for row in tagged.tests}
    assert tags == {"T-1": "", "T-2": "New", "T-3": "Yours", "T-90": "Bug", "T-91": "Yours"}
    assert tagged.tests_note == "Test set version 2, approach version 2"
    html = all_text(bp.tests_tab(tagged))
    assert "T-90 (Bug)" in html and "T-2 (New)" in html


def test_13c_no_test_sets_means_no_note():
    tagged = screen.tag_tests(_view([]), set(), set(), [])
    assert tagged.tests_note == ""


def test_download_mode_says_upload_folder_to_rescan():
    box = screen.make_refine_box("NOT_PASSING", "b_written", 0, 5, mode="download")
    assert box.browser_buttons == [("rescan", "Upload folder to re-scan")]
