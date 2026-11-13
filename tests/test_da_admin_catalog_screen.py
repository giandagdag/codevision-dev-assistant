"""Phase 11b step 5: the Capability catalog tab and the Unassigned queue (no browser)."""

from datetime import UTC, datetime

from agents.da_admin_catalog import queue_rows, resolved_rows
from agents.da_admin_forms import capability_rows
from callbacks.screen_callbacks.da_admin_page_callbacks import (
    form_from_cells,
    queue_data,
    queue_inputs_from_states,
    run_action,
    run_queue_action,
    tabs_disabled,
)
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_enhance import add_unassigned
from db_table_functions.db_tbl_da_requests import create_request
from db_table_functions.db_tbl_da_rulebook import get_active_version, list_versions
from layouts.da_admin_page import (
    QUEUE_BUTTON_TYPE,
    TAB_CAPABILITY,
    queue_block,
    queue_button_id,
    tab_content,
)
from tests.test_da_admin_page import RETIRED, all_text, walk

ADMIN = "admin-0001"
TAB = TAB_CAPABILITY


def settings_for(make_settings):
    return make_settings(admin_ids=(ADMIN,), developer_id=ADMIN)


def add_row(db_path, path, picked="Limits"):
    request = create_request(db_path, f"Change for {path}", "dev-0001")
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        return add_unassigned(conn, path, picked, request.request_id, datetime.now(UTC))


def act(action):
    return {"type": "adm-act", "tab": TAB, "action": action}


def cells_of(content):
    found = []
    for item in walk(content):
        ident = getattr(item, "id", None)
        if isinstance(ident, dict) and ident.get("type") == "adm-cell":
            found.append({"id": ident, "value": getattr(item, "value", None)})
    return found


def q_buttons(content):
    return [
        item
        for item in walk(content)
        if isinstance(getattr(item, "id", None), dict)
        and item.id.get("type") == QUEUE_BUTTON_TYPE
    ]


def test_the_tab_builds_with_and_without_queue_rows(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    empty = tab_content(TAB, published_rulebook, queue=queue_data(settings))
    assert "No Unassigned files are waiting." in all_text(empty)
    assert "Showing v1 (active)" in all_text(empty)  # 11-3

    add_row(settings.db_path, "src/x/zzz.py", "Uploads")
    full = tab_content(TAB, published_rulebook, queue=queue_data(settings))

    text = all_text(full)
    assert "src/x/zzz.py" in text and "Uploads" in text and "Confirm" in text
    assert "Backup senior" in text and "First match wins" in text


def test_queue_buttons_are_disabled_in_edit_mode(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    add_row(settings.db_path, "src/x/zzz.py", "Uploads")

    content, editing = run_action(settings, TAB, act("edit"), {}, "", None)

    assert editing is True
    assert all(b.disabled for b in q_buttons(content))
    assert "Move up" in all_text(content) and "Move down" in all_text(content)
    assert tabs_disabled(TAB).count(False) == 1  # 11-4
    read = tab_content(TAB, published_rulebook, queue=queue_data(settings))
    assert not any(b.disabled for b in q_buttons(read))


def test_move_up_and_move_down_swap_rows_in_the_draft(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    content, _ = run_action(settings, TAB, act("edit"), {}, "", 1)
    form, _ = form_from_cells(TAB, cells_of(content), [], [])
    names = [row["name"] for row in form["capabilities"]]
    assert len(names) >= 2

    down = {"type": "adm-move", "tab": TAB, "table": "capabilities", "index": 0, "step": 1}
    content, editing = run_action(settings, TAB, down, form, "", 1)
    moved, _ = form_from_cells(TAB, cells_of(content), [], [])

    assert editing is True
    assert [r["name"] for r in moved["capabilities"]][:2] == [names[1], names[0]]
    # Nothing is written by a move.
    assert len(list_versions(settings.db_path)) == 1


def test_a_saved_reorder_gives_a_new_version(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    rows = capability_rows(published_rulebook.rulebook.policy)
    reversed_rows = list(reversed(rows))

    content, editing = run_action(
        settings, TAB, act("save"), {"capabilities": reversed_rows}, "Reorder", 1
    )

    assert editing is False and "Saved as v2" in all_text(content)
    names = [c.name for c in get_active_version(settings.db_path).rulebook.policy.capabilities]
    assert names == [r["name"] for r in reversed_rows]


def test_confirm_asks_first_then_resolves_without_a_pattern(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    row = add_row(settings.db_path, "src/x/zzz.py", "Uploads")
    uid = row.unassigned_id

    asked = run_queue_action(settings, queue_button_id("confirm", uid), {}, {}, 1)

    text = all_text(asked)
    assert "Also add this path as a pattern to 'Uploads'" in text
    assert queue_rows(settings)  # still open: asking changes nothing

    done = run_queue_action(
        settings, queue_button_id("apply", uid, "Uploads", "confirmed"), {}, {}, 1
    )

    assert "Resolved." in all_text(done)
    assert queue_rows(settings) == []
    assert len(list_versions(settings.db_path)) == 1  # 11-30 without the offer


def test_confirm_with_the_pattern_makes_a_new_version_and_records_the_admin(
    make_settings, published_rulebook
):
    settings = settings_for(make_settings)
    row = add_row(settings.db_path, "src/x/zzz.py", "Uploads")
    uid = row.unassigned_id

    done = run_queue_action(
        settings,
        queue_button_id("apply_pattern", uid, "Uploads", "confirmed"),
        {},
        {uid: "Add zzz to Uploads"},
        1,
    )

    assert "The catalog is now v2" in all_text(done)
    active = get_active_version(settings.db_path)
    assert active.change_note == "Add zzz to Uploads"
    closed = resolved_rows(settings)[0]
    assert (closed.state, closed.resolved_by) == ("confirmed", ADMIN)


def test_a_pattern_without_a_note_is_refused_and_the_row_stays_open(
    make_settings, published_rulebook
):
    settings = settings_for(make_settings)
    row = add_row(settings.db_path, "src/x/zzz.py", "Uploads")

    shown = run_queue_action(
        settings,
        queue_button_id("apply_pattern", row.unassigned_id, "Uploads", "confirmed"),
        {},
        {},
        1,
    )

    assert "change note is empty" in all_text(shown)
    assert len(queue_rows(settings)) == 1 and len(list_versions(settings.db_path)) == 1


def test_no_offer_when_an_earlier_capability_already_matches(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    row = add_row(settings.db_path, "src/x/limits_new.py", "Reports")  # matches Limits today

    asked = run_queue_action(settings, queue_button_id("confirm", row.unassigned_id), {}, {}, 1)

    text = all_text(asked)
    assert "already matches" in text and "Limits" in text
    assert "Add pattern and resolve" not in text


def test_move_to_closes_the_row_as_changed_and_stores_the_target(
    make_settings, published_rulebook
):
    settings = settings_for(make_settings)
    row = add_row(settings.db_path, "src/x/zzz.py", "Uploads")
    uid = row.unassigned_id
    other = published_rulebook.rulebook.policy.capabilities[0].name

    asked = run_queue_action(settings, queue_button_id("move", uid), {uid: other}, {}, 1)
    assert f"Move to {other}" in all_text(asked)
    run_queue_action(
        settings, queue_button_id("apply", uid, other, "changed"), {}, {}, 1
    )

    closed = resolved_rows(settings)[0]
    assert (closed.state, closed.resolved_capability) == ("changed", other)


def test_move_without_a_choice_asks_for_one(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    row = add_row(settings.db_path, "src/x/zzz.py", "Uploads")

    shown = run_queue_action(settings, queue_button_id("move", row.unassigned_id), {}, {}, 1)

    assert "Choose a capability first." in all_text(shown)


def test_a_stale_pattern_save_shows_reload_and_leaves_the_row_open(
    make_settings, published_rulebook
):
    settings = settings_for(make_settings)
    row = add_row(settings.db_path, "src/x/zzz.py", "Uploads")
    run_action(settings, "build", {"type": "adm-act", "tab": "build", "action": "save"},
               {"build_max_rounds": "4"}, "Meanwhile", 1)

    shown = run_queue_action(
        settings,
        queue_button_id("apply_pattern", row.unassigned_id, "Uploads", "confirmed"),
        {},
        {row.unassigned_id: "Late"},
        1,
    )

    assert "Reload v2" in all_text(shown)
    assert len(queue_rows(settings)) == 1


def test_a_row_closed_elsewhere_is_reported(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    row = add_row(settings.db_path, "src/x/zzz.py", "Uploads")
    button = queue_button_id("apply", row.unassigned_id, "Uploads", "confirmed")
    run_queue_action(settings, button, {}, {}, 1)

    again = run_queue_action(settings, button, {}, {}, 1)

    assert "not open any more" in all_text(again)


def test_show_resolved_lists_who_and_when_and_hide_goes_back(make_settings, published_rulebook):
    settings = settings_for(make_settings)
    row = add_row(settings.db_path, "src/x/zzz.py", "Uploads")
    run_queue_action(
        settings, queue_button_id("apply", row.unassigned_id, "Uploads", "confirmed"), {}, {}, 1
    )

    shown = run_queue_action(settings, queue_button_id("show_resolved"), {}, {}, 1)

    text = all_text(shown)
    assert "src/x/zzz.py" in text and ADMIN in text and "Hide resolved" in text
    hidden = run_queue_action(settings, queue_button_id("hide_resolved"), {}, {}, 1)
    assert "Show resolved" in all_text(hidden)


def test_hide_resolved_is_disabled_in_edit_mode():
    queue = {"rows": [], "resolved": [], "dialog": None, "notice": []}

    block = queue_block(queue, ["Uploads"], disabled=True)

    hide_id = queue_button_id("hide_resolved")
    buttons = [n for n in walk(block) if getattr(n, "id", None) == hide_id]
    assert len(buttons) == 1 and buttons[0].disabled is True


def test_no_retired_field_shows_on_the_catalog_tab(make_settings, published_rulebook):
    settings = settings_for(make_settings)

    view = tab_content(TAB, published_rulebook, editable=True, queue=queue_data(settings))

    text = all_text(view).lower()
    assert not any(word in text for word in RETIRED)


def test_the_queue_wrapper_reads_picks_and_notes_from_three_states():
    # Dash gives only the States, not the clicked button: picks, notes, base store.
    states = [
        [{"id": {"type": "adm-q-pick", "uid": 4}, "value": "Limits"}],
        [{"id": {"type": "adm-q-note", "uid": 4}, "value": None}],
        [{"id": {"type": "adm-base", "tab": "capability"}, "value": 1}],
    ]

    picks, notes = queue_inputs_from_states(states)

    assert picks == {4: "Limits"} and notes == {4: ""}
