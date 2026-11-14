"""F10 (B1-11): Home always works. From a request that is still waiting on the AI, go Home and open
the same request again: the Home link, the title and the request ID must show, and Home must work.

Skipped, not failed, when Playwright or its browser is missing."""

import threading
import time

import pytest
from werkzeug.serving import make_server

from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from tests import da_play
from web import da_home_web_server as server_module

pytestmark = pytest.mark.usefixtures("published_rulebook")

SLOW_SECONDS = 4
PROCEED = "Proceed with this understanding"


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def slow_ai(monkeypatch):
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


def test_b1_11_home_and_the_same_request_again_while_the_ai_is_slow(
    make_live_page, live, slow_ai
):
    url, view = live
    page = make_live_page(url)
    proceed = page.get_by_role("button", name=PROCEED, exact=True)
    proceed.wait_for(timeout=15000)
    proceed.click()
    page.wait_for_timeout(500)  # the AI call is still running

    page.locator("#da-home-link").evaluate("el => el.click()")  # Home, while it waits
    page.get_by_text(view.request.request_id).first.wait_for(timeout=10000)
    page.locator(f"a[href='?request={view.request.request_id}']").first.click()  # open it again

    page.locator("#da-home-link").wait_for(timeout=10000)
    assert page.get_by_text(view.request.request_id).count() >= 1
    page.wait_for_timeout((SLOW_SECONDS + 1) * 1000)  # the first call ends after Home

    link = page.locator("#da-home-link")
    assert link.count() == 1  # the stale answer must not wipe the header
    assert page.locator("#da-page-content").evaluate(
        "el => getComputedStyle(el).pointerEvents"
    ) == "auto"
    link.click()
    page.wait_for_url(lambda u: "request=" not in u, timeout=10000)
