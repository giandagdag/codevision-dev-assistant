"""Phase 11c step 5: the Repository and index screen (11-3, 11-4, 11-26, edit and save)."""

from callbacks.screen_callbacks.da_admin_page_callbacks import (
    admin_content,
    form_from_cells,
    run_action,
    tabs_disabled,
)
from db_table_functions.db_tbl_da_rulebook import get_active_version, list_versions
from layouts.da_admin_page import ADMIN_PATH, ADMIN_TABS, TAB_REPO
from tests.test_da_admin_page import RETIRED, all_text, walk

ADMIN = "admin-0001"


def act(action):
    return {"type": "adm-act", "tab": TAB_REPO, "action": action}


def admin_settings(make_settings):
    return make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)


def cells_of(content):
    return [
        {"id": c.id, "value": c.value}
        for c in walk(content)
        if isinstance(getattr(c, "id", None), dict) and c.id.get("type") == "adm-cell"
    ]


def fields_of(content):
    return [
        {"id": c.id, "value": c.value}
        for c in walk(content)
        if isinstance(getattr(c, "id", None), dict) and c.id.get("type") == "adm-field"
    ]


def test_read_view_shows_server_settings_and_the_four_fields(make_settings, published_rulebook):
    text = all_text(run_action_view(make_settings))

    for word in (
        "Code search source",  # plain label for DA_SEARCH_PROVIDER (fix 11-1, AF-2)
        "Sandbox copy of CodeVision: not set",
        "Allowed folders",
        "Workspace markers",
        "New file name pattern",
        "Largest file the scan reads (KB)",
    ):
        assert word in text
    assert "Active rulebook v1" in text  # 11-3


def run_action_view(make_settings):
    content, editing = run_action(admin_settings(make_settings), TAB_REPO, act("cancel"), {}, "", 1)
    assert editing is False
    return content


def test_no_retired_field_is_shown_on_this_tab(make_settings, published_rulebook):
    text = all_text(run_action_view(make_settings)).lower()

    for word in RETIRED:
        assert word not in text  # 11-26


def test_edit_save_makes_a_new_version_and_greys_the_other_tabs(make_settings, published_rulebook):
    settings = admin_settings(make_settings)
    content, editing = run_action(settings, TAB_REPO, act("edit"), {}, "", None)

    assert editing is True
    assert tabs_disabled(TAB_REPO).count(False) == 1  # 11-4
    greyed = tabs_disabled(TAB_REPO)
    open_tabs = [name for (name, _, _), off in zip(ADMIN_TABS, greyed, strict=True) if not off]
    assert open_tabs == [TAB_REPO]
    fields = [
        f if f["id"]["name"] != "workspace_max_file_kb" else {**f, "value": "256"}
        for f in fields_of(content)
    ]
    fields = [f for f in fields if f["id"]["name"] != "note"]
    fields.append({"id": {"type": "adm-field", "tab": TAB_REPO, "name": "note"}, "value": "Bigger"})
    form, note = form_from_cells(TAB_REPO, cells_of(content), fields, [])

    saved, editing = run_action(settings, TAB_REPO, act("save"), form, note, 1)

    assert editing is False
    assert "Saved as v2" in all_text(saved)
    assert get_active_version(settings.db_path).rulebook.policy.workspace_max_file_kb == 256
    assert len(list_versions(settings.db_path)) == 2


def test_no_tab_says_comes_in_any_more(make_settings, published_rulebook):
    text = all_text(admin_content(admin_settings(make_settings), ADMIN_PATH))

    assert "Comes in" not in text
