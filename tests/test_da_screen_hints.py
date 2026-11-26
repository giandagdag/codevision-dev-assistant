"""Fix G9 step 15: hint lines under Re-scan and Check my folder, the Missing backup chip at the
right end (S1, S3, G9-19, G9-20). The pixel positions are checked by the browser test."""

from agents.da_handoff_screen import CHECK_FOLDER_HINT, CHECK_FOLDER_KEY, HandoffBox
from agents.da_refine_flow import RESCAN_KEY
from agents.da_refine_screen import RESCAN_HINT
from layouts.da_admin_catalog_tab import MISSING_CHIP_LABEL, catalog_view
from layouts.da_developer_assistant_page import button_hints
from tests.da_tree import all_text, by_id


def _texts(blocks) -> list[str]:
    return [all_text(block) for block in blocks]


def test_the_hint_constants_say_what_the_spec_says():
    assert RESCAN_HINT == "Reads your own edits so the Tester checks them."
    assert CHECK_FOLDER_HINT == "Last step: confirms your folder still matches the tested version."


def test_g9_20_each_button_shows_its_hint_only_when_the_button_is_there():
    rescan = [(RESCAN_KEY, "Re-scan")]
    check = HandoffBox(offered=True, browser_buttons=[(CHECK_FOLDER_KEY, "Check my folder")])

    assert _texts(button_hints(rescan, None)) == [RESCAN_HINT]
    assert _texts(button_hints([], check)) == [CHECK_FOLDER_HINT]
    assert _texts(button_hints(rescan, check)) == [RESCAN_HINT, CHECK_FOLDER_HINT]
    assert button_hints([], HandoffBox()) == []


def test_g9_19_the_missing_backup_chip_is_labelled_and_sits_at_the_right_end(published_rulebook):
    chip = by_id(catalog_view(published_rulebook), "adm-cat-missing")

    assert chip.children == MISSING_CHIP_LABEL == "Show: Missing backup"
