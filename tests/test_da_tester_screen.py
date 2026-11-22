"""The Tester's report, the Layer C box and the finding buttons (7-20, 7-22, 7-23)."""

import pytest
from dash.exceptions import PreventUpdate

from agents import da_build_agent as agent
from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents import da_tester_flow as tflow
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from layouts import da_build_panel as bp
from layouts import da_tester_panel as tp
from tests.da_build_play import ready_with_workspace, request_status
from tests.da_tree import all_text, by_id, components

pytestmark = pytest.mark.usefixtures("published_rulebook")

REASON = "I checked it and the plan is fine"


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def request_id(settings):
    return ready_with_workspace(settings)[0]


def built(settings, request_id, monkeypatch=None, *switches):
    if monkeypatch is not None:
        monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset(switches))
    flow.start_build(settings, request_id, flow.get_revision(settings, request_id))
    assert loop.run_build(settings, request_id) == "done"


def draw(request_id):
    return cb.show_page(f"?request={request_id}", 0)


def act_buttons(tree):
    found = {}
    for button in components(tree, "Button"):
        ident = getattr(button, "id", None)
        if isinstance(ident, dict) and ident.get("type") == tp.FINDING_ACT_TYPE:
            found[ident["index"]] = button
    return found


def test_7_23_the_old_layer_c_warning_and_coming_in_phase_7_appear_nowhere(settings, request_id):
    built(settings, request_id)

    tree = draw(request_id)

    text = all_text(tree)
    assert "not built yet" not in text and "Coming in Phase 7" not in text


def test_the_tests_tab_shows_the_label_seven_checks_and_findings_by_severity(settings, request_id):
    built(settings, request_id)

    tree = draw(request_id)

    report = all_text(by_id(tree, tp.REPORT_ID))
    assert "Ready with warnings" in report and "1 Should fix" in report
    checks = all_text(by_id(tree, tp.CHECKS_ID))
    for name in (
        "Every criterion has a test",
        "Files match the file plan",
        "Flag-for-review zones",
    ):
        assert name in checks
    findings = all_text(by_id(tree, tp.FINDINGS_ID))
    assert findings.index("Should fix") < findings.index("FYI")
    assert "1 Tester finding was dropped" in all_text(by_id(tree, tp.DROPPED_ID))
    assert "Show dropped" in all_text(tree) and "Earlier reviews" in all_text(tree)
    assert "Nothing from it is written to your folder" in all_text(by_id(tree, "da-tester-note"))
    assert "fake" in all_text(tree).lower()  # the model name is shown


def test_fx12_findings_table_has_five_columns_and_a_dimmed_detail_line(settings, request_id):
    built(settings, request_id)

    table = by_id(draw(request_id), tp.FINDINGS_ID)

    heads = [all_text(th) for th in components(table, "TableTh")]
    assert heads == ["ID", "Severity", "Where", "Message", "Action"]
    first_row = components(table, "TableTr")[1]
    cells = components(first_row, "TableTd")
    assert len(cells) == 5
    assert cells[0].children.style == tp.ID_STYLE  # F-1 stays on one line
    assert cells[2].children.style == tp.WHERE_STYLE  # a long path wraps
    detail = all_text(cells[3])
    assert "Check " in detail and "Cites: " in detail


def test_7_22_a_should_fix_has_accept_and_a_greyed_fix_it(settings, request_id):
    built(settings, request_id)

    tree = draw(request_id)

    assert any(key.startswith("accept:") for key in act_buttons(tree))
    fix_it = [b for b in components(tree, "Button") if all_text(b) == tp.FIX_IT_TEXT]
    # Phase 8 made Fix it real, but only once the code is in his folder (b_written); a build
    # that is only done (b_done) still shows it greyed.
    assert len(fix_it) == 1 and fix_it[0].disabled is True


def test_7_20_a_must_fix_has_dispute_and_no_accept(settings, request_id, monkeypatch):
    built(settings, request_id, monkeypatch, "review_must_fix_always")

    tree = draw(request_id)

    keys = list(act_buttons(tree))
    assert any(key.startswith("dispute:") for key in keys)
    assert not any(key.startswith("accept:") for key in keys)
    assert "Not passing" in all_text(by_id(tree, tp.REPORT_ID))


def test_g5_19_a_saved_dispute_shows_edit_withdraw_and_one_send_button(
    settings, request_id, monkeypatch
):
    built(settings, request_id, monkeypatch, "review_must_fix_always")
    assert "send:all" not in act_buttons(draw(request_id))
    row = next(
        r
        for r in tflow.get_tester_view(settings, request_id).rows
        if r.finding.severity == "must_fix"
    )
    fid = row.finding.finding_id
    cb.perform_finding_action(
        settings, f"dispute:{fid}", {fid: REASON}, state_of(settings, request_id), 0
    )

    tree = draw(request_id)

    keys = list(act_buttons(tree))
    assert f"withdraw:{fid}" in keys and "send:all" in keys
    assert "Send 1 dispute to my senior" in all_text(tree)
    assert "Disputed, not sent yet" in all_text(tree)


def test_the_layer_c_box_and_this_build_lines(settings, request_id):
    built(settings, request_id)

    tree = draw(request_id)

    layers = all_text(by_id(tree, bp.LAYERS_ID))
    assert "Warnings" in layers and "See the Tester report" in layers
    summary = all_text(by_id(tree, bp.SUMMARY_ID))
    assert "Tester findings: 0 Must fix, 1 Should fix, 1 FYI" in summary
    assert "Tester model:" in summary


def test_the_banner_follows_the_live_label_after_accept(settings, request_id):
    built(settings, request_id)
    row = next(
        r
        for r in tflow.get_tester_view(settings, request_id).rows
        if r.finding.severity == "should_fix"
    )
    tflow.accept_finding(
        settings,
        request_id,
        flow.get_revision(settings, request_id),
        row.finding.finding_id,
        REASON,
    )

    view = tflow.get_build_view(settings, request_id)

    assert view.label == "Ready for your review"
    tree = draw(request_id)
    assert "Accepted: " + REASON in all_text(by_id(tree, tp.FINDINGS_ID))
    assert "Passed" in all_text(by_id(tree, bp.LAYERS_ID))
    assert any(key.startswith("reopen:") for key in act_buttons(tree))


def test_run_again_is_a_chat_button_only_for_unable_to_assess(settings, request_id, monkeypatch):
    built(settings, request_id, monkeypatch, "review_unusable")

    view = tflow.get_build_view(settings, request_id)

    assert (tflow.RERUN_KEY, tflow.RERUN_LABEL) in view.buttons
    assert view.label == "Unable to assess" and view.tester.can_rerun
    other = ready_with_workspace(settings)[0]
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset())
    built(settings, other)
    assert (tflow.RERUN_KEY, tflow.RERUN_LABEL) not in tflow.get_build_view(settings, other).buttons


def test_the_chat_run_again_button_runs_the_review(settings, request_id, monkeypatch):
    built(settings, request_id, monkeypatch, "review_unusable")
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"review_empty"}))
    tree = draw(request_id)
    state = by_id(tree, cb.STATE_ID).data
    index = next(
        i
        for i, (key, _) in enumerate(tflow.get_build_view(settings, request_id).buttons)
        if key == tflow.RERUN_KEY
    )

    cb.perform_action(settings, {"type": cb.CHOICE_TYPE, "index": index}, "", state, 0)

    assert tflow.get_tester_view(settings, request_id).label == "Ready for your review"


# --- the finding buttons (callback side) ---


def state_of(settings, request_id):
    return {
        "request_id": request_id,
        "revision": flow.get_revision(settings, request_id),
        "build": True,
    }


def test_the_accept_button_saves_and_redraws(settings, request_id):
    built(settings, request_id)
    row = next(
        r
        for r in tflow.get_tester_view(settings, request_id).rows
        if r.finding.severity == "should_fix"
    )
    fid = row.finding.finding_id

    refresh, message = cb.perform_finding_action(
        settings, f"accept:{fid}", {fid: REASON}, state_of(settings, request_id), 4
    )

    assert (refresh, message) == (5, "")
    assert tflow.get_tester_view(settings, request_id).label == "Ready for your review"


def test_a_short_reason_shows_the_plain_message_and_redraws_nothing(settings, request_id):
    built(settings, request_id)
    row = next(
        r
        for r in tflow.get_tester_view(settings, request_id).rows
        if r.finding.severity == "should_fix"
    )
    fid = row.finding.finding_id

    refresh, message = cb.perform_finding_action(
        settings, f"accept:{fid}", {fid: "no"}, state_of(settings, request_id), 4
    )

    assert refresh is cb.no_update and "10 to 300 characters" in message


def test_the_dispute_button_saves_and_the_send_button_hands_it_to_a_senior(
    settings, request_id, monkeypatch
):
    built(settings, request_id, monkeypatch, "review_must_fix_always")
    row = next(
        r
        for r in tflow.get_tester_view(settings, request_id).rows
        if r.finding.severity == "must_fix"
    )
    fid = row.finding.finding_id

    cb.perform_finding_action(
        settings, f"dispute:{fid}", {fid: REASON}, state_of(settings, request_id), 0
    )
    assert request_status(settings, request_id) == "NOT_PASSING"

    cb.perform_finding_action(settings, "send:all", {}, state_of(settings, request_id), 0)

    assert request_status(settings, request_id) == "ESCALATION_REQUIRED"


def test_an_unknown_button_or_a_screen_without_a_build_does_nothing(settings, request_id):
    with pytest.raises(PreventUpdate):
        cb.perform_finding_action(settings, "delete:F-1", {}, {"build": True}, 0)
    with pytest.raises(PreventUpdate):
        cb.perform_finding_action(settings, "accept:F-1", {}, {"request_id": request_id}, 0)
