"""Fix 11-1, AF-3 (changed 18 Nov): version once in the header, quiet Edit link, edit bar."""

from datetime import datetime

import pytest

from callbacks.screen_callbacks.da_admin_page_callbacks import admin_content, run_action
from layouts.da_admin_common import header_version, version_pill
from layouts.da_admin_page import ADMIN_PATH, EDITABLE_TABS, admin_page
from tests.test_da_admin_page import all_text, walk

ADMIN = "admin-0001"


def test_the_header_shows_version_date_who_and_no_history_button(published_rulebook):
    version = published_rulebook

    text = all_text(admin_page(version))
    header = all_text(header_version(version))

    assert f"Active rulebook v{version.version_number}" in header
    assert f"Published {version.saved_at:%Y-%m-%d %H:%M}, {version.saved_by}" in header
    assert "View history" not in text  # the Version history tab is right there
    assert text.count("Active rulebook") == 1  # once, in the header, not per tab


def test_no_tab_repeats_the_version(make_settings, published_rulebook):
    settings = make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)
    page = admin_content(settings, ADMIN_PATH)

    panels = [c for c in walk(page) if type(c).__name__ == "TabsPanel"]
    assert len(panels) == 8
    for panel in panels:
        assert "Active rulebook" not in all_text(panel), panel.value


def test_edit_is_a_quiet_text_link_with_a_pen(published_rulebook):
    buttons = [
        c
        for c in walk(admin_page(published_rulebook))
        if type(c).__name__ == "Button" and getattr(c, "children", None) == "Edit"
    ]

    assert buttons and all(b.variant == "subtle" for b in buttons)
    assert all(b.leftSection.icon == "tabler:pencil" for b in buttons)


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
