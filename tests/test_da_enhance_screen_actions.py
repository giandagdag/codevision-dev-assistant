"""Phase 9 step 16c: the buttons, the composer and the callbacks of the Enhance steps, and the
browser hand-over for the freshness check (tests 9-1 and 9-48 screen parts). Made-up data, no AI."""

import pytest
from dash.exceptions import PreventUpdate

from agents import da_enhance_flow as enhance
from agents.da_search_index import FakeSearchIndex, IndexData, IndexPiece
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from callbacks.screen_callbacks import da_workspace_callbacks as ws_cb
from layouts import da_developer_assistant_page as page
from layouts import da_enhance_panel as panel
from tests.da_tree import all_text

LIMITS = "src/agents/limits_expiry_report.py"


@pytest.fixture
def settings(make_settings, published_rulebook, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    piece = IndexPiece(
        piece_no=0, path=LIMITS, symbol="format_expiry", line_start=1, kind="code",
        language="python", snippet="def format_expiry(day): date text",
    )
    index = FakeSearchIndex(IndexData(build_id="t", built_at="", pieces=(piece,)))
    monkeypatch.setattr(enhance, "get_search_index", lambda _settings: index)
    return settings


def state_of(view):
    return {"request_id": view.request_id, "revision": view.revision, "enhance": view.step}


def act(settings, view, trigger, text=""):
    """One click or Send, the way handle_action passes it to perform_action."""
    outputs = cb.perform_action(settings, trigger, text, state_of(view), 0)
    return outputs, enhance.get_enhance_view(settings, view.request_id)


def choice(index):
    return {"type": page.CHOICE_TYPE, "index": index}


def label_index(view, text):
    return [label for _key, label in panel.enhance_buttons(view)].index(text)


def searched(settings):
    started = enhance.start_enhance_request(settings)
    _outputs, view = act(settings, started, page.SEND_ID, "limits_expiry_report")
    return view


def facts_event(settings, kind, text):
    fact = {"path": LIMITS, "exists": True, "parent_exists": True, "text": text}
    facts = {"folder_name": "mine", "markers": {}, "looks_like_src": False, "has_git": False,
             "files": [fact]}
    return {"kind": kind, "facts": facts, "nonce": 1}


def context_of(view):
    return panel.enhance_context(view)


def test_send_at_find_runs_a_search_and_moves_to_the_pick_step(settings):
    view = searched(settings)

    assert view.step == "e_pick" and [c.path for c in view.candidates] == [LIMITS]


def test_the_pick_step_offers_yes_this_is_a_fix_and_get_help(settings):
    view = searched(settings)

    labels = [label for _key, label in panel.enhance_buttons(view)]

    assert f"Yes, that's it: {LIMITS}" in labels
    assert "This is a fix" in labels and "Get help" in labels


def test_this_is_a_fix_marks_the_kind_and_the_button_goes_away(settings):
    view = searched(settings)

    _outputs, fixed = act(settings, view, choice(label_index(view, "This is a fix")))

    assert fixed.kind == "fix"
    assert "This is a fix" not in [label for _k, label in panel.enhance_buttons(fixed)]


def test_the_yes_button_confirms_the_target_and_then_the_browser_check_shows(settings):
    view = searched(settings)

    _outputs, done = act(settings, view, choice(label_index(view, f"Yes, that's it: {LIMITS}")))

    assert [t.path for t in done.targets] == [LIMITS]
    assert [key for key, _label in panel.browser_buttons(done)] == [panel.CHECK_KEY]
    assert "Check against main" in all_text(cb.show_page(f"?request={done.request_id}", 0))


def test_the_browser_may_read_only_the_confirmed_targets(settings):
    view = searched(settings)
    assert context_of(view)["planned_paths"] == []  # nothing is confirmed yet: nothing is read

    _outputs, done = act(settings, view, choice(label_index(view, f"Yes, that's it: {LIMITS}")))

    assert context_of(done)["planned_paths"] == [LIMITS]
    assert context_of(done)["enhance_revision"] == done.revision


def test_a_fresh_copy_moves_to_describe_the_change_and_then_to_the_understand_screen(settings):
    view = searched(settings)
    _outputs, done = act(settings, view, choice(label_index(view, f"Yes, that's it: {LIMITS}")))
    his = (settings.fake_main_dir / LIMITS).read_text(encoding="utf-8")

    ws_cb.handle_workspace_event(
        settings, facts_event(settings, "enhance_check", his), context_of(done), 0
    )
    fresh = enhance.get_enhance_view(settings, done.request_id)

    assert fresh.step == "e_fresh"
    assert [label for _k, label in panel.enhance_buttons(fresh)][0] == "Describe the change"
    _outputs, started = act(settings, fresh, choice(0))
    assert started.understand_started
    drawn = all_text(cb.show_page(f"?request={done.request_id}", 0))
    assert "Describe the change" not in drawn  # the Understand form has taken over


def test_a_different_copy_shows_the_stale_buttons(settings):
    view = searched(settings)
    _outputs, done = act(settings, view, choice(label_index(view, f"Yes, that's it: {LIMITS}")))

    ws_cb.handle_workspace_event(
        settings, facts_event(settings, "enhance_check", "x = 1\n"), context_of(done), 0
    )
    stale = enhance.get_enhance_view(settings, done.request_id)

    assert stale.step == "e_stale"
    labels = [label for _key, label in panel.browser_buttons(stale)]
    assert labels == ["I've updated, check again", "My local changes are intentional"]


def test_the_intentional_button_moves_on(settings):
    view = searched(settings)
    _outputs, done = act(settings, view, choice(label_index(view, f"Yes, that's it: {LIMITS}")))
    ws_cb.handle_workspace_event(
        settings, facts_event(settings, "enhance_check", "x = 1\n"), context_of(done), 0
    )
    stale = enhance.get_enhance_view(settings, done.request_id)

    ws_cb.handle_workspace_event(
        settings, facts_event(settings, "enhance_intentional", "x = 1\n"), context_of(stale), 0
    )

    assert enhance.get_enhance_view(settings, done.request_id).step == "e_fresh"


def test_a_closed_picker_changes_nothing(settings):
    view = searched(settings)

    with pytest.raises(PreventUpdate):
        ws_cb.handle_workspace_event(settings, {"kind": "enhance_cancelled"}, context_of(view), 0)

    assert enhance.get_enhance_view(settings, view.request_id).revision == view.revision


def test_an_old_window_is_refused_with_the_stale_message(settings):
    view = searched(settings)
    stale_state = {**state_of(view), "revision": view.revision - 1}

    outputs = cb.perform_action(settings, choice(0), "", stale_state, 0)

    assert "another window" in outputs[2]
    assert enhance.get_enhance_view(settings, view.request_id).revision == view.revision


def test_a_button_with_nothing_behind_it_is_refused(settings):
    view = searched(settings)

    outputs = cb.perform_action(settings, choice(99), "", state_of(view), 0)

    assert "another window" in outputs[2]


def test_get_help_escalates_from_the_pick_step(settings):
    view = searched(settings)

    _outputs, helped = act(settings, view, choice(label_index(view, "Get help")))

    assert helped.step == "escalated"
