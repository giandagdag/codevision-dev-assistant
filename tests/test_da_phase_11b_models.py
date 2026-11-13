"""Phase 11b step 1: the new rulebook fields, their checks, the seed, and the Unassigned column."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from agents.da_admin_diff import CATALOG_ORDER_PATH, diff_rulebooks
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_enhance import (
    add_unassigned,
    ensure_enhance_tables,
    list_resolved,
    list_unassigned,
    resolve_unassigned,
)
from db_table_functions.db_tbl_da_rulebook import load_rulebook_file
from pydantic_classes.da_rulebook_models import (
    SONAR_SEVERITY_KEYS,
    Capability,
    GoldenExample,
    Policy,
    Rulebook,
    find_rulebook_problems,
)
from tests.da_build_play import ready_with_workspace

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
OLD_11A_SEED = Path(__file__).parent / "data" / "da_rulebook_seed_11a.json"


def with_policy(rulebook: Rulebook, **changes) -> Rulebook:
    return rulebook.model_copy(update={"policy": rulebook.policy.model_copy(update=changes)})


def capability(name: str, patterns=("*x*",)) -> Capability:
    return Capability(
        name=name, description="Made up.", named_senior="Lead", path_patterns=list(patterns)
    )


# --- The new fields and their checks ---


def test_an_11a_shape_version_loads_with_the_11b_defaults():
    old = load_rulebook_file(OLD_11A_SEED)

    assert old.golden_examples == []
    assert all(c.backup_senior == "" for c in old.policy.capabilities)
    assert old.policy.sonar_severity_map["MAJOR"] == "should_fix"
    assert find_rulebook_problems(old) == []


def test_the_seed_has_backups_a_golden_example_and_no_library_in_both_lists(seed_rulebook):
    policy = seed_rulebook.policy

    assert all(c.backup_senior for c in policy.capabilities)
    assert [g.title for g in seed_rulebook.golden_examples]
    assert set(policy.approved_libraries).isdisjoint(policy.build_blocked_imports)
    defaults = Policy(escalation_triggers=[])
    assert set(defaults.approved_libraries).isdisjoint(defaults.build_blocked_imports)
    assert find_rulebook_problems(seed_rulebook) == []


def test_11_16_a_map_missing_a_key_is_refused_naming_it(seed_rulebook):
    short = {k: v for k, v in seed_rulebook.policy.sonar_severity_map.items() if k != "INFO"}

    problems = find_rulebook_problems(with_policy(seed_rulebook, sonar_severity_map=short))

    assert problems == ["The SonarQube severity map is missing the key INFO."]


def test_an_extra_sonar_key_is_refused_naming_it(seed_rulebook):
    extra = {**seed_rulebook.policy.sonar_severity_map, "SEVERE": "fyi"}

    problems = find_rulebook_problems(with_policy(seed_rulebook, sonar_severity_map=extra))

    assert problems == ["The SonarQube severity map has an unknown key SEVERE."]


def test_the_five_sonar_keys_are_fixed():
    assert SONAR_SEVERITY_KEYS == ("BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO")


def test_a_sonar_value_must_be_one_of_our_three_severities():
    with pytest.raises(ValidationError):
        Policy(escalation_triggers=[], sonar_severity_map={"MAJOR": "urgent"})


def test_two_capabilities_with_the_same_name_in_any_case_are_refused(seed_rulebook):
    caps = [capability("Cards"), capability("cards ")]

    problems = find_rulebook_problems(with_policy(seed_rulebook, capabilities=caps))

    assert problems == ["Capability 'cards ' is listed more than once."]


def test_a_blank_capability_pattern_is_refused(seed_rulebook):
    caps = [capability("Cards", patterns=("*cards*", "  "))]

    problems = find_rulebook_problems(with_policy(seed_rulebook, capabilities=caps))

    assert problems == ["Capability 'Cards' has an empty path pattern."]


def test_a_golden_example_needs_a_title_and_code():
    with pytest.raises(ValidationError):
        GoldenExample(title="", code="x = 1")
    with pytest.raises(ValidationError):
        GoldenExample(title="A title", code="")


def test_a_golden_example_is_kept_in_the_saved_json(seed_rulebook):
    example = GoldenExample(title="Plain sum", tags=["general"], code="total = a + b", why="Clear.")
    book = seed_rulebook.model_copy(update={"golden_examples": [example]})

    again = Rulebook.model_validate(book.model_dump(mode="json"))

    assert again.golden_examples == [example]


# --- The diff ---


def test_a_catalog_reorder_shows_in_the_diff_because_first_match_wins(seed_rulebook):
    caps = seed_rulebook.policy.capabilities
    swapped = with_policy(seed_rulebook, capabilities=[caps[1], caps[0], *caps[2:]])

    diff = diff_rulebooks(seed_rulebook, swapped)

    assert diff.paths == [CATALOG_ORDER_PATH]
    assert diff.changed[CATALOG_ORDER_PATH][1].startswith("Reports > Limits")


def test_a_rule_reorder_is_still_an_empty_diff(seed_rulebook):
    flipped = seed_rulebook.model_copy(update={"rules": list(reversed(seed_rulebook.rules))})

    assert diff_rulebooks(seed_rulebook, flipped).is_empty


def test_golden_examples_are_keyed_by_title_so_a_reorder_is_empty(seed_rulebook):
    one = GoldenExample(title="One", code="a = 1")
    two = GoldenExample(title="Two", code="b = 2")
    first = seed_rulebook.model_copy(update={"golden_examples": [one, two]})
    second = seed_rulebook.model_copy(update={"golden_examples": [two, one]})

    assert diff_rulebooks(first, second).is_empty


# --- The Unassigned queue column ---


@pytest.fixture
def settings(make_settings):
    return make_settings()


def test_resolve_stores_the_capability_it_was_moved_to(published_rulebook, settings):
    request_id = ready_with_workspace(settings)[0]
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        row = add_unassigned(conn, "util/odd.py", "Limits", request_id, NOW)
        resolve_unassigned(conn, row.unassigned_id, "changed", "Admin", NOW, "Reports")

        moved = list_unassigned(conn, "changed")[0]

    assert (moved.resolved_capability, moved.picked_capability) == ("Reports", "Limits")


def test_a_confirmed_row_has_no_moved_to_capability(published_rulebook, settings):
    request_id = ready_with_workspace(settings)[0]
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        row = add_unassigned(conn, "util/odd.py", "Limits", request_id, NOW)
        resolve_unassigned(conn, row.unassigned_id, "confirmed", "Admin", NOW)

        assert list_unassigned(conn, "confirmed")[0].resolved_capability == ""


def test_an_old_database_without_the_column_gets_it(tmp_path):
    old_db = tmp_path / "old.db"
    with open_db(old_db) as conn:
        conn.execute(
            "CREATE TABLE da_unassigned_files (unassigned_id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " path TEXT NOT NULL, picked_capability TEXT NOT NULL, request_id TEXT NOT NULL,"
            " state TEXT NOT NULL, resolved_by TEXT NOT NULL, resolved_at TEXT,"
            " created_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO da_unassigned_files VALUES (1, 'a.py', 'Limits', 'CVDA-2026-0001',"
            " 'open', '', NULL, '2026-11-01T09:00:00+00:00')"
        )
        ensure_enhance_tables(conn)

        columns = {r["name"] for r in conn.execute("PRAGMA table_info(da_unassigned_files)")}
        assert "resolved_capability" in columns
        assert list_unassigned(conn)[0].resolved_capability == ""


def test_list_resolved_returns_both_states_newest_first_and_stops_at_the_limit(
    published_rulebook, settings
):
    request_id = ready_with_workspace(settings)[0]
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        for number in range(53):
            row = add_unassigned(conn, f"util/f{number}.py", "Limits", request_id, NOW)
            state = "confirmed" if number % 2 else "changed"
            resolve_unassigned(
                conn, row.unassigned_id, state, "Admin", NOW + timedelta(minutes=number)
            )
        still_open = add_unassigned(conn, "util/open.py", "Limits", request_id, NOW)

        rows = list_resolved(conn)

    assert len(rows) == 50
    assert rows[0].path == "util/f52.py"
    assert {r.state for r in rows} == {"confirmed", "changed"}
    assert still_open.path not in {r.path for r in rows}
