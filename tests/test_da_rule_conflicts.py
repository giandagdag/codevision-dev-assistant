"""Fix G9 step 1: plain-code rule conflicts and the keep-only-real filter (U3, U4)."""

import pytest

from agents.da_rule_conflicts import RuleConflict, keep_real_conflicts, plain_conflicts
from db_table_functions.db_tbl_da_rulebook import SEED_RULEBOOK_FILE, load_rulebook_file
from pydantic_classes.da_request_record_models import AcceptanceCriterion, Decision, RequestRecord


@pytest.fixture
def rulebook():
    return load_rulebook_file(SEED_RULEBOOK_FILE)


def _record(then="The text is shown", **changes) -> RequestRecord:
    criterion = AcceptanceCriterion(
        id="AC-1", kind="success", given="A user opens the page", when="They press go", then=then
    )
    base = {
        "request_id": "CVDA-2026-0001",
        "rulebook_version": 1,
        "acceptance_criteria": [criterion],
    }
    return RequestRecord(**(base | changes))


def test_blocked_import_is_a_conflict_without_any_ai(rulebook):
    """G9-4: a criterion that names a blocked import."""
    record = _record(then="The result is sent with the subprocess module to a shell")

    found = plain_conflicts(record, rulebook)

    assert [(c.criterion, c.rule) for c in found] == [("AC-1", "LIB:subprocess")]


def test_library_off_the_approved_list_is_a_conflict(rulebook):
    record = _record(then="The page is fetched with the requests library and shown")

    found = plain_conflicts(record, rulebook)

    assert [c.rule for c in found] == ["LIB:requests"]


def test_approved_library_and_plain_text_pass(rulebook):
    record = _record(then="The values are checked with the pydantic library and shown")

    assert plain_conflicts(record, rulebook) == []


def test_everyday_bank_wording_is_not_a_library(rulebook):
    """Review round 2: everyday words like 'requests' or 'csv module' are not libraries."""
    text = "A user requests the HTTP report page; the report module reads it with the csv module"

    assert plain_conflicts(_record(then=text), rulebook) == []


def test_import_as_a_verb_and_package_are_ordinary_words(rulebook):
    """Finish review 1, Must 1."""
    text = "The clerk can import daily rates from the loan package screen"

    assert plain_conflicts(_record(then=text), rulebook) == []


def test_import_written_like_code_is_still_checked(rulebook):
    found = plain_conflicts(_record(then="Load it with `import numpy` first"), rulebook)

    assert [c.rule for c in found] == ["LIB:numpy"]


def test_ai_cite_of_an_approved_library_or_a_long_rule_is_dropped(rulebook):
    """Finish review 1, Must 2."""
    conflicts = [
        RuleConflict("AC-1", "LIB:pydantic", "why", "fix"),
        RuleConflict("AC-1", "LIB:" + "x" * 500, "why", "fix"),
        RuleConflict("AC-1", "LIB:requests", "why", "fix"),
    ]

    kept = keep_real_conflicts(conflicts, _record(), rulebook)

    assert [c.rule for c in kept] == ["LIB:requests"]


def test_plain_conflicts_carry_no_wording_to_paste(rulebook):
    record = _record(then="The result is sent with the subprocess module to a shell")

    assert [c.fix for c in plain_conflicts(record, rulebook)] == [""]


def test_out_of_scope_matches_ignoring_case_and_word_order(rulebook):
    record = _record(then="Access control, login and PASSWORDS are all changed")

    rules = [c.rule for c in plain_conflicts(record, rulebook)]

    assert "CHARTER:out_of_scope:1" in rules


def test_a_decision_is_checked_too(rulebook):
    decision = Decision(
        question="How to call it?",
        choice="Use the socket module",
        decided_at="2026-11-26T09:00:00+00:00",
    )

    found = plain_conflicts(_record(decisions=[decision]), rulebook)

    assert [(c.criterion, c.rule) for c in found] == [("DD-1", "LIB:socket")]


def test_unknown_rule_and_unknown_place_are_dropped(rulebook):
    """G9-5: a conflict citing a rule that does not exist is dropped; so is a missing place."""
    record = _record()
    real = RuleConflict("AC-1", "CV-PY-001", "why", "fix")
    conflicts = [
        real,
        RuleConflict("AC-1", "CV-PY-999", "why", "fix"),
        RuleConflict("AC-9", "CV-PY-001", "why", "fix"),
        RuleConflict("DD-1", "CV-PY-001", "why", "fix"),
        RuleConflict("SUMMARY", "CHARTER:out_of_scope:99", "why", "fix"),
        RuleConflict("SUMMARY", "ZONE:nothing", "why", "fix"),
    ]

    assert keep_real_conflicts(conflicts, record, rulebook) == [real]


def test_f6_a_destructive_request_shows_each_missing_item_as_a_zone_conflict(rulebook):
    from agents.da_destructive import DESTRUCTIVE_ZONE, missing_questions

    record = _record(destructive=True)

    zone = [c for c in plain_conflicts(record, rulebook) if c.rule.startswith("ZONE:")]

    assert [c.rule for c in zone] == [f"ZONE:{DESTRUCTIVE_ZONE}"] * len(missing_questions(record))
    assert zone and all(c.criterion == "SUMMARY" and c.fix == "" for c in zone)


def test_f6_an_ordinary_request_has_no_zone_conflict(rulebook):
    assert not [c for c in plain_conflicts(_record(), rulebook) if c.rule.startswith("ZONE:")]


def test_f6_the_zone_conflict_has_change_and_exception_buttons():
    from agents.da_refine_rules import rule_buttons
    from pydantic_classes.da_refine_models import RefineState

    conflict = RuleConflict("SUMMARY", "ZONE:Destructive data change", "why", "")
    state = RefineState(
        request_id="CVDA-2026-0001", pending_record=_record(), check_conflicts=[conflict]
    )

    assert [key for key, _ in rule_buttons(state)] == ["rc:change:1", "rc:ask:1"]


def test_kept_conflict_texts_are_cut_to_200(rulebook):
    long = "x" * 500

    kept = keep_real_conflicts([RuleConflict("AC-1", "CV-PY-001", long, long)], _record(), rulebook)

    assert len(kept[0].why) == len(kept[0].fix) == 200
