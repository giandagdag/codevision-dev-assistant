"""Fix 11-1, AF-3: the version pill with View history, and the shared edit bar."""

import pytest

from callbacks.screen_callbacks.da_admin_page_callbacks import run_action
from layouts.da_admin_page import EDITABLE_TABS, TAB_HISTORY, version_line
from tests.test_da_admin_page import all_text, walk

ADMIN = "admin-0001"


def test_the_pill_shows_version_date_who_and_a_view_history_link(published_rulebook):
    version = published_rulebook

    pill = version_line(version)
    text = all_text(pill)

    assert f"v{version.version_number}" in text
    assert version.saved_at.strftime("%Y-%m-%d %H:%M") in text
    assert f"saved by {version.saved_by}" in text
    links = [c for c in walk(pill) if getattr(c, "children", None) == "View history"]
    assert len(links) == 1 and links[0].id["tab"] == TAB_HISTORY


@pytest.mark.parametrize("tab", EDITABLE_TABS)
def test_every_edit_view_has_the_floating_bar(tab, make_settings, published_rulebook):
    settings = make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)
    act = {"type": "adm-act", "tab": tab, "action": "edit"}

    content, _ = run_action(settings, tab, act, {}, "", None)
    text = all_text(content)

    assert "Nothing changes for developers until you save." in text
    assert "Save as new version" in text and "Cancel" in text
