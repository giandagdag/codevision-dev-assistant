"""Phase 11b step 3: the catalog tab form, the no-folder-match warning and the Unassigned queue."""

from datetime import UTC, datetime, timedelta

import pytest

from agents.da_admin_catalog import (
    pattern_offer,
    queue_rows,
    resolve_row,
    resolved_rows,
    would_match,
)
from agents.da_admin_forms import (
    RESULT_PROBLEMS,
    RESULT_SAVED,
    RESULT_STALE,
    RESULT_UNCHANGED,
    capabilities_without_backup,
    capability_rows,
    move_row,
    pattern_warnings,
    save_from_form,
)
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_enhance import add_unassigned
from db_table_functions.db_tbl_da_requests import create_request
from db_table_functions.db_tbl_da_rulebook import get_active_version, list_versions

ADMIN = "admin-0001"


def add_row(db_path, path, picked="Limits", when=None):
    # A real request each time: the Unassigned row points at it.
    request = create_request(db_path, f"Change for {path}", "dev-0001")
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        row = add_unassigned(conn, path, picked, request.request_id, when or datetime.now(UTC))
    return row


def catalog_form(rulebook):
    return {"capabilities": capability_rows(rulebook.policy)}


def test_an_unchanged_catalog_form_says_no_changes(db_path, published_rulebook):
    form = catalog_form(published_rulebook.rulebook)

    assert save_from_form(db_path, "capability", form, 1, ADMIN, "x").kind == RESULT_UNCHANGED


def test_a_backup_senior_is_saved(db_path, published_rulebook):
    form = catalog_form(published_rulebook.rulebook)
    form["capabilities"][0]["backup_senior"] = "New deputy"

    result = save_from_form(db_path, "capability", form, 1, ADMIN, "New deputy")

    assert result.kind == RESULT_SAVED
    saved = get_active_version(db_path).rulebook.policy.capabilities[0]
    assert saved.backup_senior == "New deputy"


def test_a_new_capability_row_and_an_empty_one(db_path, published_rulebook):
    form = catalog_form(published_rulebook.rulebook)
    form["capabilities"].append(
        {
            "name": "Loans",
            "description": "Loan set-up.",
            "named_senior": "Loans lead",
            "backup_senior": "",
            "path_patterns": "*loan*\n",
        }
    )
    form["capabilities"].append({"name": "", "path_patterns": ""})

    result = save_from_form(db_path, "capability", form, 1, ADMIN, "Add Loans")

    assert result.kind == RESULT_SAVED
    names = [c.name for c in get_active_version(db_path).rulebook.policy.capabilities]
    assert names[-1] == "Loans" and len(names) == 4


def test_duplicate_names_and_empty_patterns_are_refused(db_path, published_rulebook):
    form = catalog_form(published_rulebook.rulebook)
    form["capabilities"][1]["name"] = "limits"

    result = save_from_form(db_path, "capability", form, 1, ADMIN, "Dup")

    assert result.kind == RESULT_PROBLEMS and any("more than once" in p for p in result.problems)


def test_a_stale_catalog_save_names_the_newer_version(db_path, published_rulebook):
    form = catalog_form(published_rulebook.rulebook)
    form["capabilities"][0]["backup_senior"] = "A"
    save_from_form(db_path, "capability", form, 1, ADMIN, "First")
    form["capabilities"][0]["backup_senior"] = "B"

    result = save_from_form(db_path, "capability", form, 1, ADMIN, "Second")

    assert result.kind == RESULT_STALE and result.newest_version == 2


def test_move_row_swaps_and_stops_at_the_ends():
    rows = ["a", "b", "c"]

    assert move_row(rows, 1, -1) == ["b", "a", "c"]
    assert move_row(rows, 1, 1) == ["a", "c", "b"]
    assert move_row(rows, 0, -1) == rows and move_row(rows, 2, 1) == rows
    assert rows == ["a", "b", "c"]  # the original is not changed


def test_catalog_order_matters(db_path, published_rulebook):
    catalog = published_rulebook.rulebook.policy.capabilities
    overlap = catalog[0].model_copy(update={"name": "Everything", "path_patterns": ["*"]})

    assert would_match("src/x/limits_a.py", [overlap, *catalog]) == "Everything"
    assert would_match("src/x/limits_a.py", [*catalog, overlap]) == "Limits"
    assert would_match("src/x/other.py", catalog) == ""


def test_a_reorder_is_saved_and_changes_the_match(db_path, published_rulebook):
    form = catalog_form(published_rulebook.rulebook)
    form["capabilities"] = move_row(form["capabilities"], 2, -1)

    result = save_from_form(db_path, "capability", form, 1, ADMIN, "Move Uploads up")

    assert result.kind == RESULT_SAVED
    names = [c.name for c in get_active_version(db_path).rulebook.policy.capabilities]
    assert names == ["Limits", "Uploads", "Reports"]


def test_no_folder_match_warning_rule(published_rulebook):
    policy = published_rulebook.rulebook.policy
    assert pattern_warnings(policy) == []  # the seed patterns start with *

    def with_pattern(pattern):
        cap = policy.capabilities[0].model_copy(update={"path_patterns": [pattern]})
        return policy.model_copy(update={"capabilities": [cap]})

    assert pattern_warnings(with_pattern("docs/x.py")) != []
    assert pattern_warnings(with_pattern("src/agents/da_*.py")) == []
    assert pattern_warnings(with_pattern("src/*")) == []  # prefix of an allowed folder
    assert pattern_warnings(with_pattern("?x.py")) == []
    assert pattern_warnings(with_pattern("src/agentsx/a.py")) != []


def test_saving_a_pattern_outside_the_folders_warns_but_saves(db_path, published_rulebook):
    form = catalog_form(published_rulebook.rulebook)
    form["capabilities"][0]["path_patterns"] += "\ndocs/x.py"

    result = save_from_form(db_path, "capability", form, 1, ADMIN, "Docs")

    assert result.kind == RESULT_SAVED and any("docs/x.py" in w for w in result.warnings)


def test_capabilities_without_backup(published_rulebook):
    policy = published_rulebook.rulebook.policy
    cap = policy.capabilities[0].model_copy(update={"backup_senior": "  "})
    edited = policy.model_copy(update={"capabilities": [cap, *policy.capabilities[1:]]})

    assert capabilities_without_backup(edited) == ["Limits"]
    assert capabilities_without_backup(policy) == []


# --- queue ---


def test_queue_row_shows_path_pick_request_age_and_match(
    db_path, published_rulebook, make_settings
):
    old = datetime.now(UTC) - timedelta(days=3)
    made = add_row(db_path, "src/x/limits_new.py", "Reports", when=old)
    add_row(db_path, "src/x/zzz.py", "Uploads")

    rows = queue_rows(make_settings())

    assert [r.path for r in rows] == ["src/x/limits_new.py", "src/x/zzz.py"]
    first = rows[0]
    assert (first.picked_capability, first.request_id) == ("Reports", made.request_id)
    assert first.would_match == "Limits" and rows[1].would_match == ""
    assert datetime.now(UTC) - first.waiting_since >= timedelta(days=3)


def test_confirm_without_the_offer_closes_the_row(db_path, published_rulebook, make_settings):
    row = add_row(db_path, "src/x/zzz.py", "Uploads")

    result = resolve_row(make_settings(), row.unassigned_id, "confirmed", "Uploads", ADMIN)

    assert result.kind == "resolved" and result.new_version is None
    assert queue_rows(make_settings()) == []
    done = resolved_rows(make_settings())[0]
    assert (done.state, done.resolved_by, done.resolved_capability) == ("confirmed", ADMIN, "")
    assert len(list_versions(db_path)) == 1


def test_confirm_with_the_offer_saves_a_new_version_with_the_note(
    db_path, published_rulebook, make_settings
):
    row = add_row(db_path, "src/x/zzz.py", "Uploads")

    result = resolve_row(
        make_settings(), row.unassigned_id, "confirmed", "Uploads", ADMIN,
        add_pattern=True, note="zzz belongs to Uploads", base_version=1,
    )  # fmt: skip

    assert result.kind == "resolved" and result.new_version == 2
    active = get_active_version(db_path)
    assert active.change_note == "zzz belongs to Uploads" and active.saved_by == ADMIN
    uploads = next(c for c in active.rulebook.policy.capabilities if c.name == "Uploads")
    assert "src/x/zzz.py" in uploads.path_patterns
    assert would_match("src/x/zzz.py", active.rulebook.policy.capabilities) == "Uploads"
    assert resolved_rows(make_settings())[0].state == "confirmed"


def test_a_refused_pattern_save_leaves_the_row_open(db_path, published_rulebook, make_settings):
    row = add_row(db_path, "src/x/zzz.py", "Uploads")

    result = resolve_row(
        make_settings(), row.unassigned_id, "confirmed", "Uploads", ADMIN,
        add_pattern=True, note="  ", base_version=1,
    )  # fmt: skip

    assert result.kind == "refused"
    assert len(queue_rows(make_settings())) == 1 and len(list_versions(db_path)) == 1


def test_a_stale_view_leaves_the_row_open(db_path, published_rulebook, make_settings):
    row = add_row(db_path, "src/x/zzz.py", "Uploads")
    form = catalog_form(published_rulebook.rulebook)
    form["capabilities"][0]["backup_senior"] = "Changed meanwhile"
    save_from_form(db_path, "capability", form, 1, ADMIN, "Meanwhile")

    result = resolve_row(
        make_settings(), row.unassigned_id, "confirmed", "Uploads", ADMIN,
        add_pattern=True, note="n", base_version=1,
    )  # fmt: skip

    assert result.kind == "refused" and result.stale
    assert len(queue_rows(make_settings())) == 1


def test_no_offer_when_a_capability_already_matches(published_rulebook):
    catalog = published_rulebook.rulebook.policy.capabilities

    said = pattern_offer("src/x/limits_new.py", catalog, "Uploads")

    assert "'Limits'" in said and "already matches" in said
    assert pattern_offer("src/x/zzz.py", catalog, "Uploads") == ""
    assert "not in the catalog" in pattern_offer("src/x/zzz.py", catalog, "Nope")


def test_the_offer_is_skipped_when_a_pattern_already_matches(
    db_path, published_rulebook, make_settings
):
    row = add_row(db_path, "src/x/limits_new.py", "Uploads")

    result = resolve_row(
        make_settings(), row.unassigned_id, "confirmed", "Uploads", ADMIN,
        add_pattern=True, note="n", base_version=1,
    )  # fmt: skip

    assert result.kind == "resolved" and result.new_version is None
    assert len(list_versions(db_path)) == 1


def test_move_closes_the_row_as_changed_and_keeps_the_target(
    db_path, published_rulebook, make_settings
):
    row = add_row(db_path, "src/x/zzz.py", "Uploads")
    with open_db(db_path) as conn:
        before = [tuple(r) for r in conn.execute("SELECT * FROM da_requests")]

    result = resolve_row(make_settings(), row.unassigned_id, "changed", "Reports", ADMIN)

    assert result.kind == "resolved"
    done = resolved_rows(make_settings())[0]
    assert (done.state, done.resolved_capability, done.picked_capability) == (
        "changed",
        "Reports",
        "Uploads",
    )
    with open_db(db_path) as conn:
        assert [tuple(r) for r in conn.execute("SELECT * FROM da_requests")] == before


def test_move_to_an_unknown_capability_is_refused(db_path, published_rulebook, make_settings):
    row = add_row(db_path, "src/x/zzz.py", "Uploads")

    result = resolve_row(make_settings(), row.unassigned_id, "changed", "Nope", ADMIN)

    assert result.kind == "refused" and len(queue_rows(make_settings())) == 1


def test_a_row_cannot_be_resolved_twice(db_path, published_rulebook, make_settings):
    row = add_row(db_path, "src/x/zzz.py", "Uploads")
    resolve_row(make_settings(), row.unassigned_id, "confirmed", "Uploads", ADMIN)

    again = resolve_row(make_settings(), row.unassigned_id, "confirmed", "Uploads", ADMIN)

    assert again.kind == "refused"


@pytest.mark.parametrize("count", [3, 55])
def test_show_resolved_is_limited_to_fifty(db_path, published_rulebook, make_settings, count):
    for number in range(count):
        row = add_row(db_path, f"src/x/f{number}.py", "Uploads")
        resolve_row(make_settings(), row.unassigned_id, "confirmed", "Uploads", ADMIN)

    assert len(resolved_rows(make_settings())) == min(count, 50)
