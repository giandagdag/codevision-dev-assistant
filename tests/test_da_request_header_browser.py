"""Fix G5 N6 (G5-14): the request page always shows Home, the title and the request ID, never the
Home subtitle. One test per entry path, on a request waiting on a decision (choice buttons).

Skipped, not failed, when Playwright or its browser is missing."""

import threading

import pytest
from werkzeug.serving import make_server

from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from tests import da_play
from web import da_home_web_server as server_module

pytestmark = pytest.mark.usefixtures("published_rulebook")

HOME_SUBTITLE = "Start a new change, or get your own code reviewed."


@pytest.fixture
def live(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    view = da_play.to_decision(settings)
    app = server_module.create_app()
    server = make_server("127.0.0.1", 0, app.server, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/", view
    server.shutdown()


def _check_header(page, view):
    page.locator("#da-home-link").wait_for(timeout=15000)
    page.get_by_text(view.request.request_id).first.wait_for(timeout=5000)
    page.wait_for_timeout(1500)  # a late redraw would show up by now
    assert page.locator("#da-home-link").count() == 1
    assert page.get_by_text(view.request.title).count() >= 1
    assert page.get_by_text(HOME_SUBTITLE).count() == 0
    assert view.choices and page.get_by_role("button", name=view.choices[0]).count() >= 1


def test_direct_address(make_live_page, live):
    base, view = live
    page = make_live_page(f"{base}?request={view.request.request_id}")
    _check_header(page, view)


def test_from_the_home_list(make_live_page, live):
    base, view = live
    page = make_live_page(base)
    page.locator(f"a[href='?request={view.request.request_id}']").first.click()
    _check_header(page, view)


def test_home_then_reopen(make_live_page, live):
    base, view = live
    page = make_live_page(f"{base}?request={view.request.request_id}")
    _check_header(page, view)
    page.locator("#da-home-link").click()
    page.locator(f"a[href='?request={view.request.request_id}']").first.click()
    _check_header(page, view)


def test_slow_server_does_not_leave_home_on_screen(make_live_page, live, monkeypatch):
    """A slow load of the request page (work server) must not keep the Home subtitle showing."""
    import time

    base, view = live
    original = cb.show_page

    def slow(search, refresh):
        if search and "request=" in search:
            time.sleep(3)
        return original(search, refresh)

    monkeypatch.setattr(cb, "show_page", slow)
    app = server_module.create_app()
    server = make_server("127.0.0.1", 0, app.server, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        page = make_live_page(f"http://127.0.0.1:{server.server_port}/")
        page.locator(f"a[href='?request={view.request.request_id}']").first.click()
        page.wait_for_timeout(1000)  # the request page has not arrived yet
        assert page.get_by_text(HOME_SUBTITLE).count() == 0
        _check_header(page, view)
    finally:
        server.shutdown()


def test_reload(make_live_page, live):
    base, view = live
    page = make_live_page(f"{base}?request={view.request.request_id}")
    _check_header(page, view)
    page.reload()
    _check_header(page, view)
