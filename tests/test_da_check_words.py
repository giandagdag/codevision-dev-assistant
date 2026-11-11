"""FX-10 and FX-11 (Phase 8 fix 1, F6 and F9): a check run reads as testing, with an honest count.
No browser: the page is drawn as a component tree and the loop runs on the fake provider."""

import pytest

from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents import da_check_words as words
from agents import da_refine_flow as rflow
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from layouts import da_build_panel as bp
from layouts import da_developer_assistant_page as page
from tests.da_build_play import MODIFY
from tests.da_refine_play import written_request
from tests.da_tree import all_text, by_id, components
from tests.da_workspace_play import facts_of

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return settings


def draw(request_id):
    return cb.show_page(f"?request={request_id}", 0)


def start_check_after_edit(settings):
    request_id, folder = written_request(settings)
    folder.edit(MODIFY, "# my own note\n" + folder.files[MODIFY])
    rflow.rescan(
        settings,
        request_id,
        facts_of(settings, request_id, folder),
        flow.get_revision(settings, request_id),
    )
    rflow.start_check(settings, request_id, flow.get_revision(settings, request_id))
    return request_id


def button_labels(tree):
    return [
        all_text(b)
        for b in components(tree, "Button")
        if isinstance(getattr(b, "id", None), dict) and b.id.get("type") == page.CHOICE_TYPE
    ]


def test_fx_10_a_running_check_run_reads_as_testing(settings):
    request_id = start_check_after_edit(settings)

    tree = draw(request_id)
    text = all_text(tree)

    assert "TESTING" in all_text(by_id(tree, "da-build-chat-status"))
    assert words.CHECK_BANNER in all_text(by_id(tree, bp.BANNER_ID))
    assert words.CHECK_CHAT_LINE in text
    assert button_labels(tree) == [words.CHECK_CANCEL_LABEL]
    # ("Round 1 of 3" also names the Discovery round elsewhere on the page: look at the banner.)
    assert "Round" not in all_text(by_id(tree, bp.BANNER_ID))
    # Screen only: the system status is still BUILDING.
    assert flow.get_build_view(settings, request_id).request_status == "BUILDING"


def test_fx_10_a_normal_build_keeps_its_words(settings):
    from tests.da_build_play import ready_with_workspace

    request_id, _ = ready_with_workspace(settings)
    flow.start_build(settings, request_id, flow.get_revision(settings, request_id))

    tree = draw(request_id)

    assert "BUILDING" in all_text(by_id(tree, "da-build-chat-status"))
    assert "Round 1 of 3" in all_text(by_id(tree, bp.BANNER_ID))
    assert button_labels(tree) == ["Cancel build"]


def test_fx_10_a_finished_test_run_has_its_own_box_title_and_versions_name(settings):
    request_id = start_check_after_edit(settings)
    loop.run_build(settings, request_id)

    text = all_text(draw(request_id))

    assert words.CHECK_BOX_TITLE in text and "Rounds used" not in text
    assert words.check_version_name(flow.get_state(settings, request_id).build_number) in text


def test_fx_11_the_line_counts_only_the_files_he_edited(settings):
    request_id = start_check_after_edit(settings)
    loop.run_build(settings, request_id)

    lines = [line.text for line in flow.get_build_view(settings, request_id).progress]

    planned = len(flow.get_build_view(settings, request_id).rows)
    assert words.testing_files_line(planned, 1) in lines


def test_the_count_line_wording():
    assert words.testing_files_line(2, 1) == "Testing 2 planned file(s) (1 edited by you)"
    assert words.testing_files_line(2, 0) == "Testing 2 planned file(s) with your new test"
