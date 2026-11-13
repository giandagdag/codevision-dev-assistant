import json

from agents.da_admin_forms import (
    RESULT_PROBLEMS,
    RESULT_REFUSED_NOTE,
    RESULT_SAVED,
    RESULT_STALE,
    RESULT_UNCHANGED,
    field_bounds,
    rulebook_from_form,
    save_from_form,
)
from db_table_functions.db_tbl_da_rulebook import (
    get_active_version,
    list_versions,
    publish_first_version,
    restore_version,
)
from pydantic_classes.da_rulebook_models import (
    CHARTER_CHARACTER_LIMIT,
    Rulebook,
    check_charter_size,
)

ADMIN = "admin-0001"
OLD_SEED = "tests/data/da_rulebook_seed_phase1.json"


def build_form(policy):
    """A form that repeats the current values (so it changes nothing)."""
    return {
        "build_max_rounds": str(policy.build_max_rounds),
        "build_test_timeout_seconds": str(policy.build_test_timeout_seconds),
        "max_files": str(policy.max_files),
        "triggers": {t.name: t.on for t in policy.escalation_triggers},
    }


def test_a_changed_limit_saves_a_new_version_with_note_and_admin(db_path, published_rulebook):
    form = build_form(published_rulebook.rulebook.policy) | {"build_max_rounds": "4"}

    result = save_from_form(db_path, "build", form, 1, ADMIN, "More rounds")

    assert result.kind == RESULT_SAVED
    assert result.version_number == 2
    active = get_active_version(db_path)
    assert (active.change_note, active.saved_by) == ("More rounds", ADMIN)
    assert active.rulebook.policy.build_max_rounds == 4


def test_empty_note_is_refused_and_nothing_is_saved(db_path, published_rulebook):
    form = build_form(published_rulebook.rulebook.policy) | {"build_max_rounds": "4"}

    result = save_from_form(db_path, "build", form, 1, ADMIN, "  ")

    assert result.kind == RESULT_REFUSED_NOTE
    assert "change note is empty" in result.message
    assert len(list_versions(db_path)) == 1


def test_two_problems_come_back_together_and_nothing_is_saved(db_path, published_rulebook):
    zone = {"name": "Login", "description": "d", "path_patterns": ["*login*"]}
    form = {
        "zones": [zone, zone],
        "triggers": [{"name": "dispute", "on": True}, {"name": "dispute", "on": True}],
    }

    result = save_from_form(db_path, "build", form, 1, ADMIN, "Two problems")

    assert result.kind == RESULT_PROBLEMS
    assert len(result.problems) == 2
    assert any("more than once" in line for line in result.problems)
    assert any("triggers" in line for line in result.problems)
    assert len(list_versions(db_path)) == 1


def test_a_stale_save_names_the_newer_version(db_path, published_rulebook):
    first = build_form(published_rulebook.rulebook.policy) | {"build_max_rounds": "4"}
    save_from_form(db_path, "build", first, 1, ADMIN, "Someone else")
    mine = build_form(published_rulebook.rulebook.policy) | {"build_max_rounds": "2"}

    result = save_from_form(db_path, "build", mine, 1, ADMIN, "Mine")

    assert result.kind == RESULT_STALE
    assert result.newest_version == 2
    assert "v2" in result.message
    assert len(list_versions(db_path)) == 2


def test_a_form_with_no_change_says_no_changes(db_path, published_rulebook):
    result = save_from_form(
        db_path, "build", build_form(published_rulebook.rulebook.policy), 1, ADMIN, "Nothing"
    )

    assert result.kind == RESULT_UNCHANGED
    assert "No changes to save" in result.message
    assert len(list_versions(db_path)) == 1


def test_building_the_edited_rulebook_writes_nothing(db_path, published_rulebook):
    # Cancel = never call save_from_form. Building the form's rulebook is a pure calculation.
    form = build_form(published_rulebook.rulebook.policy) | {"build_max_rounds": "5"}

    edited = rulebook_from_form(published_rulebook.rulebook, "build", form)

    assert edited.policy.build_max_rounds == 5
    assert get_active_version(db_path).rulebook.policy.build_max_rounds == 3
    assert len(list_versions(db_path)) == 1


def test_a_limit_out_of_bounds_is_refused_with_the_bound(db_path, published_rulebook):
    form = build_form(published_rulebook.rulebook.policy) | {"build_max_rounds": "9"}

    result = save_from_form(db_path, "build", form, 1, ADMIN, "Too many")

    assert result.kind == RESULT_PROBLEMS
    assert result.problems == [
        "build_max_rounds: Input should be less than or equal to 5 (allowed: 1 to 5)"
    ]
    assert len(list_versions(db_path)) == 1
    assert field_bounds("build_max_rounds") == "1 to 5"


def test_text_that_is_not_a_number_is_a_plain_problem(db_path, published_rulebook):
    form = build_form(published_rulebook.rulebook.policy) | {"max_files": "many"}

    result = save_from_form(db_path, "build", form, 1, ADMIN, "Typo")

    assert result.kind == RESULT_PROBLEMS
    assert result.problems[0].startswith("max_files:")


def test_a_trigger_set_off_is_saved_off(db_path, published_rulebook):
    form = build_form(published_rulebook.rulebook.policy)
    form["triggers"]["cap_hit_twice"] = False

    result = save_from_form(db_path, "build", form, 1, ADMIN, "Switch off")

    assert result.kind == RESULT_SAVED
    saved = get_active_version(db_path).rulebook.policy.escalation_triggers
    assert {t.name: t.on for t in saved}["cap_hit_twice"] is False
    assert len(saved) == 5


def test_zones_protected_files_and_models_are_saved(db_path, published_rulebook):
    form = {
        "zones": [
            {
                "name": "Payments",
                "description": "Money movement.",
                "examples": "Posting a transfer\n\nRefund",
                "path_patterns": ["*payment*"],
            },
            {"name": "", "description": "", "examples": "", "path_patterns": ""},
        ],
        "protected_files": ["secrets/*", " ", "src/web/web_server.py"],
        "generator_model": " qwen-made-up ",
        "tester_model": "",
    }

    result = save_from_form(db_path, "build", form, 1, ADMIN, "Zones and models")

    assert result.kind == RESULT_SAVED
    policy = get_active_version(db_path).rulebook.policy
    assert [zone.name for zone in policy.flag_review_zones] == ["Payments"]
    assert policy.flag_review_zones[0].examples == ["Posting a transfer", "Refund"]
    assert policy.protected_files == ["secrets/*", "src/web/web_server.py"]
    assert (policy.generator_model, policy.tester_model) == ("qwen-made-up", "")


def test_two_zones_with_the_same_name_are_refused_naming_it(db_path, published_rulebook):
    zone = {"name": "Login", "description": "d", "path_patterns": ["*login*"]}

    result = save_from_form(db_path, "build", {"zones": [zone, zone]}, 1, ADMIN, "Dup")

    assert result.kind == RESULT_PROBLEMS
    assert "Login" in result.problems[0]


def test_a_zone_with_no_pattern_is_refused(db_path, published_rulebook):
    zone = {"name": "Empty", "description": "d", "path_patterns": []}

    result = save_from_form(db_path, "build", {"zones": [zone]}, 1, ADMIN, "No pattern")

    assert result.kind == RESULT_PROBLEMS
    assert "path_patterns" in result.problems[0]


def test_a_protected_pattern_that_is_a_whole_allowed_folder_warns(db_path, published_rulebook):
    form = {"protected_files": ["src/agents", ".env"]}

    result = save_from_form(db_path, "build", form, 1, ADMIN, "Lock a folder")

    assert result.kind == RESULT_SAVED
    assert len(result.warnings) == 1
    assert "src/agents" in result.warnings[0]


def test_an_advanced_limit_is_saved(db_path, published_rulebook):
    result = save_from_form(
        db_path, "build", {"admin_unassigned_stale_days": "30"}, 1, ADMIN, "Stale days"
    )

    assert result.kind == RESULT_SAVED
    assert get_active_version(db_path).rulebook.policy.admin_unassigned_stale_days == 30


# --- Charter ---


def test_charter_edit_saves_lists_and_glossary(db_path, published_rulebook):
    form = {
        "purpose": "A new purpose.",
        "in_scope": ["One", "", "Two"],
        "glossary": [
            {"term": "Batch", "meaning": "A group of jobs."},
            {"term": "", "meaning": ""},
        ],
    }

    result = save_from_form(db_path, "charter", form, 1, ADMIN, "Charter edit")

    assert result.kind == RESULT_SAVED
    charter = get_active_version(db_path).rulebook.charter
    assert charter.purpose == "A new purpose."
    assert charter.in_scope == ["One", "Two"]
    assert [(g.term, g.meaning) for g in charter.glossary] == [("Batch", "A group of jobs.")]


def test_charter_half_filled_glossary_row_is_a_problem(db_path, published_rulebook):
    form = {"glossary": [{"term": "Batch", "meaning": ""}]}

    result = save_from_form(db_path, "charter", form, 1, ADMIN, "Half row")

    assert result.kind == RESULT_PROBLEMS
    assert "meaning" in result.problems[0]


def test_charter_at_81_percent_shows_amber(published_rulebook):
    limit = CHARTER_CHARACTER_LIMIT
    base_size = check_charter_size(published_rulebook.rulebook.charter).characters
    purpose_now = len(published_rulebook.rulebook.charter.purpose)
    purpose = "x" * (limit * 81 // 100 - (base_size - purpose_now))

    edited = rulebook_from_form(published_rulebook.rulebook, "charter", {"purpose": purpose})

    size = check_charter_size(edited.charter)
    assert size.status == "amber"
    assert size.percent == 81.0


# --- from an old-shape active version (Gian's home v1) ---


def test_save_from_an_old_shape_version_writes_no_retired_key(db_path):
    with open(OLD_SEED, encoding="utf-8") as handle:
        old = Rulebook.model_validate(json.load(handle))
    publish_first_version(db_path, old, ADMIN, "Old shape")
    form = {"build_max_rounds": "4"}

    result = save_from_form(db_path, "build", form, 1, ADMIN, "From old")

    assert result.kind == RESULT_SAVED
    from db_table_functions.da_db import open_db

    with open_db(db_path) as conn:
        stored = conn.execute(
            "SELECT rulebook FROM da_rulebook_versions WHERE version_number = 2"
        ).fetchone()["rulebook"]
    policy = json.loads(stored)["policy"]
    for key in ("default_level", "max_level", "never_generate_zones", "max_review_rounds"):
        assert key not in policy
    assert len(policy["escalation_triggers"]) == 5


def test_unchanged_form_on_an_old_shape_version_says_no_changes(db_path):
    with open(OLD_SEED, encoding="utf-8") as handle:
        old = Rulebook.model_validate(json.load(handle))
    publish_first_version(db_path, old, ADMIN, "Old shape")

    result = save_from_form(db_path, "build", {"build_max_rounds": "3"}, 1, ADMIN, "Same")

    assert result.kind == RESULT_UNCHANGED


def test_restored_version_holds_the_new_shape(db_path, published_rulebook):
    save_from_form(db_path, "build", {"build_max_rounds": "4"}, 1, ADMIN, "Four")

    restored = restore_version(db_path, 1, ADMIN)

    assert restored.version_number == 3
    assert restored.rulebook.policy.build_max_rounds == 3
