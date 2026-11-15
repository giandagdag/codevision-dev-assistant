"""Version history on the Admin screen (plain functions, no browser): tests 11-33 and 11-37."""

from callbacks.screen_callbacks.da_admin_page_callbacks import run_history_action
from db_table_functions.db_tbl_da_requests import create_request
from db_table_functions.db_tbl_da_rulebook import get_active_version, save_new_version
from tests.test_da_admin_page import all_text

ADMIN = "admin-0001"


def settings_for(make_settings):
    return make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)


def click(action, version=0):
    return {"type": "adm-hist", "action": action, "version": version}


def with_rounds(rulebook, value):
    policy = rulebook.policy.model_copy(update={"build_max_rounds": value})
    return rulebook.model_copy(update={"policy": policy})


def make_three_versions(settings, seed_rulebook):
    first = create_request(settings.db_path, "First pinned", "dev-0001")
    second = create_request(settings.db_path, "Second pinned", "dev-0002")
    save_new_version(settings.db_path, with_rounds(seed_rulebook, 4), 1, ADMIN, "Rounds four")
    save_new_version(settings.db_path, with_rounds(seed_rulebook, 5), 2, ADMIN, "Rounds five")
    return first, second


def test_timeline_is_newest_first_with_pins_and_the_active_mark(
    make_settings, seed_rulebook, published_rulebook
):
    settings = settings_for(make_settings)
    first, second = make_three_versions(settings, seed_rulebook)

    text = all_text(run_history_action(settings, click("cancel"), None, None, None))

    assert text.index("v3 ") < text.index("v2 ") < text.index("v1 ")
    assert text.count("(active)") == 1
    assert "2 requests pinned" in text
    assert first.request_id in text and second.request_id in text
    assert text.count("Restore") >= 2  # a button on each non-active version


def test_side_panel_shows_plain_diff_pinned_requests_and_restore(
    make_settings, seed_rulebook, published_rulebook
):
    settings = settings_for(make_settings)
    make_three_versions(settings, seed_rulebook)

    content = run_history_action(settings, click("view", 2), None, None, None)

    text = all_text(content)
    assert "What changed in v2" in text
    assert "+ Max fix rounds: 4" in text and "− Max fix rounds: 3" in text
    assert "build_max_rounds" not in text.split("What changed in v2")[1].split("Requests")[0]
    assert "Requests pinned" in text
    assert "Restore v2" in text


def test_restore_dialog_says_what_happens_to_versions(
    make_settings, seed_rulebook, published_rulebook
):
    settings = settings_for(make_settings)
    make_three_versions(settings, seed_rulebook)

    text = all_text(run_history_action(settings, click("restore", 1), None, None, None))

    assert "v4 becomes active for new requests. Requests in progress keep their version." in text
    assert "v3 stays in history." in text


def test_compare_lists_the_changed_path(make_settings, seed_rulebook, published_rulebook):
    settings = settings_for(make_settings)
    make_three_versions(settings, seed_rulebook)

    content = run_history_action(settings, click("compare"), "1", "2", None)

    text = all_text(content)
    assert "What changed v1 to v2" in text
    assert "Max fix rounds" in text
    assert "build_max_rounds" not in text  # AF-2: plain words only


def test_restore_asks_first_with_the_note_filled_in_and_writes_nothing(
    make_settings, seed_rulebook, published_rulebook
):
    settings = settings_for(make_settings)
    make_three_versions(settings, seed_rulebook)

    text = all_text(run_history_action(settings, click("restore", 1), None, None, None))

    assert "Restore v1 as a new version?" in text
    assert "Restored from v1" in text
    assert get_active_version(settings.db_path).version_number == 3


def test_confirmed_restore_of_v1_makes_v4(make_settings, seed_rulebook, published_rulebook):
    settings = settings_for(make_settings)
    make_three_versions(settings, seed_rulebook)

    content = run_history_action(settings, click("confirm", 1), None, None, "Restored from v1")

    active = get_active_version(settings.db_path)
    assert active.version_number == 4
    assert active.restored_from == 1
    text = all_text(content)
    assert "Saved as v4" in text
    assert "Restored from v1" in text


def test_restoring_the_active_version_shows_the_phase_1_refusal(
    make_settings, seed_rulebook, published_rulebook
):
    settings = settings_for(make_settings)
    make_three_versions(settings, seed_rulebook)

    content = run_history_action(settings, click("confirm", 3), None, None, "Restored from v3")

    assert "already the active version" in all_text(content)
    assert get_active_version(settings.db_path).version_number == 3
