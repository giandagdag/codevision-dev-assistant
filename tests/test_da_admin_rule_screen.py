"""Phase 11b step 4: the UI standards and Coding standards screens (plain functions, no browser)."""

from agents.da_admin_forms import RESULT_SAVED, save_from_form
from callbacks.screen_callbacks.da_admin_page_callbacks import (
    form_from_cells,
    run_action,
    tabs_disabled,
)
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_rulebook import get_active_version
from layouts.da_admin_page import (
    RULE_COLUMNS,
    TAB_CODING,
    TAB_UI,
    admin_page,
    tab_content,
)
from pydantic_classes.da_rulebook_models import MAX_JUDGEMENT_RULES
from tests.test_da_admin_page import RETIRED, all_text, walk

ADMIN = "admin-0001"


def settings_for(make_settings):
    return make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)


def act(tab, action):
    return {"type": "adm-act", "tab": tab, "action": action}


def add_action(tab):
    return {"type": "adm-add", "tab": tab, "table": "rules", "index": 0}


def cells_of(content):
    """The adm-cell components of a drawn tab, as Dash would give them back (id and value)."""
    found = []
    for item in walk(content):
        ident = getattr(item, "id", None)
        if isinstance(ident, dict) and ident.get("type") == "adm-cell":
            found.append({"id": ident, "value": getattr(item, "value", None)})
    return found


def fields_of(content):
    found = []
    for item in walk(content):
        ident = getattr(item, "id", None)
        if isinstance(ident, dict) and ident.get("type") == "adm-field":
            found.append({"id": ident, "value": getattr(item, "value", None)})
    return found


def sample_rows(content):
    """The Sonar sample table rows as lists of cell text: key, name, sonar severity, mapped."""
    rows = []
    for item in walk(content):
        if type(item).__name__ == "TableTr":
            texts = [str(getattr(cell.children, "children", "")) for cell in item.children]
            if len(texts) == 4 and texts[0].startswith("py:"):
                rows.append(texts)
    return rows


def rule_ids(rows):
    return [row["rule_id"] for row in rows]


def test_both_tabs_build_from_the_seed_and_show_the_header_line(published_rulebook):
    for tab in (TAB_UI, TAB_CODING):
        text = all_text(tab_content(tab, published_rulebook))
        assert "Showing v1 (active)" in text  # 11-3
        assert "Edit" in text
        assert "Nothing here yet" not in text.split("Approved libraries")[0]


def test_the_console_draws_the_new_tabs_with_a_body(published_rulebook):
    page = admin_page(published_rulebook, cited={})
    ids = {str(getattr(c, "id", None)) for c in walk(page)}

    assert "adm-body-ui" in ids and "adm-body-coding" in ids


def test_the_counter_reads_n_of_10_for_judgement_rules(published_rulebook):
    count = sum(1 for r in published_rulebook.rulebook.rules if r.kind == "judgement")

    text = all_text(tab_content(TAB_CODING, published_rulebook))

    assert f"Judgement rules: {count} of {MAX_JUDGEMENT_RULES}" in text


def test_the_cited_column_shows_the_count_in_read_and_edit_view(published_rulebook):
    rule = next(r for r in published_rulebook.rulebook.rules if r.kind == "judgement")
    cited = {rule.rule_id: 7}

    read = tab_content(TAB_CODING, published_rulebook, cited=cited)
    edit = tab_content(TAB_CODING, published_rulebook, editable=True, cited=cited)

    assert "Cited" in all_text(read) and "7" in all_text(read)
    assert "7" in all_text(edit)
    # Cited is read only: it must not come back as a form cell.
    assert all(c["id"]["col"] != "cited" for c in cells_of(edit))


def test_the_sonar_banner_and_sample_list_are_shown(published_rulebook):
    text = all_text(tab_content(TAB_CODING, published_rulebook))

    assert "Sample list. The real list comes from SonarQube when access is decided (WF-4)." in text
    assert "py:S107" in text


def test_changing_the_map_changes_the_sample_list_to_fyi(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    form, _ = form_from_cells(
        TAB_CODING,
        cells_of(tab_content(TAB_CODING, published_rulebook, editable=True)),
        [
            {"id": {"type": "adm-field", "tab": TAB_CODING, "name": "sonar_MAJOR"}, "value": "fyi"},
        ],
        [],
    )

    assert form["sonar_map"] == {"MAJOR": "fyi"}
    # The draft map shows in the sample list, and saving it keeps it.
    draft_view = tab_content(TAB_CODING, published_rulebook, editable=True, draft=form)
    assert "MAJOR: fyi" not in all_text(draft_view)  # edit view uses dropdowns, not lines
    current_map = published_rulebook.rulebook.policy.sonar_severity_map
    full = {**form, "sonar_map": {**current_map, **form["sonar_map"]}}
    result = save_from_form(settings.db_path, TAB_CODING, full, 1, ADMIN, "MAJOR is for info")
    assert result.kind == RESULT_SAVED
    saved_view = tab_content(TAB_CODING, get_active_version(settings.db_path))
    assert "MAJOR: fyi" in all_text(saved_view)
    # 11-15: the sample rows of the MAJOR checks now show fyi (the draft view shows it too).
    for view in (saved_view, draft_view):
        major_rows = [
            cells
            for cells in sample_rows(view)
            if cells[2] == "MAJOR"
        ]
        assert major_rows and all(cells[3] == "fyi" for cells in major_rows)


def test_edit_greys_the_other_tabs_for_both_new_tabs(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    for tab in (TAB_UI, TAB_CODING):
        content, editing = run_action(settings, tab, act(tab, "edit"), {}, "", None)

        assert editing is True  # 11-4
        assert "Add row" in all_text(content)
        assert tabs_disabled(tab).count(False) == 1


def test_rule_ids_survive_the_round_trip_after_add_row_and_remove(
    make_settings, published_rulebook
):
    settings = settings_for(make_settings)
    content, _ = run_action(settings, TAB_UI, act(TAB_UI, "edit"), {}, "", 1)
    form, _ = form_from_cells(TAB_UI, cells_of(content), fields_of(content), [])
    before = rule_ids(form["rules"])
    assert before  # the seed has UI rules

    content, _ = run_action(settings, TAB_UI, add_action(TAB_UI), form, "", 1)
    form, _ = form_from_cells(TAB_UI, cells_of(content), fields_of(content), [])
    after_add = rule_ids(form["rules"])
    assert after_add[:-1] == before and after_add[-1] not in before and after_add[-1]

    remove = {"type": "adm-remove", "tab": TAB_UI, "table": "rules", "index": 0}
    content, _ = run_action(settings, TAB_UI, remove, form, "", 1)
    form, _ = form_from_cells(TAB_UI, cells_of(content), fields_of(content), [])
    assert rule_ids(form["rules"]) == after_add[1:]


def test_add_row_then_cancel_then_add_row_gives_the_following_number(
    make_settings, published_rulebook
):
    settings = settings_for(make_settings)

    first, _ = run_action(settings, TAB_UI, add_action(TAB_UI), {"rules": []}, "", 1)
    run_action(settings, TAB_UI, act(TAB_UI, "cancel"), {}, "", 1)
    second, _ = run_action(settings, TAB_UI, add_action(TAB_UI), {"rules": []}, "", 1)

    one = rule_ids(form_from_cells(TAB_UI, cells_of(first), [], [])[0]["rules"])
    two = rule_ids(form_from_cells(TAB_UI, cells_of(second), [], [])[0]["rules"])
    assert one != two


def test_add_row_at_the_cap_shows_the_message_and_adds_nothing(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    rows = [{col: "x" for col in RULE_COLUMNS} | {"rule_id": f"CV-PY-9{i:02d}"} for i in range(10)]

    content, editing = run_action(
        settings, TAB_CODING, add_action(TAB_CODING), {"rules": rows}, "", 1
    )

    assert editing is True
    text = all_text(content)
    assert "Remove one before adding another" in text
    assert "10 of 10" in text


def test_a_save_from_the_drawn_form_with_an_unchanged_rule_says_no_changes(
    make_settings, published_rulebook
):
    settings = settings_for(make_settings)
    content, _ = run_action(settings, TAB_CODING, act(TAB_CODING, "edit"), {}, "", 1)
    form, _ = form_from_cells(TAB_CODING, cells_of(content), fields_of(content), [])

    saved, editing = run_action(settings, TAB_CODING, act(TAB_CODING, "save"), form, "Same", 1)

    assert editing is True
    assert "No changes to save" in all_text(saved)


def test_cited_counts_reach_the_coding_tab_through_run_action(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    rule = next(r for r in published_rulebook.rulebook.rules if r.kind == "judgement")
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            "INSERT INTO da_tester_findings (request_id, build_number, review_number,"
            " finding_id, check_number, severity, file, line, quote, cites, message, made_by,"
            " kept, reject_reason, fixable, created_at)"
            " VALUES ('CVDA-2026-0001', 1, 1, 'F1', 1, 'fyi', 'a.py', 1, 'q', ?, 'm', 'tester',"
            " 1, '', 0, '2026-11-01T09:00:00+00:00')",
            (rule.rule_id,),
        )

    content, _ = run_action(settings, TAB_CODING, act(TAB_CODING, "cancel"), {}, "", 1)

    assert "Cited" in all_text(content)
    assert any(getattr(c, "children", None) == "1" for c in walk(content))


def test_no_retired_field_shows_on_the_new_tabs(published_rulebook):
    for tab in (TAB_UI, TAB_CODING):
        text = all_text(tab_content(tab, published_rulebook, editable=True)).lower()
        assert not any(word in text for word in RETIRED)
