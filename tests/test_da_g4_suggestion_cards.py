"""Fix G4 step 4b: the new-capability suggestion card (S4, S5; G4-12, G4-13). Made-up only."""

from agents.da_admin_suggestions import (
    assign_suggestion,
    create_and_assign,
    reject_suggestion,
    remove_from_suggestion,
    suggestions,
)
from agents.da_admin_tag_cards import ai_cards
from agents.da_admin_tag_store import read_tags, save_store
from db_table_functions.db_tbl_da_rulebook import get_active_version, list_versions
from layouts.da_admin_catalog_tab import queue_block

ADMIN = "admin-0001"


def _entry(confidence, name="Document export"):
    return {"summary": "Does a thing.", "proposed_capability": "", "confidence": confidence,
            "reason": "r", "state": "proposed", "new_name": name, "new_description": "Writes docs."}


def _seed(tmp_path):
    save_store({"modules": {
        "zz/a.py": _entry("high"), "zz/b.py": _entry("low"), "zz/c.py": _entry("medium"),
        "zz/plain.py": {**_entry("high"), "new_name": "", "proposed_capability": "Uploads"},
    }, "runs": []}, tmp_path)


def test_suggestion_groups_its_modules_and_takes_the_lowest_confidence(tmp_path):
    _seed(tmp_path)

    [one] = suggestions(tmp_path)

    assert one.name == "Document export" and one.confidence == "low"
    assert list(one.modules) == ["zz/a.py", "zz/b.py", "zz/c.py"]
    assert [c.path for c in ai_cards(tmp_path)] == ["zz/plain.py"]  # no second card


def test_g4_12_create_and_assign_is_one_version_with_exact_patterns(
    db_path, published_rulebook, make_settings, tmp_path
):
    _seed(tmp_path)
    remove_from_suggestion("zz/c.py", tmp_path)  # kept 2 of 3
    kept = list(suggestions(tmp_path)[0].modules)

    result = create_and_assign(make_settings(), " Doc  export ", "Writes docs.", "Ana Cruz", "",
                               kept, ADMIN, 1, tmp_path)

    assert result.kind == "resolved" and len(list_versions(db_path)) == 2
    active = get_active_version(db_path)
    assert active.change_note == "AI suggestion: new capability Doc export with 2 programs"
    new = next(c for c in active.rulebook.policy.capabilities if c.name == "Doc export")
    assert new.path_patterns == ["zz/a.py", "zz/b.py"]
    tags = read_tags(tmp_path)
    assert tags["zz/a.py"]["state"] == "approved"
    assert tags["zz/c.py"]["state"] == "proposed" and not tags["zz/c.py"].get("new_name")
    assert [c.path for c in ai_cards(tmp_path)] == ["zz/c.py", "zz/plain.py"]


def test_create_without_a_name_is_refused_and_saves_nothing(
    db_path, published_rulebook, make_settings, tmp_path
):
    _seed(tmp_path)

    for name, senior in ((" ", "Ana"), ("Doc export", " ")):  # the rulebook needs a named senior
        result = create_and_assign(make_settings(), name, "d", senior, "", ["zz/a.py"], ADMIN, 1,
                                   tmp_path)
        assert result.kind == "refused"

    assert len(list_versions(db_path)) == 1
    assert len(suggestions(tmp_path)) == 1


def test_assign_to_an_existing_capability_and_reject(
    db_path, published_rulebook, make_settings, tmp_path
):
    _seed(tmp_path)
    paths = list(suggestions(tmp_path)[0].modules)

    result = assign_suggestion(make_settings(), "Uploads", paths, ADMIN, 1, tmp_path)

    assert result.kind == "resolved" and suggestions(tmp_path) == []
    _seed(tmp_path)
    reject_suggestion(paths, ADMIN, tmp_path)
    assert {read_tags(tmp_path)[p]["state"] for p in paths} == {"rejected"}


def test_g4_13_the_card_and_the_confirm_box_count_suggestions(tmp_path):
    _seed(tmp_path)
    queue = {"rows": [], "resolved": None, "dialog": None, "notice": [],
             "ai_cards": ai_cards(tmp_path), "suggestions": suggestions(tmp_path),
             "ai_confirm": {"counts": {"Uploads": 1}, "suggestions": 1}}

    text = str(queue_block(queue, ["Uploads"]))

    assert "New capability suggested" in text and "Create and assign" in text
    assert "1 new-capability suggestions wait for your review" in text
