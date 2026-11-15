"""Edit, Save and Cancel on the Admin screen (plain functions, no browser)."""

from callbacks.screen_callbacks.da_admin_page_callbacks import (
    form_from_cells,
    run_action,
    tabs_disabled,
)
from db_table_functions.db_tbl_da_rulebook import get_active_version, list_versions
from layouts.da_admin_page import ADMIN_TABS
from tests.test_da_admin_page import all_text, walk

ADMIN = "admin-0001"


def act(action):
    return {"type": "adm-act", "tab": "build", "action": action}


def settings_for(make_settings):
    return make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)


def field(tab, name, value):
    return {"id": {"type": "adm-field", "tab": tab, "name": name}, "value": value}


def cell(table, row, col, value):
    return {"id": {"table": table, "row": row, "col": col}, "value": value}


def test_edit_shows_inputs_and_the_other_tabs_are_greyed(make_settings, published_rulebook):
    content, editing = run_action(settings_for(make_settings), "build", act("edit"), {}, "", None)

    assert editing is True
    text = all_text(content)
    assert "Save" in text and "Cancel" in text and "Add row" in text
    assert "Change note (required)" in text
    greyed = tabs_disabled("build")
    assert greyed.count(False) == 1
    open_tabs = [name for (name, _, _), off in zip(ADMIN_TABS, greyed, strict=True) if not off]
    assert open_tabs == ["build"]
    assert tabs_disabled(None) == [False] * 8


def test_cancel_writes_nothing_and_goes_back_to_the_view(make_settings, published_rulebook):
    settings = settings_for(make_settings)

    form = {"build_max_rounds": "5"}

    content, editing = run_action(settings, "build", act("cancel"), form, "", 1)

    assert editing is False
    assert "Edit" in all_text(content)
    assert len(list_versions(settings.db_path)) == 1


def test_save_with_a_note_shows_the_green_line_and_the_new_version(
    make_settings, published_rulebook
):
    settings = settings_for(make_settings)
    form, note = form_from_cells(
        "build",
        [],
        [field("build", "build_max_rounds", "4"), field("build", "note", "More rounds")],
        [],
    )

    content, editing = run_action(settings, "build", act("save"), form, note, 1)

    assert editing is False
    assert "Saved as v2" in all_text(content)
    assert "requests in progress keep their version" in all_text(content)
    assert get_active_version(settings.db_path).rulebook.policy.build_max_rounds == 4


def test_save_without_a_note_stays_in_edit_and_says_why(make_settings, published_rulebook):
    settings = settings_for(make_settings)

    content, editing = run_action(
        settings, "build", act("save"), {"build_max_rounds": "4"}, "", 1
    )

    assert editing is True
    assert "change note is empty" in all_text(content)
    assert len(list_versions(settings.db_path)) == 1


def test_bad_values_list_every_problem_and_keep_what_was_typed(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    form = {"build_max_rounds": "9", "max_files": "many"}

    content, editing = run_action(settings, "build", act("save"), form, "Try", 1)

    text = all_text(content)
    assert editing is True
    assert "build_max_rounds" in text and "max_files" in text
    assert "9" in text  # the typed value is still in the form


def test_no_change_says_no_changes(make_settings, published_rulebook):
    content, editing = run_action(
        settings_for(make_settings), "build", act("save"), {"build_max_rounds": "3"}, "Same", 1
    )

    assert editing is True
    assert "No changes to save" in all_text(content)


def test_a_stale_save_offers_reload_with_the_newer_version(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    run_action(settings, "build", act("save"), {"build_max_rounds": "4"}, "First", 1)

    content, editing = run_action(
        settings, "build", act("save"), {"build_max_rounds": "2"}, "Late", 1
    )

    text = all_text(content)
    assert editing is True
    assert "Reload v2" in text
    # The form still shows v1, which is no longer the active version.
    assert "Showing v1 (the version you started from)" in text

    reloaded, editing = run_action(settings, "build", act("reload"), {}, "", 1)
    assert editing is False
    assert "Showing v2" in all_text(reloaded)


def test_add_row_and_remove_keep_the_typed_form(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    form = {"protected_files": ["a/*", "b/*"], "build_max_rounds": "4"}
    add = {"type": "adm-add", "tab": "build", "table": "protected_files", "index": 0}
    remove = {"type": "adm-remove", "tab": "build", "table": "protected_files", "index": 0}

    added, editing = run_action(settings, "build", add, form, "", 1)
    removed, _ = run_action(settings, "build", remove, form, "", 1)

    assert editing is True
    cells = [c for c in walk(added) if type(c).__name__ == "Textarea"]
    removed_cells = [c for c in walk(removed) if type(c).__name__ == "Textarea"]
    assert [c.value for c in cells][-3:] == ["a/*", "b/*", ""]
    assert [c.value for c in removed_cells][-1:] == ["b/*"]
    # Step 13: number fields are steppers (NumberInput) holding the number.
    assert any(c.value == 4 for c in walk(added) if type(c).__name__ == "NumberInput")


def test_form_is_read_back_with_empty_tables_and_switches():
    cells = [cell("protected_files", 1, "text", "b"), cell("protected_files", 0, "text", "a")]
    switches = [
        {"id": {"name": "dispute"}, "value": True},
        {"id": {"name": "get_help"}, "value": False},
    ]

    form, note = form_from_cells("build", cells, [field("build", "note", " why ")], switches)

    assert form["protected_files"] == ["a", "b"]
    assert form["zones"] == []  # an emptied table is still in the form, so it clears
    assert form["triggers"] == {"dispute": True, "get_help": False}
    assert note == " why "


def test_charter_edit_and_save_through_the_screen_functions(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    cells = [cell("glossary", 0, "term", "Batch"), cell("glossary", 0, "meaning", "Jobs")]
    form, note = form_from_cells(
        "charter",
        cells,
        [field("charter", "purpose", "New purpose."), field("charter", "note", "Charter edit")],
        [],
    )
    action = {"type": "adm-act", "tab": "charter", "action": "save"}

    content, editing = run_action(settings, "charter", action, form, note, 1)

    assert editing is False and "Saved as v2" in all_text(content)
    charter = get_active_version(settings.db_path).rulebook.charter
    assert charter.purpose == "New purpose."
    assert [g.term for g in charter.glossary] == ["Batch"]
    assert charter.in_scope == []  # no cells were sent for it, so the list is cleared
