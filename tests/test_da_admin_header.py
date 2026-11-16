"""Fix 11-1, AF-3: the version pill with View history, and the shared edit bar."""

from datetime import datetime

import pytest

from callbacks.screen_callbacks.da_admin_page_callbacks import admin_content, run_action
from layouts.da_admin_common import version_pill
from layouts.da_admin_page import ADMIN_PATH, EDITABLE_TABS, TAB_HISTORY, version_line
from tests.test_da_admin_page import all_text, walk

ADMIN = "admin-0001"


def test_the_pill_shows_version_date_who_and_a_view_history_link(published_rulebook):
    version = published_rulebook

    pill = version_line(version)
    text = all_text(pill)

    assert f"Active rulebook v{version.version_number}" in text
    assert f"Published {version.saved_at:%Y-%m-%d %H:%M}, {version.saved_by}" in text
    links = [c for c in walk(pill) if getattr(c, "children", None) == "View history"]
    assert len(links) == 1 and links[0].id["tab"] == TAB_HISTORY


def test_all_eight_tabs_draw_the_pill_and_it_stays_off_the_old_line(
    make_settings, published_rulebook
):
    settings = make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)
    page = admin_content(settings, ADMIN_PATH)

    panels = [c for c in walk(page) if type(c).__name__ == "TabsPanel"]
    assert len(panels) == 8
    for panel in panels:
        text = all_text(panel)
        assert "Active rulebook v1" in text, panel.value
        assert "View history" in text, panel.value
        assert "Showing v" not in text


def test_a_stale_form_says_started_from_with_no_active_word():
    class Old:
        version_number, saved_by = 1, "admin-0001"
        saved_at = datetime(2026, 11, 1, 9, 30)

    text = all_text(version_pill(Old(), active=False))

    assert "Started from v1" in text and "Active" not in text


@pytest.mark.parametrize("tab", EDITABLE_TABS)
def test_every_edit_view_has_the_floating_bar(tab, make_settings, published_rulebook):
    settings = make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)
    act = {"type": "adm-act", "tab": tab, "action": "edit"}

    content, _ = run_action(settings, tab, act, {}, "", None)
    text = all_text(content)

    assert "Nothing changes for developers until you save." in text
    assert "Save as new version" in text and "Cancel" in text
