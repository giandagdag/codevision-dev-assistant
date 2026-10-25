import sqlite3
from contextlib import closing
from datetime import UTC, datetime

import pytest

from db_table_functions import da_db, db_tbl_da_rulebook
from db_table_functions.da_db import DatabaseBusyError
from db_table_functions.db_tbl_da_requests import (
    create_request,
    get_rulebook_for_request,
    list_requests,
)
from db_table_functions.db_tbl_da_rulebook import (
    RulebookError,
    StaleSaveError,
    get_active_version,
    get_version,
    list_versions,
    load_rulebook_file,
    next_rule_id,
    publish_first_version,
    restore_version,
    save_new_version,
)
from pydantic_classes.da_rulebook_models import Rule, Rulebook

ADMIN = "admin-0001"
T1 = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)


def with_severity(rulebook: Rulebook, rule_id: str, severity: str) -> Rulebook:
    rules = [
        rule.model_copy(update={"severity": severity}) if rule.rule_id == rule_id else rule
        for rule in rulebook.rules
    ]
    return rulebook.model_copy(update={"rules": rules})


def with_extra_rule(rulebook: Rulebook, rule_id: str) -> Rulebook:
    new_rule = Rule(
        rule_id=rule_id,
        title="Made-up extra rule",
        kind="judgement",
        tags=["general"],
        severity="fyi",
        why="Example only.",
        good_example="good()",
        bad_example="bad()",
        source="Written by Admin",
    )
    return rulebook.model_copy(update={"rules": [*rulebook.rules, new_rule]})


def without_rule(rulebook: Rulebook, rule_id: str) -> Rulebook:
    rules = [rule for rule in rulebook.rules if rule.rule_id != rule_id]
    return rulebook.model_copy(update={"rules": rules})


def save_v2(db_path, seed_rulebook):
    changed = with_severity(seed_rulebook, "CV-PY-002", "must_fix")
    return save_new_version(db_path, changed, 1, ADMIN, "Make CV-PY-002 a must fix", now=T1)


# --- Publishing v1 ---


def test_publish_creates_v1(db_path, seed_rulebook):
    v1 = publish_first_version(db_path, seed_rulebook, ADMIN, "Starter rulebook", now=T1)

    assert v1.version_number == 1
    assert v1.saved_by == ADMIN
    assert v1.saved_at == T1
    assert v1.restored_from is None
    assert get_version(db_path, 1) == v1


def test_second_publish_is_refused(db_path, seed_rulebook, published_rulebook):
    with pytest.raises(RulebookError, match="already published .active version v1"):
        publish_first_version(db_path, seed_rulebook, ADMIN, "Again")


def test_publish_with_problems_writes_nothing(db_path, seed_rulebook):
    bad = seed_rulebook.model_copy(
        update={"policy": seed_rulebook.policy.model_copy(update={"max_review_rounds": 0})}
    )

    with pytest.raises(RulebookError, match="Max review rounds is 0"):
        publish_first_version(db_path, bad, ADMIN, "Starter rulebook")

    assert list_versions(db_path) == []


def test_save_before_publish_is_refused(db_path, seed_rulebook):
    with pytest.raises(RulebookError, match="No rulebook has been published yet"):
        save_new_version(db_path, seed_rulebook, 1, ADMIN, "Too early")


def test_active_version_on_empty_database_is_none(db_path):
    assert get_active_version(db_path) is None


def test_unknown_version_is_none(db_path, published_rulebook):
    assert get_version(db_path, 99) is None


# --- Saving and listing ---


def test_save_creates_the_next_version_and_it_becomes_active(
    db_path, seed_rulebook, published_rulebook
):
    v2 = save_v2(db_path, seed_rulebook)

    assert v2.version_number == 2
    assert get_active_version(db_path) == v2
    # v1 is untouched.
    assert get_version(db_path, 1).rulebook == seed_rulebook


def test_list_versions_is_newest_first(db_path, seed_rulebook, published_rulebook):
    save_v2(db_path, seed_rulebook)
    restore_version(db_path, 1, ADMIN)

    numbers = [version.version_number for version in list_versions(db_path)]

    assert numbers == [3, 2, 1]


# --- R1: versions cannot be edited or deleted ---


def test_module_offers_no_edit_or_delete_function():
    public_names = [name for name in dir(db_tbl_da_rulebook) if not name.startswith("_")]

    for word in ("update", "edit", "delete", "remove"):
        assert not any(word in name.lower() for name in public_names)


def test_database_refuses_to_edit_a_version(db_path, published_rulebook):
    # Go around our functions on purpose, as careless future code might.
    with closing(sqlite3.connect(db_path)) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="cannot be edited"):
            conn.execute("UPDATE da_rulebook_versions SET change_note = 'changed'")

    assert get_version(db_path, 1).change_note == "Starter rulebook"


def test_database_refuses_to_delete_a_version(db_path, published_rulebook):
    with closing(sqlite3.connect(db_path)) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
            conn.execute("DELETE FROM da_rulebook_versions")

    assert len(list_versions(db_path)) == 1


def test_saved_version_cannot_be_changed_in_memory(published_rulebook):
    with pytest.raises(ValueError):
        published_rulebook.change_note = "changed"


# --- R2: a change note is required ---


@pytest.mark.parametrize("note", ["", "   "])
def test_empty_change_note_is_refused(db_path, seed_rulebook, published_rulebook, note):
    changed = with_severity(seed_rulebook, "CV-PY-002", "must_fix")

    with pytest.raises(RulebookError, match="change note is empty"):
        save_new_version(db_path, changed, 1, ADMIN, note)

    assert len(list_versions(db_path)) == 1


def test_empty_change_note_is_refused_on_publish(db_path, seed_rulebook):
    with pytest.raises(RulebookError, match="change note is empty"):
        publish_first_version(db_path, seed_rulebook, ADMIN, " ")


def test_empty_saved_by_is_refused(db_path, seed_rulebook):
    with pytest.raises(RulebookError, match="Saved by is empty"):
        publish_first_version(db_path, seed_rulebook, "", "Starter rulebook")


# --- R3: a rulebook with problems is refused, with every problem listed ---


def test_save_with_several_problems_lists_them_all_and_writes_nothing(
    db_path, seed_rulebook, published_rulebook
):
    bad_policy = seed_rulebook.policy.model_copy(
        update={"default_level": "L3", "max_level": "L2", "max_review_rounds": 6}
    )
    bad = seed_rulebook.model_copy(
        update={"policy": bad_policy, "rules": [*seed_rulebook.rules, seed_rulebook.rules[0]]}
    )

    with pytest.raises(RulebookError) as refused:
        save_new_version(db_path, bad, 1, ADMIN, "Several mistakes")

    message = str(refused.value)
    assert message.startswith("The rulebook was not saved. Please fix these problems:")
    assert "higher than the max level" in message
    assert "locked for the pilot" in message
    assert "Max review rounds is 6" in message
    assert "CV-PY-001 is used by more than one rule" in message
    assert len(list_versions(db_path)) == 1


# --- R4: stale-save protection ---


def test_save_based_on_an_old_version_is_refused(db_path, seed_rulebook, published_rulebook):
    save_v2(db_path, seed_rulebook)
    # Another Admin, still looking at v1, tries to save.
    their_change = with_severity(seed_rulebook, "CV-PY-005", "should_fix")

    with pytest.raises(StaleSaveError, match="based on v1, but v2 is now the active version"):
        save_new_version(db_path, their_change, 1, ADMIN, "My change")

    assert len(list_versions(db_path)) == 2


def test_save_during_a_competing_save_gives_busy_message_and_writes_nothing(
    db_path, seed_rulebook, published_rulebook, monkeypatch
):
    monkeypatch.setattr(da_db, "BUSY_TIMEOUT_SECONDS", 0.1)
    changed = with_severity(seed_rulebook, "CV-PY-002", "must_fix")

    # A second Admin's save is half way through and holds the write lock.
    with closing(sqlite3.connect(db_path)) as other:
        other.execute("BEGIN IMMEDIATE")
        with pytest.raises(DatabaseBusyError, match="Try again in a moment"):
            save_new_version(db_path, changed, 1, ADMIN, "My change")
        other.rollback()

    assert len(list_versions(db_path)) == 1
    # Once the lock is free, the same save goes through.
    assert save_new_version(db_path, changed, 1, ADMIN, "My change").version_number == 2


# --- R5: nothing changed ---


def test_identical_rulebook_is_refused(db_path, seed_rulebook, published_rulebook):
    with pytest.raises(RulebookError, match="No changes to save"):
        save_new_version(db_path, seed_rulebook, 1, ADMIN, "Nothing really")

    assert len(list_versions(db_path)) == 1


# --- R6 and restore ---


def test_restore_copies_an_old_version_into_a_new_one(db_path, seed_rulebook, published_rulebook):
    save_v2(db_path, seed_rulebook)

    v3 = restore_version(db_path, 1, ADMIN, now=T1)

    assert v3.version_number == 3
    assert v3.restored_from == 1
    assert v3.change_note == "Restored from v1"
    assert v3.rulebook == seed_rulebook
    # Nothing is lost: v2 is still there, unchanged.
    assert get_version(db_path, 2).rulebook == with_severity(seed_rulebook, "CV-PY-002", "must_fix")


def test_restore_keeps_a_given_note(db_path, seed_rulebook, published_rulebook):
    save_v2(db_path, seed_rulebook)

    v3 = restore_version(db_path, 1, ADMIN, note="Back to the starter rules")

    assert v3.change_note == "Back to the starter rules"


def test_restoring_the_active_version_is_refused(db_path, seed_rulebook, published_rulebook):
    save_v2(db_path, seed_rulebook)

    with pytest.raises(RulebookError, match="v2 is already the active version"):
        restore_version(db_path, 2, ADMIN)

    assert len(list_versions(db_path)) == 2


def test_restoring_a_copy_of_the_active_content_is_refused(
    db_path, seed_rulebook, published_rulebook
):
    save_v2(db_path, seed_rulebook)
    restore_version(db_path, 1, ADMIN)  # v3 is now a copy of v1

    with pytest.raises(RulebookError, match="No changes to save"):
        restore_version(db_path, 1, ADMIN)


def test_restoring_an_unknown_version_is_refused(db_path, published_rulebook):
    with pytest.raises(RulebookError, match="v9 does not exist. The newest version is v1"):
        restore_version(db_path, 9, ADMIN)


# --- R7 and addition A: rule IDs ---


def test_first_new_judgement_id_after_the_seed_is_006(db_path, published_rulebook):
    assert next_rule_id(db_path, "judgement") == "CV-PY-006"


def test_deleted_rule_number_is_never_reused(db_path, seed_rulebook, published_rulebook):
    new_id = next_rule_id(db_path, "judgement")
    assert new_id == "CV-PY-006"
    v2 = save_new_version(db_path, with_extra_rule(seed_rulebook, new_id), 1, ADMIN, "Add 006")
    save_new_version(db_path, without_rule(v2.rulebook, new_id), 2, ADMIN, "Remove 006")

    assert next_rule_id(db_path, "judgement") == "CV-PY-007"


def test_ui_and_judgement_counters_are_separate(db_path, published_rulebook):
    assert next_rule_id(db_path, "judgement") == "CV-PY-006"
    assert next_rule_id(db_path, "ui_convention") == "CV-UI-003"
    assert next_rule_id(db_path, "judgement") == "CV-PY-007"


def test_unknown_rule_kind_is_refused(db_path):
    with pytest.raises(RulebookError, match="Rule kind 'style' is not allowed"):
        next_rule_id(db_path, "style")


def test_id_not_handed_out_is_refused(db_path, seed_rulebook, published_rulebook):
    next_rule_id(db_path, "judgement")  # counter is now at 6

    with pytest.raises(RulebookError, match="CV-PY-009 has not been handed out yet"):
        save_new_version(
            db_path, with_extra_rule(seed_rulebook, "CV-PY-009"), 1, ADMIN, "Typed by hand"
        )

    assert len(list_versions(db_path)) == 1


def test_id_not_handed_out_message_says_how_to_fix(db_path, seed_rulebook, published_rulebook):
    with pytest.raises(RulebookError, match="Use next_rule_id to get a new rule ID"):
        save_new_version(
            db_path, with_extra_rule(seed_rulebook, "CV-PY-006"), 1, ADMIN, "Typed by hand"
        )


def test_id_already_handed_out_is_accepted(db_path, seed_rulebook, published_rulebook):
    next_rule_id(db_path, "judgement")  # hands out 006

    v2 = save_new_version(
        db_path, with_extra_rule(seed_rulebook, "CV-PY-006"), 1, ADMIN, "Add 006"
    )

    assert v2.version_number == 2


def test_seed_ids_set_the_counter_even_after_earlier_hand_outs(db_path, seed_rulebook):
    # Two numbers handed out before v1: the seed's own IDs (up to 005) still win.
    next_rule_id(db_path, "judgement")
    next_rule_id(db_path, "judgement")
    publish_first_version(db_path, seed_rulebook, ADMIN, "Starter rulebook")

    assert next_rule_id(db_path, "judgement") == "CV-PY-006"


# --- Pinning ---


def test_request_is_pinned_to_the_active_version(db_path, published_rulebook):
    request = create_request(db_path, "Change A", "dev-0001", now=T1)

    assert request.rulebook_version == 1
    assert get_rulebook_for_request(db_path, request.request_id).version_number == 1


def test_pinned_request_still_gets_v1_after_v2_and_v3(db_path, seed_rulebook, published_rulebook):
    request = create_request(db_path, "Change A", "dev-0001", now=T1)
    save_v2(db_path, seed_rulebook)
    restore_version(db_path, 1, ADMIN)

    pinned = get_rulebook_for_request(db_path, request.request_id)

    assert pinned.version_number == 1
    assert pinned == published_rulebook


def test_new_request_after_a_save_is_pinned_to_the_new_version(
    db_path, seed_rulebook, published_rulebook
):
    save_v2(db_path, seed_rulebook)

    request = create_request(db_path, "Change B", "dev-0001", now=T1)

    assert request.rulebook_version == 2


def test_request_without_a_rulebook_is_refused_and_nothing_is_saved(db_path):
    with pytest.raises(RulebookError, match="No rulebook has been published yet"):
        create_request(db_path, "Change A", "dev-0001", now=T1)

    assert list_requests(db_path) == []


def test_rulebook_for_unknown_request_gives_plain_message(db_path, published_rulebook):
    with pytest.raises(RulebookError, match="CVDA-2026-9999 does not exist"):
        get_rulebook_for_request(db_path, "CVDA-2026-9999")


# --- Loading a rulebook file ---


def test_missing_rulebook_file_gives_plain_message(tmp_path):
    with pytest.raises(RulebookError, match="was not found"):
        load_rulebook_file(tmp_path / "missing.json")


def test_broken_json_gives_plain_message(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ not json", encoding="utf-8")

    with pytest.raises(RulebookError, match="is not valid JSON"):
        load_rulebook_file(path)


def test_wrong_shape_names_the_field(tmp_path):
    path = tmp_path / "wrong.json"
    path.write_text('{"charter": {}, "rules": [], "policy": {}}', encoding="utf-8")

    with pytest.raises(RulebookError, match="charter.purpose"):
        load_rulebook_file(path)
