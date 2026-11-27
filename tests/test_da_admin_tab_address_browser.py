"""Fix G5 N5 (G5-13): the admin tab is in the address. /admin opens Overview and nothing changes the
tab on load. Skipped, not failed, when Playwright or its browser is missing."""

import threading

import pytest
from werkzeug.serving import make_server

from callbacks.screen_callbacks import da_admin_page_callbacks as admin_cb
from layouts.da_admin_page import ADMIN_PATH
from web import da_home_web_server as server_module

pytestmark = pytest.mark.usefixtures("published_rulebook")

ADMIN = "admin-0001"


@pytest.fixture
def base(make_settings, monkeypatch):
    settings = make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)
    monkeypatch.setattr(admin_cb, "get_admin_settings", lambda: settings)
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    server = make_server("127.0.0.1", 0, server_module.create_app().server, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}{ADMIN_PATH}"
    server.shutdown()


def selected(page) -> str:
    return page.locator("[role=tab][aria-selected=true]").first.inner_text()


def test_plain_admin_opens_overview_and_stays(make_live_page, base):
    page = make_live_page(base)
    page.get_by_role("tab", name="Overview", exact=True).wait_for(timeout=15000)
    page.wait_for_timeout(4000)  # a late callback would have moved the tab by now
    assert selected(page) == "Overview"
    assert page.url.rstrip("/").endswith("/admin") or "tab=overview" in page.url


def test_click_updates_the_address_and_reload_keeps_it(make_live_page, base):
    page = make_live_page(base)
    page.get_by_role("tab", name="Project charter", exact=True).click()
    page.wait_for_url("**tab=charter**", timeout=5000)
    page.reload()
    page.get_by_role("tab", name="Project charter", exact=True).wait_for(timeout=15000)
    page.wait_for_timeout(1500)
    assert selected(page) == "Project charter"


def test_g9_18_admin_tab_clicks_never_show_the_developer_assistant_page(make_live_page, base):
    page = make_live_page(base)
    for name in ("Project charter", "Build and test", "Overview"):
        page.get_by_role("tab", name=name, exact=True).click()
        page.wait_for_timeout(700)
        assert not page.locator("#da-page-content").is_visible()
        assert "Opening..." not in page.locator("body").inner_text()
    page.reload()
    page.get_by_role("tab", name="Overview", exact=True).wait_for(timeout=15000)
    page.wait_for_timeout(1500)
    assert selected(page) == "Overview"  # F5 keeps the tab
    assert not page.locator("#da-page-content").is_visible()


def test_g9_17_admin_then_developer_assistant_then_start_shows_understand_not_opening(
    make_live_page, base
):
    page = make_live_page(base)
    page.get_by_role("tab", name="Project charter", exact=True).click()
    page.wait_for_url("**tab=charter**", timeout=5000)
    page.locator("#da-dev-menu").click()  # Admin -> Developer Assistant
    page.locator("#da-start-card").wait_for(timeout=10000)  # Home shows, not a stuck "Opening..."
    page.locator("#da-start-card").click()
    page.locator("#da-text").wait_for(timeout=10000)  # the Understand page
    page.wait_for_timeout(5000)
    assert page.locator("#da-text").is_visible()
    assert "Opening..." not in page.locator("#da-page-content").inner_text()


def test_g9_17_admin_to_home_through_the_menu_always_redraws(make_live_page, base):
    page = make_live_page(base)
    page.get_by_role("tab", name="Overview", exact=True).wait_for(timeout=15000)
    page.locator("#da-dev-menu").click()
    page.locator("#da-start-card").wait_for(timeout=10000)
    page.locator("#da-admin-menu").click()
    page.get_by_role("tab", name="Overview", exact=True).wait_for(timeout=10000)
    page.locator("#da-dev-menu").click()
    page.locator("#da-start-card").wait_for(timeout=10000)  # back again: redrawn, not stale


def test_shared_link_and_back(make_live_page, base):
    page = make_live_page(f"{base}?tab=repository")
    page.get_by_role("tab", name="Repository and index", exact=True).wait_for(timeout=15000)
    page.wait_for_timeout(1500)
    assert selected(page) == "Repository and index"
    page.get_by_role("tab", name="Build and test", exact=True).click()
    page.wait_for_url("**tab=build**", timeout=5000)
    page.go_back()
    page.wait_for_url("**tab=repository**", timeout=5000)
    page.wait_for_timeout(1000)
    assert selected(page) == "Repository and index"


def test_catalog_view_in_the_address(make_live_page, base):
    page = make_live_page(f"{base}?tab=catalog&view=queue")
    page.get_by_role("tab", name="Capability catalog").wait_for(timeout=15000)
    page.wait_for_timeout(1500)
    assert selected(page).startswith("Capability")
    assert page.locator("#adm-cat-view input:checked").evaluate("e => e.value") == "queue"
