"""Fix 11-1, step 3: the new rulebook fields, with defaults so every old version still loads."""

from agents.da_admin_forms import _golden_rows
from pydantic_classes.da_rulebook_models import (
    GoldenExample,
    Rulebook,
    find_rulebook_problems,
)

NEW_POLICY_FIELDS = (
    "index_repo", "index_branch", "index_folder_scope", "index_refresh_mode", "index_exclusions",
)


def test_a_version_saved_before_the_fix_loads_with_defaults(seed_rulebook):
    old = seed_rulebook.model_dump(mode="json")
    for name in NEW_POLICY_FIELDS:
        del old["policy"][name]
    del old["brand_constants"]
    for example in old["golden_examples"]:
        del example["program_type"]
        del example["module_path"]

    loaded = Rulebook.model_validate(old)

    assert loaded.policy.index_branch == "main"
    assert loaded.policy.index_refresh_mode == "manual"
    assert loaded.policy.index_exclusions == []
    assert loaded.policy.index_folder_scope == ""
    assert loaded.brand_constants == []
    # No program type stored: the first tag ("data"), as the spec says.
    assert loaded.golden_examples[0].program_type == "data"
    assert loaded.golden_examples[0].module_path == ""


def test_a_golden_example_without_tags_defaults_to_utility():
    assert GoldenExample(title="A", code="x = 1").program_type == "Utility"


def test_the_seed_has_one_golden_example_per_program_type(seed_rulebook):
    types = {g.program_type for g in seed_rulebook.golden_examples}

    assert types == {"Screen", "Batch or ingestion", "Utility"}
    assert find_rulebook_problems(seed_rulebook) == []


def test_the_seed_brand_table_has_the_agreed_rows(seed_rulebook):
    names = {b.name for b in seed_rulebook.brand_constants}

    assert {"FONT_FAMILY", "FONT_BOLD", "SPACING", "TABLE_PAGE_SIZE"} <= names
    assert any(b.value == "Pending brand guide" for b in seed_rulebook.brand_constants)


def test_the_seed_index_settings_point_at_the_made_up_folder(seed_rulebook):
    assert seed_rulebook.policy.index_folder_scope == "src/data/da_fake_codevision"
    assert seed_rulebook.policy.index_refresh_mode == "manual"


def test_a_four_column_row_from_the_screen_keeps_the_saved_program_type(seed_rulebook):
    rows = [
        {k: v for k, v in g.model_dump().items() if k in ("title", "tags", "code", "why")}
        for g in seed_rulebook.golden_examples
    ]

    cleaned = _golden_rows(rows, seed_rulebook.golden_examples)
    kept = [GoldenExample.model_validate(r) for r in cleaned]

    assert kept == seed_rulebook.golden_examples


def test_saving_golden_rows_keeps_program_type_and_module_path(seed_rulebook):
    rows = [g.model_dump() for g in seed_rulebook.golden_examples]

    kept = [GoldenExample.model_validate(r) for r in _golden_rows(rows)]

    assert kept == seed_rulebook.golden_examples
