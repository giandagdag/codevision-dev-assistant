"""A second click while an action is still running must do nothing (found at work: "This request
was updated in another window. Reload to continue." with only one window open).

The cause: the choice buttons stayed clickable for the 10 to 20 seconds the AI needs. A second
click carried the revision from before the first one finished, and the server rightly refused it.
Now the page takes no clicks while an action runs.

Skipped, not failed, when Playwright or its browser is missing."""

import threading
import time

import pytest
from werkzeug.serving import make_server

from agents import da_understand_flow as flow
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from tests import da_play
from web import da_home_web_server as server_module

pytestmark = pytest.mark.usefixtures("published_rulebook")

SLOW_SECONDS = 3
PROCEED = "Proceed with this understanding"


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def slow_ai(monkeypatch):
    """Discover takes a few seconds, like Qwen at work (the fake AI answers in milliseconds)."""
    original = cb.start_discovery

    def slow(*args, **kwargs):
        time.sleep(SLOW_SECONDS)
        return original(*args, **kwargs)

    monkeypatch.setattr(cb, "start_discovery", slow)


@pytest.fixture
def live(settings):
    view = da_play.to_checkpoint(settings)
    app = server_module.create_app()
    server = make_server("127.0.0.1", 0, app.server, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/?request={view.request.request_id}", view
    server.shutdown()


def message(page) -> str:
    return page.locator("#da-message").inner_text()


def real_click(page, locator) -> None:
    """A click with the mouse at the button's place, like a person. (A script click would skip
    the pointer-events rule that this test is about.)"""
    box = locator.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def test_a_second_click_while_the_first_still_runs_does_nothing(
    make_live_page, live, settings, slow_ai
):
    url, view = live
    page = make_live_page(url)
    proceed = page.get_by_role("button", name=PROCEED, exact=True)
    proceed.wait_for(timeout=15000)
    box = proceed.bounding_box()

    real_click(page, proceed)
    page.wait_for_timeout(700)  # the first action is still running (Discover is slow now)
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)  # impatient click
    page.get_by_role("button").filter(has_text="Findings look right").wait_for(timeout=20000)

    assert message(page) == ""  # no "updated in another window"
    found = flow.get_understand_view(settings, view.request.request_id)
    assert found.request.status == "SIMILAR_IMPLEMENTATION_FOUND"


def test_the_page_takes_clicks_again_when_the_action_has_finished(
    make_live_page, live, settings, slow_ai
):
    url, _ = live
    page = make_live_page(url)
    proceed = page.get_by_role("button", name=PROCEED, exact=True)
    proceed.wait_for(timeout=15000)

    real_click(page, proceed)
    page.get_by_role("button").filter(has_text="Findings look right").wait_for(timeout=20000)
    page.wait_for_timeout(300)

    style = page.locator("#da-page-content").evaluate(
        "el => ({pe: getComputedStyle(el).pointerEvents, op: getComputedStyle(el).opacity})"
    )
    assert style == {"pe": "auto", "op": "1"}
    real_click(page, page.get_by_role("button").filter(has_text="Findings look right"))
    # The approach starts by itself and first asks its design choice.
    page.get_by_role("button", name="I need help deciding", exact=True).wait_for(timeout=30000)
    assert message(page) == ""
