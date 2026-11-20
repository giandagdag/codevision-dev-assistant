"""Fix G4 step 3a: find and remove the made-up starter data in a work rulebook (C1, C2)."""

import agents.da_admin_starter as starter
from agents.da_admin_forms import capability_rows, save_from_form
from agents.da_admin_starter import (
    ACTION_ALL,
    ACTION_ONE,
    remove_starter,
    starter_leftovers,
)
from agents.da_admin_tag_store import read_tags, save_store
from agents.da_tag_versions import list_versions as tag_versions
from db_table_functions.db_tbl_da_rulebook import (
    get_active_version,
    list_versions,
    restore_version,
    save_new_version,
)
from layouts.da_admin_starter_card import CLEAR_LABEL, REMOVE_ALL_LABEL, scope_alert, starter_card
from pydantic_classes.da_rulebook_models import Capability


def _with_real_capability(db_path, patterns):
    """Version 2 = the seed plus one real-looking capability that holds the given patterns."""
    active = get_active_version(db_path)
    real = Capability(
        name="Payments",
        description="Payment screens.",
        named_senior="Pay lead",
        path_patterns=patterns,
    )
    policy = active.rulebook.policy
    caps = [*policy.capabilities, real]
    book = active.rulebook.model_copy(
        update={"policy": policy.model_copy(update={"capabilities": caps})}
    )
    save_new_version(db_path, book, 1, "admin-0001", "add real one")


def test_the_seed_itself_shows_scope_and_three_capabilities(published_rulebook):
    found = starter_leftovers(published_rulebook.rulebook)

    assert [x.kind for x in found] == ["scope", "capability", "capability", "capability"]


def test_a_real_capability_with_two_made_up_patterns_is_flagged_by_pattern(
    db_path, published_rulebook
):
    full = "src/data/da_fake_codevision/src/layouts/limits_menu.py"
    _with_real_capability(db_path, ["src/agents/limits_batch.py", full, "*pay*"])

    found = starter_leftovers(get_active_version(db_path).rulebook)

    patterns = [x for x in found if x.kind == "pattern"]
    assert [x.capability for x in patterns] == ["Payments", "Payments"]
    assert "*pay*" not in [x.text for x in found]


def test_remove_all_saves_one_version_and_restore_brings_it_back(
    db_path, published_rulebook, make_settings
):
    _with_real_capability(db_path, ["src/agents/limits_batch.py", "*pay*"])
    before = len(list_versions(db_path))

    text = remove_starter(make_settings(), "admin-0001", ACTION_ALL)

    assert len(list_versions(db_path)) == before + 1
    active = get_active_version(db_path)
    assert [c.name for c in active.rulebook.policy.capabilities] == ["Payments"]
    assert active.rulebook.policy.capabilities[0].path_patterns == ["*pay*"]
    assert active.rulebook.policy.index_folder_scope == ""
    assert "3 capabilities, 1 pattern" in text
    assert starter_leftovers(active.rulebook) == []

    restore_version(db_path, 2, "admin-0001", "undo")

    assert len(starter_leftovers(get_active_version(db_path).rulebook)) == 5


def test_remove_one_row_and_a_capability_with_no_pattern_left_goes_too(
    db_path, published_rulebook, make_settings
):
    _with_real_capability(db_path, ["src/agents/limits_batch.py"])
    found = starter_leftovers(get_active_version(db_path).rulebook)
    index = next(i for i, x in enumerate(found) if x.kind == "pattern")

    remove_starter(make_settings(), "admin-0001", f"{ACTION_ONE}{index}")

    names = [c.name for c in get_active_version(db_path).rulebook.policy.capabilities]
    assert "Payments" not in names
    assert len(names) == 3


def test_approved_tags_of_a_removed_capability_go_back_to_the_queue(
    db_path, published_rulebook, make_settings, tmp_path, monkeypatch
):
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path))
    entry = {"state": "approved", "proposed_capability": "Limits"}
    other = {"state": "approved", "proposed_capability": "Payments"}
    save_store({"modules": {"a.py": entry, "b.py": other}, "runs": []}, tmp_path)

    text = remove_starter(make_settings(), "admin-0001", ACTION_ALL)

    tags = read_tags(tmp_path)
    assert tags["a.py"]["state"] == "proposed"
    assert tags["b.py"]["state"] == "approved"  # its capability was not removed
    assert "1 approved programs back in the queue" in text
    assert len(tag_versions(tmp_path)) == 2  # the starting tags, then the change


def test_a_catalog_form_save_that_drops_a_capability_requeues_its_tags(
    db_path, published_rulebook, tmp_path, monkeypatch
):
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path))
    save_store(
        {"modules": {"a.py": {"state": "approved", "proposed_capability": "Uploads"}}, "runs": []},
        tmp_path,
    )
    rows = capability_rows(published_rulebook.rulebook.policy)[:2]  # Uploads dropped

    result = save_from_form(db_path, "capability", {"capabilities": rows}, 1, "admin-0001", "drop")

    assert result.kind == "saved"
    assert read_tags(tmp_path)["a.py"]["state"] == "proposed"


def test_starter_at_work_is_empty_at_home(published_rulebook, monkeypatch):
    class Home:
        llm_provider = "fake"

    monkeypatch.setattr(starter, "load_settings", lambda: Home())

    assert starter.starter_at_work(published_rulebook.rulebook) == []


def test_the_screens_show_the_red_box_and_the_card(published_rulebook):
    found = starter_leftovers(published_rulebook.rulebook)

    assert CLEAR_LABEL in str(scope_alert(found))
    assert REMOVE_ALL_LABEL in str(starter_card(found))
    assert scope_alert([x for x in found if x.kind != "scope"]) is None
    assert starter_card([]) is None
