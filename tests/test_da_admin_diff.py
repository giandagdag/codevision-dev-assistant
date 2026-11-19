from datetime import UTC, datetime
from pathlib import Path

from agents.da_admin_diff import (
    area_of_path,
    build_timeline,
    diff_rulebooks,
    open_request_lines,
    text_line_diff,
)
from db_table_functions.db_tbl_da_requests import create_request, list_pinned_request_ids
from db_table_functions.db_tbl_da_rulebook import (
    load_rulebook_file,
    restore_version,
    save_new_version,
)
from pydantic_classes.da_rulebook_models import without_retired_fields

ADMIN = "admin-0001"
T1 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def with_policy(rulebook, **changes):
    return rulebook.model_copy(update={"policy": rulebook.policy.model_copy(update=changes)})


def with_rule_field(rulebook, rule_id, **changes):
    rules = [
        rule.model_copy(update=changes) if rule.rule_id == rule_id else rule
        for rule in rulebook.rules
    ]
    return rulebook.model_copy(update={"rules": rules})


# --- the diff (11-34 to 11-36) ---


def test_diff_lists_exactly_the_changed_paths_with_old_and_new(seed_rulebook):
    v2 = with_rule_field(
        with_policy(seed_rulebook, build_max_rounds=4), "CV-PY-003", why="A new reason."
    )

    diff = diff_rulebooks(seed_rulebook, v2)

    assert diff.paths == ["policy.build_max_rounds", "rules[CV-PY-003].why"]
    assert diff.changed["policy.build_max_rounds"] == (3, 4)
    assert diff.changed["rules[CV-PY-003].why"][1] == "A new reason."
    assert not diff.added and not diff.removed


def test_reordering_rules_is_an_empty_diff(seed_rulebook):
    reordered = seed_rulebook.model_copy(update={"rules": list(reversed(seed_rulebook.rules))})

    assert diff_rulebooks(seed_rulebook, reordered).is_empty


def test_an_edited_plain_word_is_one_removed_and_one_added(seed_rulebook):
    files = [".env", "src/web/other.py"]

    diff = diff_rulebooks(seed_rulebook, with_policy(seed_rulebook, protected_files=files))

    assert 'policy.protected_files[src/web/other.py]' in diff.added
    assert 'policy.protected_files[src/web/web_server.py]' in diff.removed
    assert not diff.changed


def test_a_trigger_switched_off_is_a_change_keyed_by_name(seed_rulebook):
    triggers = [
        t.model_copy(update={"on": False}) if t.name == "dispute" else t
        for t in seed_rulebook.policy.escalation_triggers
    ]

    diff = diff_rulebooks(seed_rulebook, with_policy(seed_rulebook, escalation_triggers=triggers))

    assert diff.changed == {"policy.escalation_triggers[dispute].on": (True, False)}


def test_a_long_changed_text_gets_a_line_diff():
    old = "The first sentence stays. " + "Filler words go here. " * 12 + "The ending is old."
    new = old.replace("The ending is old.", "The ending is new.")

    lines = text_line_diff(old, new)

    assert "-The ending is old." in lines
    assert "+The ending is new." in lines


def test_a_short_text_or_a_number_gets_no_line_diff():
    assert text_line_diff("short", "shorter") == []
    assert text_line_diff(3, 4) == []


# --- areas ---


def test_paths_map_to_their_console_tab():
    assert area_of_path("charter.purpose") == "Project charter"
    assert area_of_path("rules[CV-PY-001].why") == "Coding standards"
    assert area_of_path("rules[CV-UI-001].why") == "UI standards"
    assert area_of_path("policy.capabilities[Limits].named_senior") == "Capability catalog"
    assert area_of_path("policy.allowed_folders[src/web]") == "Repository and index"
    assert area_of_path("policy.approved_libraries[pydantic]") == "Coding standards"
    assert area_of_path("policy.index_folder_scope") == "Repository and index"
    assert area_of_path("policy.index_exclusions[0].pattern") == "Repository and index"
    assert area_of_path("brand_constants[NAVY].value") == "UI standards"
    assert area_of_path("policy.build_max_rounds") == "Build and test"
    assert area_of_path("policy.escalation_triggers[dispute].on") == "Build and test"


# --- the timeline (11-33) ---


def test_timeline_is_newest_first_with_areas_pins_and_the_active_mark(
    db_path, seed_rulebook, published_rulebook
):
    first = create_request(db_path, "First pinned", "dev-0001")
    second = create_request(db_path, "Second pinned", "dev-0002")
    save_new_version(db_path, with_policy(seed_rulebook, build_max_rounds=4), 1, ADMIN, "Rounds")
    changed = with_rule_field(
        with_policy(seed_rulebook, build_max_rounds=4), "CV-PY-001", why="Changed."
    )
    save_new_version(db_path, changed, 2, ADMIN, "A reason")

    rows = build_timeline(db_path)

    assert [row.version_number for row in rows] == [3, 2, 1]
    assert [row.is_active for row in rows] == [True, False, False]
    assert rows[0].areas == ["Coding standards"]
    assert rows[1].areas == ["Build and test"]
    assert rows[2].areas == []
    assert rows[2].pinned_count == 2
    assert rows[2].pinned_request_ids == sorted([first.request_id, second.request_id])
    assert rows[0].pinned_count == 0


def test_timeline_shows_a_restore_and_its_areas(db_path, seed_rulebook, published_rulebook):
    save_new_version(db_path, with_policy(seed_rulebook, build_max_rounds=4), 1, ADMIN, "Rounds")
    restore_version(db_path, 1, ADMIN, now=T1)

    newest = build_timeline(db_path)[0]

    assert newest.restored_from == 1
    assert newest.areas == ["Build and test"]


def test_restore_confirm_counts_only_open_requests_per_old_version(
    db_path, seed_rulebook, published_rulebook
):
    # G-24: 2 open requests on v1 (a third is handed off) while v3 is active.
    import sqlite3
    from contextlib import closing

    create_request(db_path, "Open one", "dev-0001")
    create_request(db_path, "Open two", "dev-0002")
    done = create_request(db_path, "Done", "dev-0003")
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("UPDATE da_requests SET status = 'HANDED_OFF' WHERE request_id = ?",
                     (done.request_id,))
        conn.commit()
    save_new_version(db_path, with_policy(seed_rulebook, build_max_rounds=4), 1, ADMIN, "Rounds")
    changed = with_rule_field(
        with_policy(seed_rulebook, build_max_rounds=4), "CV-PY-001", why="Changed."
    )
    save_new_version(db_path, changed, 2, ADMIN, "A reason")

    assert open_request_lines(db_path, 3) == ["2 open requests use v1 and keep it"]


def test_restore_dialog_shows_the_open_request_line():
    from layouts.da_admin_history_tab import _restore_dialog

    dialog = _restore_dialog(7, 8, ["2 open requests use v6 and keep it"])
    assert "2 open requests use v6 and keep it" in str(dialog)


def test_pinned_ids_are_empty_without_requests(db_path, published_rulebook):
    assert list_pinned_request_ids(db_path) == {}


def test_old_shape_diff_lists_retired_paths_as_removed(seed_rulebook):
    old = load_rulebook_file(Path(__file__).parent / "data" / "da_rulebook_seed_phase1.json")
    diff = diff_rulebooks(old, without_retired_fields(old))

    assert "policy.default_level" in diff.removed
    assert "policy.max_review_rounds" in diff.removed
