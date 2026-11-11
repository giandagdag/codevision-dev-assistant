"""Phase 9 step 18c: the s_* steps and the checkpoint are drawn by the page (code review round 1,
Must fix 3). Click-through tests: they call show_page and the page callbacks, not the engine.
Made-up data, no real AI."""

import pytest

from agents import da_enhance_flow as enhance
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from tests.test_da_enhance_discover import confirmed_enhance
from tests.test_da_enhance_understand import fresh, to_checkpoint  # noqa: F401  (fixture by name)
from tests.test_da_safety_net_flow import Runner, at_s_writing, state_of

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def draw(settings, monkeypatch, request_id):
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return repr(cb.show_page(f"?request={request_id}", 0))


def run_net(settings, request_id, tmp_path):
    from agents import da_safety_net_flow as net_flow

    net_flow.run_safety_net(
        settings, request_id, state_of(settings, request_id).revision, Runner(tmp_path)
    )


def test_the_checkpoint_shows_the_tick_list_and_save_calls_the_engine(
    settings, fresh, monkeypatch  # noqa: F811
):
    enhance.start_understand(settings, fresh.request_id, fresh.revision)
    checkpoint = to_checkpoint(settings, fresh.request_id)

    page = draw(settings, monkeypatch, fresh.request_id)
    assert "da-scope-group" in page and "format_expiry" in page
    assert "Save functions in scope" in page

    state = {"request_id": fresh.request_id, "revision": checkpoint.revision}
    refresh, message = cb.perform_scope_save(settings, ["format_expiry"], state, 0)
    assert (refresh, message) == (1, "")

    refresh, message = cb.perform_scope_save(settings, [], state, 1)  # now a stale window
    assert refresh is cb.no_update and message


def test_a_refused_scope_shows_its_message(settings, fresh):  # noqa: F811
    enhance.start_understand(settings, fresh.request_id, fresh.revision)
    checkpoint = to_checkpoint(settings, fresh.request_id)
    state = {"request_id": fresh.request_id, "revision": checkpoint.revision}

    refresh, message = cb.perform_scope_save(settings, [], state, 0)

    assert refresh is cb.no_update and "Tick at least one" in message


def test_discover_shows_the_impact_card_for_an_enhance_request(settings, monkeypatch):
    from agents import da_discover_flow as discover

    request_id = confirmed_enhance(settings)
    discover.start_discovery(settings, request_id, 0)

    page = draw(settings, monkeypatch, request_id)

    assert "Impact" in page


def test_the_review_step_draws_the_net_tab_the_pill_and_its_own_buttons(
    settings, monkeypatch, tmp_path
):
    request_id = at_s_writing(settings)
    run_net(settings, request_id, tmp_path)

    page = draw(settings, monkeypatch, request_id)

    assert "SAFETY NET READY" in page
    assert "Safety net" in page and "Today's behaviour" in page
    assert "Continue to Approach" in page and "Correct something" in page
    assert "da-net-mark" in page  # the marks can be changed while in review
    assert "'enhance': 's_review'" in page  # the buttons reach the Enhance engine


def test_the_writing_step_polls_and_shows_the_writing_pill(settings, monkeypatch):
    request_id = at_s_writing(settings)

    page = draw(settings, monkeypatch, request_id)

    assert "WRITING SAFETY NET" in page and "Interval" in page
    state = {"request_id": request_id, "revision": 1, "enhance": "s_writing"}
    assert cb.poll_build(1, state, 0) == 1


def test_after_accepting_the_test_plan_shows_the_net_read_only(settings, monkeypatch, tmp_path):
    from agents import da_safety_net_flow as net_flow

    request_id = at_s_writing(settings)
    run_net(settings, request_id, tmp_path)
    net_flow.accept_safety_net(settings, request_id, state_of(settings, request_id).revision)

    page = draw(settings, monkeypatch, request_id)

    assert "Safety net" in page and "da-net-mark" not in page
