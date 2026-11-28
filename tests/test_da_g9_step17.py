"""G9 step 17 (S5, S6): "Opening..." and the redraw follow the page that is showing."""

import pytest
from dash.exceptions import PreventUpdate

from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture(autouse=True)
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    return settings


@pytest.mark.parametrize("path", ["/admin", "/inbox", "/dev-assistant/capability-map"])
def test_g9_18_the_developer_page_ignores_address_changes_while_another_page_shows(path):
    with pytest.raises(PreventUpdate):
        cb.show_page("?tab=charter", 0, path)


def test_g9_17_the_developer_page_still_draws_on_its_own_path():
    assert cb.show_page("", 0, "/") is not None
    assert cb.show_page("", 0) is not None  # the old two-argument call


def test_g9_17_opening_is_shown_only_on_the_developer_page():
    js = cb.OPENING_JS
    assert "'Opening...'" in js and "no_update" in js
    for path in ("/admin", "/inbox", "/dev-assistant/capability-map"):
        assert path in js
