"""Phase 11c step 3: Repository and index (spec 11; tests 11-38 and the shared Save pattern
11-5 to 11-10 for this tab)."""

from pathlib import Path

from agents.da_admin_forms import (
    RESULT_PROBLEMS,
    RESULT_REFUSED_NOTE,
    RESULT_SAVED,
    RESULT_STALE,
    RESULT_UNCHANGED,
    rulebook_from_form,
    save_from_form,
)
from agents.da_admin_overview import server_settings_view
from db_table_functions.db_tbl_da_rulebook import (
    get_active_version,
    list_versions,
    load_rulebook_file,
    publish_first_version,
)

ADMIN = "admin-0001"
TAB = "repo"
OLD_SEED = Path(__file__).parent / "data" / "da_rulebook_seed_phase1.json"


def repo_form(policy):
    """A form that repeats the current values (so it changes nothing)."""
    return {
        "allowed_folders": list(policy.allowed_folders),
        "new_file_name_pattern": policy.new_file_name_pattern,
        "workspace_markers": list(policy.workspace_markers),
        "workspace_max_file_kb": str(policy.workspace_max_file_kb),
    }


def test_11_38_the_server_settings_are_listed_without_any_path_or_key(make_settings):
    secret_dir = Path("C:/very/secret/place")
    settings = make_settings(sandbox_source_dir=secret_dir, anthropic_api_key="sk-not-real")

    view = server_settings_view(settings)

    assert [name for name, _ in view] == [
        "DA_SEARCH_PROVIDER",
        "DA_SEARCH_TOP_K",
        "DA_DISCOVERY_MAX_ROUNDS",
        "DA_MAIN_SOURCE",
        "DA_SANDBOX_SOURCE_DIR",
        "DA_CODEVISION_SRC",
        "DA_CODEVISION_PYTHON",
        "Tests run with",  # Fix G3
        "AI thinks before answering",  # Fix G4 T9
        "DA_SONAR_URL",
        "DA_SONAR_TOKEN",
        "DA_SONAR_PROFILE",
        "DA_SONAR_LANGUAGE",
    ]
    shown = dict(view)
    assert shown["DA_SANDBOX_SOURCE_DIR"] == "set"
    assert shown["DA_SEARCH_TOP_K"] == str(settings.search_top_k)
    text = " ".join(f"{name} {value}" for name, value in view)
    assert "secret" not in text and "sk-not-real" not in text


def test_a_sandbox_folder_that_is_not_set_says_so(make_settings):
    assert dict(server_settings_view(make_settings()))["DA_SANDBOX_SOURCE_DIR"] == "not set"


def test_a_repo_save_changes_only_the_four_fields(db_path, published_rulebook):
    old = published_rulebook.rulebook.policy
    form = repo_form(old) | {
        "workspace_max_file_kb": "300",
        "allowed_folders": ["src/agents", "src/configs"],
        "workspace_markers": "src/\ntests/\n",
        "new_file_name_pattern": r"^da_[a-z_]+\.py$",
    }

    result = save_from_form(db_path, TAB, form, 1, ADMIN, "Smaller picture")

    assert result.kind == RESULT_SAVED and result.version_number == 2
    new = get_active_version(db_path).rulebook.policy
    assert new.workspace_max_file_kb == 300
    assert new.allowed_folders == ["src/agents", "src/configs"]
    assert new.workspace_markers == ["src/", "tests/"]
    assert new.new_file_name_pattern == r"^da_[a-z_]+\.py$"
    untouched = old.model_dump() | {
        "workspace_max_file_kb": 300,
        "allowed_folders": new.allowed_folders,
        "workspace_markers": new.workspace_markers,
        "new_file_name_pattern": new.new_file_name_pattern,
    }
    assert new.model_dump() == untouched  # nothing else on the policy moved


def test_a_pattern_that_does_not_compile_is_refused_with_the_models_words(
    db_path, published_rulebook
):
    form = repo_form(published_rulebook.rulebook.policy) | {"new_file_name_pattern": "(["}

    result = save_from_form(db_path, TAB, form, 1, ADMIN, "Broken")

    assert result.kind == RESULT_PROBLEMS
    assert any("not a valid regular expression" in line for line in result.problems)
    assert len(list_versions(db_path)) == 1


def test_two_bad_values_come_back_together(db_path, published_rulebook):
    form = repo_form(published_rulebook.rulebook.policy) | {
        "new_file_name_pattern": "([",
        "workspace_max_file_kb": "0",
    }

    result = save_from_form(db_path, TAB, form, 1, ADMIN, "Two problems")

    assert result.kind == RESULT_PROBLEMS and len(result.problems) == 2
    assert len(list_versions(db_path)) == 1


def test_11_5_an_empty_note_is_refused(db_path, published_rulebook):
    form = repo_form(published_rulebook.rulebook.policy) | {"workspace_max_file_kb": "300"}

    result = save_from_form(db_path, TAB, form, 1, ADMIN, " ")

    assert result.kind == RESULT_REFUSED_NOTE and len(list_versions(db_path)) == 1


def test_11_8_a_stale_save_names_the_newer_version(db_path, published_rulebook):
    policy = published_rulebook.rulebook.policy
    first = repo_form(policy) | {"workspace_max_file_kb": "300"}
    save_from_form(db_path, TAB, first, 1, ADMIN, "A")

    result = save_from_form(
        db_path, TAB, repo_form(policy) | {"workspace_max_file_kb": "200"}, 1, ADMIN, "B"
    )

    assert result.kind == RESULT_STALE and result.newest_version == 2


def test_11_9_a_form_with_no_change_says_no_changes(db_path, published_rulebook):
    result = save_from_form(
        db_path, TAB, repo_form(published_rulebook.rulebook.policy), 1, ADMIN, "Nothing"
    )

    assert result.kind == RESULT_UNCHANGED and len(list_versions(db_path)) == 1


def test_11_10_building_the_form_writes_nothing_so_cancel_changes_nothing(
    db_path, published_rulebook
):
    form = repo_form(published_rulebook.rulebook.policy) | {"workspace_max_file_kb": "300"}

    edited = rulebook_from_form(published_rulebook.rulebook, TAB, form)

    assert edited.policy.workspace_max_file_kb == 300
    assert get_active_version(db_path) == published_rulebook
    assert len(list_versions(db_path)) == 1


def test_a_repo_save_writes_no_retired_field(db_path):
    old = load_rulebook_file(Path(OLD_SEED))
    publish_first_version(db_path, old, ADMIN, "Old shape")
    form = repo_form(old.policy) | {"workspace_max_file_kb": "300"}

    result = save_from_form(db_path, TAB, form, 1, ADMIN, "Repo edit")

    assert result.kind == RESULT_SAVED
    policy = get_active_version(db_path).rulebook.policy
    assert policy.default_level is None and policy.max_level is None
    assert policy.never_generate_zones == [] and policy.max_review_rounds is None
