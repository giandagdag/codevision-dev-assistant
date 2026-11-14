"""Phase 10 step 5: the Handoff screen (spec sections 6 and 14). The page functions are called
directly, as the Refine callback tests do; no browser, fake provider only."""

from datetime import UTC, datetime

import pytest
from dash import no_update
from dash.exceptions import PreventUpdate

from agents import da_build_flow as build_flow
from agents import da_build_loop as loop
from agents import da_handoff_flow as flow
from agents import da_tester_flow as tester_flow
from agents.da_handoff_screen import (
    CHECK_FOLDER_KEY,
    CHECK_FOLDER_LABEL,
    UPLOAD_CHECK_LABEL,
    make_handoff_box,
)
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from callbacks.screen_callbacks import da_handoff_callbacks as hcb
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_handoff import get_last_tested_fingerprints
from layouts import da_developer_assistant_page as page
from pydantic_classes.da_handoff_models import HandoffRow, HandoffState, HandoffView
from pydantic_classes.da_workspace_models import FileFact, FolderFacts
from styles import da_styles
from tests.da_build_play import chat, ready_with_workspace
from tests.da_tree import all_text, by_id, components
from web import da_web_components as parts

NOW = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)


@pytest.fixture
def settings(make_settings, published_rulebook, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def built_open(settings):
    request_id = ready_with_workspace(settings)[0]
    build_flow.start_build(settings, request_id, build_flow.get_revision(settings, request_id))
    assert loop.run_build(settings, request_id) == "done"
    return settings, request_id


def accept_open_findings(settings, request_id):
    for row in tester_flow.get_tester_view(settings, request_id).rows:
        if row.state == "open" and row.finding.severity == "should_fix":
            tester_flow.accept_finding(
                settings,
                request_id,
                build_flow.get_revision(settings, request_id),
                row.finding.finding_id,
                "Made-up reason: the team agreed to leave this as it is.",
            )


def draw(request_id):
    return cb.show_page(f"?request={request_id}", 0)


def state_of(tree) -> dict:
    return dict(by_id(tree, page.STATE_ID).data)


def handoff_keys(tree) -> list[str]:
    return [
        b.id["index"]
        for b in components(tree, "Button")
        if isinstance(getattr(b, "id", None), dict) and b.id.get("type") == page.HANDOFF_TYPE
    ]


def ws_keys(tree) -> list[str]:
    return [
        b.id["index"]
        for b in components(tree, "Button")
        if isinstance(getattr(b, "id", None), dict) and b.id.get("type") == "da-ws-btn"
    ]


def press(settings, tree, key, refresh=0):
    trigger = {"type": page.HANDOFF_TYPE, "index": key}
    return hcb.handle_handoff_button(settings, trigger, 1, state_of(tree), refresh)


def prints_of(settings, request_id) -> dict[str, str]:
    with open_db(settings.db_path) as conn:
        conn.execute("BEGIN")
        return get_last_tested_fingerprints(conn, request_id)


def hand_off(settings, request_id):
    accept_open_findings(settings, request_id)
    state = flow.ready_for_handoff(
        settings, request_id, flow.get_handoff_view(settings, request_id).state.revision, NOW
    )
    return flow.final_check(
        settings, request_id, state.revision, prints_of(settings, request_id), NOW
    )


# --- the pure rule (10-1, 10-10) ---


def view_at(step: str, **extra) -> HandoffView:
    state = HandoffState(request_id="CVDA-2026-0001", step=step, revision=3)
    return HandoffView(state=state, **extra)


def test_the_box_is_empty_outside_the_handoff_statuses():
    assert not make_handoff_box("BUILDING", view_at("h_start")).offered


def test_ready_for_review_offers_only_the_ready_button():
    box = make_handoff_box("READY_FOR_REVIEW", view_at("h_start"))
    assert box.buttons == [("ready", "Ready for handoff")]
    assert box.browser_buttons == [] and box.revision == 3


def test_a_passing_check_offers_the_folder_button_and_download_mode_the_upload_one():
    picker = make_handoff_box("READY_FOR_REVIEW", view_at("h_checking"))
    download = make_handoff_box("READY_FOR_REVIEW", view_at("h_checking"), "download")
    assert picker.browser_buttons == [(CHECK_FOLDER_KEY, CHECK_FOLDER_LABEL)]
    assert download.browser_buttons == [(CHECK_FOLDER_KEY, UPLOAD_CHECK_LABEL)]
    assert "Upload folder to check in" == UPLOAD_CHECK_LABEL


def test_not_passing_offers_no_button_but_says_why():
    box = make_handoff_box("NOT_PASSING", view_at("h_start"))
    assert not box.offered and box.note == "Handoff needs a passing build. Refine, or Get help."


def test_handed_off_is_locked_with_a_follow_up_button_and_opens_on_audit():
    row = HandoffRow(
        request_id="CVDA-2026-0001", record_version=1, approach_version=1, last_tested_build=1,
        summary_text="the summary", handed_off_by="dev1",
    )  # fmt: skip
    box = make_handoff_box("HANDED_OFF", view_at("h_done", handoff=row, locked=True))
    assert box.locked and box.open_tab == "audit" and box.summary == "the summary"
    assert [key for key, _ in box.buttons] == ["follow_up"]


# --- the page ---


def test_ready_for_review_page_shows_the_ready_button_and_the_state_flag(built_open):
    settings, request_id = built_open
    tree = draw(request_id)

    assert handoff_keys(tree) == ["ready"]
    state = state_of(tree)
    assert state["handoff"] is True and state["handoff_revision"] == 0


def test_a_blocked_check_lists_the_finding_and_opens_the_tests_tab(built_open):
    settings, request_id = built_open
    tree = draw(request_id)

    refresh, search, message = press(settings, tree, "ready")
    assert refresh == 1 and search is no_update and message == ""

    again = draw(request_id)
    assert "F-1 (Should fix) is still open: Fix it or Accept, with reason." in all_text(again)
    assert components(again, "Tabs")[0].value == "tests"
    assert handoff_keys(again) == ["ready"]  # he can press it again after fixing


def test_a_clean_check_shows_the_folder_button(built_open):
    settings, request_id = built_open
    accept_open_findings(settings, request_id)
    press(settings, draw(request_id), "ready")

    tree = draw(request_id)

    assert "handoff_check" in ws_keys(tree)
    assert "Check my folder" in all_text(tree)
    assert handoff_keys(tree) == []


def test_a_stale_window_is_shown_under_the_chat(built_open):
    settings, request_id = built_open
    tree = draw(request_id)
    press(settings, tree, "ready")  # moves the revision on

    refresh, search, message = press(settings, tree, "ready")

    assert refresh is no_update and "updated in another window" in message


def test_a_click_without_the_handoff_flag_is_ignored(settings):
    with pytest.raises(PreventUpdate):
        hcb.handle_handoff_button(
            settings, {"type": page.HANDOFF_TYPE, "index": "ready"}, 1, {}, 0
        )


# --- handed off ---


def test_a_handed_off_page_is_locked_and_opens_on_the_audit_tab(built_open):
    settings, request_id = built_open
    hand_off(settings, request_id)

    tree = draw(request_id)

    assert components(tree, "Tabs")[0].value == "audit"
    box = by_id(tree, parts.SUMMARY_BOX_ID)
    assert box.value.startswith(request_id) and "tests/" not in box.value
    assert by_id(tree, parts.COPY_BUTTON_ID).children == "Copy summary"
    assert by_id(tree, "da-lock-banner") is not None
    assert "HANDED OFF" in all_text(tree)
    assert handoff_keys(tree) == ["follow_up"]
    assert by_id(tree, "da-send") is None  # read-only composer: no text box, no Send
    step_six = [
        c for c in components(tree) if getattr(c, "id", None) == {"type": "da-step", "step": 6}
    ]
    assert step_six[0].style["background"] == da_styles.STEP_CURRENT["background"]


def test_the_sixth_step_is_lit_only_when_handed_off(built_open):
    settings, request_id = built_open
    before = [
        c
        for c in components(draw(request_id))
        if getattr(c, "id", None) == {"type": "da-step", "step": 6}
    ]
    assert before[0].style.get("background") != da_styles.STEP_CURRENT["background"]


def test_follow_up_opens_a_new_request_that_says_what_it_follows(built_open):
    settings, request_id = built_open
    hand_off(settings, request_id)

    refresh, search, message = press(settings, draw(request_id), "follow_up")

    assert refresh is no_update and message == "" and search.startswith("?request=CVDA-")
    new_page = cb.show_page(search, 0)
    assert by_id(new_page, "da-follows") is not None, all_text(new_page)[:600]
    assert by_id(new_page, "da-follows").children == f"Follows {request_id}"
    assert by_id(draw(request_id), parts.SUMMARY_BOX_ID) is not None  # the old one is untouched


def test_the_done_chat_names_no_git_command_and_a_zip_copy_gets_the_upload_words(
    built_open, monkeypatch
):
    settings, request_id = built_open
    monkeypatch.setattr(flow, "read_workspace_state", lambda conn, rid: None)  # no .git known
    hand_off(settings, request_id)

    done = chat(settings, request_id)[-1]

    assert "Upload the files listed under Files in the summary" in done
    assert "git " not in done.lower()


def test_a_git_clone_gets_the_commit_words(built_open, monkeypatch):
    settings, request_id = built_open

    class Check:
        has_git = True

    class Workspace:
        last_check = Check()

    monkeypatch.setattr(flow, "read_workspace_state", lambda conn, rid: Workspace())
    with open_db(settings.db_path) as conn:
        conn.execute("BEGIN")
        text = flow.done_text(conn, request_id, "the Limits capability lead")

    assert "Commit the changed files from your folder" in text
    assert text.endswith("Add the Limits capability lead as a reviewer.")


# --- the folder read ---


def test_fingerprints_come_from_the_text_and_skip_missing_files():
    facts = FolderFacts(
        folder_name="demo",
        files=[
            FileFact(path="src/a.py", exists=True, parent_exists=True, text="x = 1\n"),
            FileFact(path="src/b.py", exists=False, parent_exists=True),
            FileFact(path="src/c.py", exists=True, parent_exists=True, fingerprint="big-hash"),
        ],
    )

    seen = hcb.fingerprints_from_facts(facts)

    assert set(seen) == {"src/a.py", "src/c.py"} and seen["src/c.py"] == "big-hash"


def test_summary_box_is_plain_text_with_a_copy_button():
    box = parts.summary_box("line 1\nline 2")
    assert by_id(box, parts.SUMMARY_BOX_ID).readOnly is True
    assert by_id(box, parts.COPY_BUTTON_ID) is not None
    assert by_id(box, parts.COPY_NOTE_ID) is not None
