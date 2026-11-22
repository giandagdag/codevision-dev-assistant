"""The Workspace on screen and in the callbacks (rows 5-1, 5-22, 5-25 and the four-hop chain)."""

import pytest
from dash import Dash, no_update
from dash.exceptions import PreventUpdate

from agents import da_workspace_flow as flow
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from callbacks.screen_callbacks import da_workspace_callbacks as wcb
from db_table_functions.db_tbl_da_understand import STALE_MESSAGE
from layouts import da_developer_assistant_page as page
from layouts import da_workspace_panel as panel
from tests.da_tree import all_text, by_id, components
from tests.da_workspace_play import MODIFY, facts_of, good_folder, pick, ready_to_build_id, texts

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def request_id(settings):
    return ready_to_build_id(settings)


def draw(request_id):
    return cb.show_page(f"?request={request_id}", 0)


def button_labels(tree, kind):
    return [
        all_text(b)
        for b in components(tree, "Button")
        if isinstance(getattr(b, "id", None), dict) and b.id["type"] == kind
    ]


def tab(tree, name):
    return [t for t in components(tree, "TabsTab") if all_text(t) == name][0]


def chip_text(tree):
    return all_text(by_id(tree, "da-ws-chip"))


# --- the screen ---


def test_5_1_before_a_folder_the_chip_says_none_and_choose_is_active(settings, request_id):
    tree = draw(request_id)

    assert "No workspace chosen" in chip_text(tree)
    # "Use <name>" is drawn hidden; the browser shows it when it remembers a folder (D-B).
    assert button_labels(tree, panel.WS_BTN_TYPE) == [
        "Use remembered folder",
        "Choose workspace folder",
    ]
    assert by_id(tree, panel.ws_button_id("use_remembered", "bar")).style == {"display": "none"}
    wanted = "Choose workspace folder"
    chooser = [b for b in components(tree, "Button") if all_text(b) == wanted][0]
    assert not chooser.disabled
    assert chooser.id == panel.ws_button_id("choose", "bar")
    assert tab(tree, "Build").disabled  # the Build tab waits for a ready workspace
    assert "READY TO BUILD" in all_text(tree)
    state = by_id(tree, page.STATE_ID).data
    assert state["workspace"] is True and state["revision"] == 0


def planned_file_blocked_folder():
    """B3: the plan changes a file this folder does not have (the plan, not the folder, is off)."""
    folder = good_folder()
    del folder.files[MODIFY]
    folder.files["src/agents/other.py"] = "x\n"
    return folder


def test_a_wrong_folder_shows_the_blocker_the_chip_and_two_ways_out(settings, request_id):
    folder = good_folder()
    del folder.files["src/callbacks/da_calls.py"]
    pick(settings, request_id, folder)

    tree = draw(request_id)

    assert "Not a CodeVision folder" in chip_text(tree)
    assert "B1:" in all_text(tree)
    assert "This folder doesn't match the plan yet:" in all_text(tree)
    assert button_labels(tree, panel.WS_BTN_TYPE) == ["Choose another folder"]
    assert button_labels(tree, page.CHOICE_TYPE) == ["Get help"]  # F6: not the plan's fault


def test_a_blocker_about_a_planned_file_shows_the_three_ways_out(settings, request_id):
    pick(settings, request_id, planned_file_blocked_folder())

    tree = draw(request_id)

    assert "B3:" in all_text(tree)
    assert button_labels(tree, panel.WS_BTN_TYPE) == ["Choose another folder"]
    assert button_labels(tree, page.CHOICE_TYPE) == ["Change the approach", "Get help"]


def test_5_31_a_ready_workspace_has_a_status_only_chip_the_build_tab_and_the_approach_note(
    settings, request_id
):
    pick(settings, request_id, good_folder())

    tree = draw(request_id)

    chip = chip_text(tree)
    assert "codevision" in chip and "✅" in chip
    # P30: the chip is status only. Change folder and Reconnect are chat buttons, once each.
    # F7: no manual Re-scan button; the Build button already re-scans by itself.
    assert [b for b in components(by_id(tree, "da-ws-chip"), "Button")] == []
    assert sorted(button_labels(tree, panel.WS_BTN_TYPE)) == [
        "Build",
        "Change folder",
        "Reconnect",
    ]
    reconnect = by_id(tree, panel.ws_button_id("reconnect", "bar"))
    assert reconnect.style == {"display": "none"}  # the browser shows it only when it must
    assert by_id(tree, panel.WS_PERM_NEEDS_ID).style == {"display": "none"}
    assert not tab(tree, "Build").disabled
    text = all_text(by_id(tree, "da-ws-summary"))
    assert text.startswith("Workspace: codevision. Checked ") and text.endswith(".")
    table = all_text(by_id(tree, "da-ws-files"))
    assert MODIFY in table and "Change" in table and "New" in table
    assert "Created" not in table and "tests/" not in table  # C1: no tests-folder row
    # 6-1: Build is a real, enabled, browser-run button now (not the old disabled one).
    build = by_id(tree, panel.ws_button_id("build", "bar"))
    assert not getattr(build, "disabled", False) and build.children == "Build"
    assert "Checked: found in your workspace" in all_text(by_id(tree, "da-file-plan"))


def test_the_checked_time_is_singapore_time_in_the_spec_style(settings, request_id):
    from datetime import UTC, datetime

    now = datetime(2026, 11, 1, 7, 40, tzinfo=UTC)  # 15:40 in Singapore
    view = flow.get_workspace_view(settings, request_id).model_copy(update={"checked_at": now})

    assert panel._short_time(now) == "1 Nov, 15:40"
    assert "Checked 1 Nov, 15:40." in all_text(panel.build_panel(view))


def test_a_missing_file_to_change_shows_the_blocker_text_in_the_approach_tab(settings, request_id):
    folder = good_folder()
    del folder.files[MODIFY]
    folder.files["src/agents/other.py"] = "x\n"
    pick(settings, request_id, folder)

    tree = draw(request_id)

    assert "does not have it" in all_text(by_id(tree, "da-file-plan"))
    assert "Checked: found in your workspace" not in all_text(tree)


def test_5_22_the_fallback_step_offers_the_zip_upload_and_the_picker_again(settings, request_id):
    flow.use_fallback(settings, request_id, "unsupported", 0)

    tree = draw(request_id)

    assert button_labels(tree, panel.WS_BTN_TYPE) == [
        "Download ZIP",
        "Upload folder to check",
        "Try the folder picker again",
    ]
    assert "Download mode" in chip_text(tree)
    assert components(by_id(tree, "da-ws-chip"), "Button") == []  # status only (P30)


def test_5_31_download_mode_at_ready_offers_zip_and_upload_in_the_bar_only(settings, request_id):
    view = flow.use_fallback(settings, request_id, "unsupported", 0)
    flow.check_uploaded(
        settings, request_id, facts_of(settings, request_id, good_folder()), view.revision
    )

    tree = draw(request_id)

    assert flow.get_workspace_view(settings, request_id).step == "ws_ready"
    assert button_labels(tree, panel.WS_BTN_TYPE) == [
        "Download ZIP",
        "Upload folder to re-scan",
        "Build",  # in download mode the pre-build re-scan is the upload (JavaScript)
    ]
    assert components(by_id(tree, "da-ws-chip"), "Button") == []
    assert "Download mode" in chip_text(tree)


def test_5_31_the_build_tab_has_no_re_scan_button(settings, request_id):
    pick(settings, request_id, good_folder())
    view = flow.get_workspace_view(settings, request_id)

    buttons_in_tab = components(panel.build_panel(view), "Button")

    assert buttons_in_tab == []  # the Build button is under the chat, once (P30)
    assert "Re-scan" not in button_labels(draw(request_id), panel.WS_BTN_TYPE)  # F7


def test_5_31_reconnect_is_drawn_only_at_ws_ready(settings, request_id):
    assert "Reconnect" not in button_labels(draw(request_id), panel.WS_BTN_TYPE)
    folder = good_folder()
    del folder.files["src/callbacks/da_calls.py"]
    pick(settings, request_id, folder)

    assert "Reconnect" not in button_labels(draw(request_id), panel.WS_BTN_TYPE)


def test_a_workspace_step_has_no_typed_input(settings, request_id):
    tree = draw(request_id)

    text_box = by_id(tree, page.TEXT_ID)
    assert text_box.disabled is True  # buttons only on every workspace step


# --- the server-run buttons ---


def click(settings, tree, index):
    state = by_id(tree, page.STATE_ID).data
    return cb.perform_action(settings, {"type": page.CHOICE_TYPE, "index": index}, None, state, 0)


def test_get_help_and_change_the_approach_buttons_reach_the_workspace_flow(settings, request_id):
    pick(settings, request_id, planned_file_blocked_folder())
    tree = draw(request_id)

    click(settings, tree, 1)  # Get help

    view = flow.get_workspace_view(settings, request_id)
    assert view.request.status == "ESCALATION_REQUIRED"
    assert view.open_item == "Escalated in Workspace: ws_blocked"


def test_change_the_approach_button_moves_the_request_back(settings, request_id):
    pick(settings, request_id, planned_file_blocked_folder())

    click(settings, draw(request_id), 0)

    assert flow.get_workspace_view(settings, request_id).request.status == "APPROACH_PROPOSED"
    assert "What should change?" in all_text(draw(request_id))


def test_5_25_a_click_from_an_old_window_gets_the_stale_message(settings, request_id):
    folder = good_folder()
    del folder.files["src/callbacks/da_calls.py"]
    pick(settings, request_id, folder)
    state = by_id(draw(request_id), page.STATE_ID).data

    result = cb.perform_action(
        settings, {"type": page.CHOICE_TYPE, "index": 0}, None, state | {"revision": 0}, 0
    )

    assert result == (no_update, no_update, STALE_MESSAGE)
    assert flow.get_workspace_view(settings, request_id).request.status == "READY_TO_BUILD"


# --- the four hops ---


def ctx_of(settings, request_id):
    return panel.workspace_context(flow.get_workspace_view(settings, request_id))


def test_the_whole_chain_with_the_pretend_folder_reaches_ws_ready(settings, request_id):
    folder = good_folder()
    ctx = ctx_of(settings, request_id)
    event = {"kind": "facts", "nonce": 1,
             "facts": facts_of(settings, request_id, folder).model_dump(mode="json")}

    refresh, job, pack, message = wcb.handle_workspace_event(settings, event, ctx, 5)

    assert refresh is no_update and pack is no_update and message == ""
    assert job["files"] == []  # the check writes nothing (C1)
    report = folder.run_job(flow.WriteJob.model_validate(
        {k: v for k, v in job.items() if k != "nonce"}
    )).model_dump(mode="json") | {"nonce": 2}

    refresh, message = wcb.finish_workspace_write(settings, report, event, ctx, 5)

    assert (refresh, message) == (6, "")
    view = flow.get_workspace_view(settings, request_id)
    assert view.step == "ws_ready"
    assert "passed the check" in " ".join(texts(view, "assistant"))
    assert "Tests folder" not in " ".join(texts(view, "assistant"))


def test_a_blocked_folder_ends_at_hop_two_with_a_refresh(settings, request_id):
    folder = good_folder()
    del folder.files["src/web/da_page.py"]
    ctx = ctx_of(settings, request_id)
    event = {"kind": "facts", "nonce": 1,
             "facts": facts_of(settings, request_id, folder).model_dump(mode="json")}

    refresh, job, pack, message = wcb.handle_workspace_event(settings, event, ctx, 5)

    assert (refresh, job, message) == (6, None, "")
    assert flow.get_workspace_view(settings, request_id).step == "ws_blocked"


def test_5_21_a_cancelled_picker_event_leaves_only_the_chat_line(settings, request_id):
    ctx = ctx_of(settings, request_id)

    refresh, job, pack, message = wcb.handle_workspace_event(
        settings, {"kind": "cancelled", "nonce": 1}, ctx, 0
    )

    assert refresh == 1 and message == ""
    view = flow.get_workspace_view(settings, request_id)
    assert view.step == "start" and texts(view, "assistant")[-1] == "No folder chosen."


def test_5_22_a_missing_picker_event_moves_to_the_fallback_step(settings, request_id):
    ctx = ctx_of(settings, request_id)

    wcb.handle_workspace_event(
        settings, {"kind": "fallback", "reason": "unsupported", "nonce": 1}, ctx, 0
    )

    assert flow.get_workspace_view(settings, request_id).step == "ws_fallback"


def test_5_23_the_download_event_hands_the_browser_the_zip_pieces(settings, request_id):
    flow.use_fallback(settings, request_id, "unsupported", 0)
    ctx = ctx_of(settings, request_id)

    refresh, job, pack, message = wcb.handle_workspace_event(
        settings, {"kind": "download", "nonce": 3}, ctx, 0
    )

    assert refresh == 1 and job is None
    assert pack["files"] == []  # C5: code files only, and a build has not made any yet
    assert pack["readme_name"] == "READ_ME_FIRST.txt" and "Unzip" in pack["readme"]


def test_5_24_an_upload_event_runs_the_check_on_what_arrived(settings, request_id):
    flow.use_fallback(settings, request_id, "unsupported", 0)
    ctx = ctx_of(settings, request_id)
    event = {"kind": "upload_facts", "nonce": 1,
             "facts": facts_of(settings, request_id, good_folder()).model_dump(mode="json")}

    refresh, *_ = wcb.handle_workspace_event(settings, event, ctx, 0)

    view = flow.get_workspace_view(settings, request_id)
    assert refresh == 1 and view.step == "ws_ready" and view.mode == "download"


def test_a_rescan_event_at_ready_lists_the_change(settings, request_id):
    folder = good_folder()
    pick(settings, request_id, folder)
    folder.edit(MODIFY, "def validate(path):\n    return None\n")
    ctx = ctx_of(settings, request_id)
    event = {"kind": "scan_facts", "nonce": 1,
             "facts": facts_of(settings, request_id, folder).model_dump(mode="json")}

    wcb.handle_workspace_event(settings, event, ctx, 0)

    view = flow.get_workspace_view(settings, request_id)
    assert {row.path: row.status for row in view.rows}[MODIFY] == "Changed by you"


def test_5_25_a_hop_with_an_old_revision_shows_the_stale_message_and_saves_nothing(
    settings, request_id
):
    folder = good_folder()
    ctx = ctx_of(settings, request_id) | {"ws_revision": 7}
    event = {"kind": "facts", "nonce": 1,
             "facts": facts_of(settings, request_id, folder).model_dump(mode="json")}

    refresh, job, pack, message = wcb.handle_workspace_event(settings, event, ctx, 0)

    assert message == STALE_MESSAGE and job is no_update


def test_an_odd_event_is_refused_without_saving(settings, request_id):
    ctx = ctx_of(settings, request_id)

    result = wcb.handle_workspace_event(
        settings, {"kind": "facts", "facts": {"folder_name": ""}, "nonce": 1}, ctx, 0
    )

    assert result[3] == wcb.UNEXPECTED
    with pytest.raises(PreventUpdate):
        wcb.handle_workspace_event(settings, {"kind": "mystery", "nonce": 1}, ctx, 0)
    with pytest.raises(PreventUpdate):
        wcb.handle_workspace_event(settings, None, ctx, 0)
    assert flow.get_workspace_view(settings, request_id).revision == 0


# --- wiring ---


def test_register_attaches_the_workspace_hops():
    app = Dash(__name__, suppress_callback_exceptions=True)
    cb.register_da_developer_assistant_page_callbacks(app)

    # after draw, action, card 2 (Phase 9), enter-to-send, the build poll, the form, the finding
    # buttons (Phase 7)
    # (Fix G5 N6 put one more page-content callback at index 1, so the hops start at 8.)
    hops = app._callback_list[8:]

    # 8 workspace hops, then the 3 Refine callbacks of Phase 8 step 16 (buttons, picks, add case)
    # then the card 1 switch offer answer of Phase 9 step 18a
    # then the mark dropdowns of the Safety net tab (Phase 9 step 18b)
    # then the scope tick list (step 18c) and the multi-pick confirm (step 18d)
    # then the Handoff buttons and the Copy summary script (Phase 10 step 5)
    # then one more (B1 step 6: the two buttons of a test that disagrees with a criterion)
    # then one more (B2 step 10: Let the AI describe it)
    assert len(hops) == 8 + 3 + 1 + 1 + 1 + 1 + 2 + 1 + 1
    click_hop = hops[0]
    assert click_hop["prevent_initial_call"] is True
    assert click_hop["clientside_function"]["function_name"]
    outputs = [h["output"] for h in hops[:8]]
    assert "da-ws-event.data" in outputs[0] and "da-ws-report.data" in outputs[2]
    assert any("use_remembered" in str(out) for out in outputs)
    assert hops[1]["running"]["running"] == {"da-busy.style": {"display": "block"}}


def test_every_clientside_hop_carries_the_browser_script_once():
    from web.da_workspace_bridge import clientside_function, workspace_script

    function = clientside_function("job", wcb.WRITE_BODY)

    assert function.count("window.daWorkspace = {") == 1
    assert function.startswith("function(job) {") and "daWorkspace.write(job)" in function
    assert workspace_script().count("showDirectoryPicker") >= 1


def test_no_two_buttons_on_the_workspace_screen_share_an_id(settings, request_id):
    """Dash cannot tell two components with one id apart: a click went nowhere (found in the
    real-browser test, where the chip and the bar both had Re-scan)."""
    pick(settings, request_id, good_folder())
    tree = draw(request_id)

    ids = [
        str(b.id) for b in components(tree, "Button") if isinstance(getattr(b, "id", None), dict)
    ] + [b.id for b in components(tree, "Button") if isinstance(getattr(b, "id", None), str)]

    assert len(ids) == len(set(ids))


def test_a_reconnected_event_only_redraws_and_adds_no_chat_line(settings, request_id):
    pick(settings, request_id, good_folder())
    before = len(flow.get_workspace_view(settings, request_id).messages)
    ctx = ctx_of(settings, request_id)

    refresh, job, pack, message = wcb.handle_workspace_event(
        settings, {"kind": "reconnected", "nonce": 1}, ctx, 4
    )

    assert (refresh, job, message) == (5, None, "")
    assert len(flow.get_workspace_view(settings, request_id).messages) == before


def test_6_32_a_different_folder_event_adds_the_wording_and_links_nothing(settings, request_id):
    folder = good_folder()
    view, _ = pick(settings, request_id, folder)
    ctx = ctx_of(settings, request_id)

    refresh, *_ = wcb.handle_workspace_event(
        settings, {"kind": "different_folder", "nonce": 9, "name": "codevision"}, ctx, 0
    )

    after = flow.get_workspace_view(settings, request_id)
    assert refresh == 1 and after.step == "ws_ready" and after.revision == view.revision
    assert texts(after, "assistant")[-1].startswith("This is a different folder that is also")
