"""Phase 11b step 2: UI and Coding standards forms, the Add row helper, Cited counts."""

import pytest

from agents.da_admin_cited import cited_counts
from agents.da_admin_forms import (
    RESULT_PROBLEMS,
    RESULT_SAVED,
    RESULT_UNCHANGED,
    add_rule_row,
    library_overlap_problems,
    rule_counter_text,
    rulebook_from_form,
    save_from_form,
)
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_rulebook import get_active_version, list_versions

ADMIN = "admin-0001"


def rule_rows(rulebook, kind):
    """The form rows that repeat the current rules of one kind (so they change nothing)."""
    return [
        {
            "rule_id": r.rule_id,
            "title": r.title,
            "tags": "\n".join(r.tags),
            "severity": r.severity,
            "why": r.why,
            "good_example": r.good_example,
            "bad_example": r.bad_example,
            "source": r.source,
        }
        for r in rulebook.rules
        if r.kind == kind
    ]


def new_row(rule_id, **changes):
    row = {
        "rule_id": rule_id,
        "title": "Name things plainly",
        "tags": "general",
        "severity": "fyi",
        "why": "Plain names are read faster.",
        "good_example": "loan_total",
        "bad_example": "lt",
        "source": "Written by Admin",
    }
    return row | changes


def coding_form(rulebook):
    policy = rulebook.policy
    return {
        "rules": rule_rows(rulebook, "judgement"),
        "approved_libraries": list(policy.approved_libraries),
        "blocked_imports": list(policy.build_blocked_imports),
        "sonar_map": dict(policy.sonar_severity_map),
        "golden_examples": [g.model_dump() for g in rulebook.golden_examples],
    }


def test_an_unchanged_coding_form_says_no_changes(db_path, published_rulebook):
    form = coding_form(published_rulebook.rulebook)

    result = save_from_form(db_path, "coding", form, 1, ADMIN, "Nothing")

    assert result.kind == RESULT_UNCHANGED


def test_an_unchanged_ui_form_says_no_changes(db_path, published_rulebook):
    form = {"rules": rule_rows(published_rulebook.rulebook, "ui_convention")}

    assert save_from_form(db_path, "ui", form, 1, ADMIN, "Nothing").kind == RESULT_UNCHANGED


def test_add_row_hands_out_the_next_id_and_cancel_still_uses_it_up(db_path, published_rulebook):
    first = add_rule_row(db_path, "judgement", 5)
    # The Admin pressed Cancel here: no save. The next Add row gets the following number.
    second = add_rule_row(db_path, "judgement", 5)

    assert first.rule_id != second.rule_id
    assert int(second.rule_id[-3:]) == int(first.rule_id[-3:]) + 1
    assert first.rule_id.startswith("CV-PY-")
    assert add_rule_row(db_path, "ui_convention", 1).rule_id.startswith("CV-UI-")


def test_add_row_at_ten_judgement_rules_adds_nothing(db_path, published_rulebook):
    before = add_rule_row(db_path, "judgement", 3).rule_id

    result = add_rule_row(db_path, "judgement", 10)
    after = add_rule_row(db_path, "judgement", 3).rule_id

    assert result.rule_id == "" and "10 judgement rules" in result.message
    # No ID was used up by the refused press.
    assert int(after[-3:]) == int(before[-3:]) + 1


def test_counter_text():
    assert rule_counter_text("judgement", 7) == "7 of 10"
    assert rule_counter_text("ui_convention", 4) == "4"


def test_a_new_rule_is_saved_with_its_id(db_path, published_rulebook):
    rule_id = add_rule_row(db_path, "judgement", 5).rule_id
    form = coding_form(published_rulebook.rulebook)
    form["rules"].append(new_row(rule_id))

    result = save_from_form(db_path, "coding", form, 1, ADMIN, "Add a naming rule")

    assert result.kind == RESULT_SAVED
    saved = get_active_version(db_path).rulebook
    assert rule_id in [r.rule_id for r in saved.rules]
    assert [r.kind for r in saved.rules if r.rule_id == rule_id] == ["judgement"]


def test_an_untouched_new_row_is_dropped(db_path, published_rulebook):
    rule_id = add_rule_row(db_path, "judgement", 5).rule_id
    form = coding_form(published_rulebook.rulebook)
    form["rules"].append({"rule_id": rule_id, "tags": "", "severity": "fyi"})

    assert save_from_form(db_path, "coding", form, 1, ADMIN, "x").kind == RESULT_UNCHANGED


def test_a_typed_row_without_an_id_is_refused(published_rulebook):
    form = coding_form(published_rulebook.rulebook)
    form["rules"].append(new_row(""))

    with pytest.raises(ValueError, match="no rule ID"):
        rulebook_from_form(published_rulebook.rulebook, "coding", form)


def test_the_other_kinds_rules_are_kept_untouched(db_path, published_rulebook):
    before = published_rulebook.rulebook
    form = coding_form(before)
    form["rules"][0]["title"] = "A new title"

    save_from_form(db_path, "coding", form, 1, ADMIN, "Retitle")

    after = get_active_version(db_path).rulebook
    assert [r for r in after.rules if r.kind == "ui_convention"] == [
        r for r in before.rules if r.kind == "ui_convention"
    ]
    assert after.rules[0].title == "A new title"


def test_the_ui_tab_leaves_judgement_rules_alone(db_path, published_rulebook):
    before = published_rulebook.rulebook
    form = {"rules": rule_rows(before, "ui_convention")}
    form["rules"][0]["title"] = "Another UI title"

    save_from_form(db_path, "ui", form, 1, ADMIN, "Retitle UI")

    after = get_active_version(db_path).rulebook
    assert [r for r in after.rules if r.kind == "judgement"] == [
        r for r in before.rules if r.kind == "judgement"
    ]


def test_a_major_check_can_be_set_to_fyi(db_path, published_rulebook):
    form = coding_form(published_rulebook.rulebook)
    form["sonar_map"]["MAJOR"] = "fyi"

    result = save_from_form(db_path, "coding", form, 1, ADMIN, "Soften MAJOR")

    assert result.kind == RESULT_SAVED
    assert get_active_version(db_path).rulebook.policy.sonar_severity_map["MAJOR"] == "fyi"


def test_a_wrong_sonar_key_is_reported_in_plain_words(db_path, published_rulebook):
    form = coding_form(published_rulebook.rulebook)
    form["sonar_map"] = {**form["sonar_map"], "HUGE": "fyi"}

    result = save_from_form(db_path, "coding", form, 1, ADMIN, "Bad key")

    assert result.kind == RESULT_PROBLEMS
    assert any("HUGE" in p for p in result.problems)


def test_a_library_on_both_lists_is_refused_naming_it(db_path, published_rulebook):
    form = coding_form(published_rulebook.rulebook)
    form["approved_libraries"].append("requests")

    result = save_from_form(db_path, "coding", form, 1, ADMIN, "Allow requests")

    assert result.kind == RESULT_PROBLEMS
    assert any("'requests'" in p for p in result.problems)
    assert len(list_versions(db_path)) == 1


def test_the_overlap_check_ignores_case_and_dash_spelling(published_rulebook):
    policy = published_rulebook.rulebook.policy.model_copy(
        update={"approved_libraries": ["Dash-Core"], "build_blocked_imports": ["dash_core"]}
    )

    assert len(library_overlap_problems(policy)) == 1


def test_a_build_save_still_works_when_the_version_has_the_overlap(db_path, published_rulebook):
    # An older database may hold a version with the overlap; other tabs must not be locked by it.
    policy = published_rulebook.rulebook.policy
    overlap = {"approved_libraries": [*policy.approved_libraries, "requests"]}
    form = coding_form(published_rulebook.rulebook)
    form["approved_libraries"] = overlap["approved_libraries"]
    rulebook = published_rulebook.rulebook.model_copy(
        update={"policy": policy.model_copy(update=overlap)}
    )
    from db_table_functions.db_tbl_da_rulebook import save_new_version

    save_new_version(db_path, rulebook, 1, ADMIN, "Overlap kept for the test")

    build_form = {"build_max_rounds": "4"}
    result = save_from_form(db_path, "build", build_form, 2, ADMIN, "More rounds")
    assert result.kind == RESULT_SAVED


def test_a_golden_example_is_stored_in_the_new_version(db_path, published_rulebook):
    form = coding_form(published_rulebook.rulebook)
    form["golden_examples"].append(
        {"title": "Plain error", "tags": "general", "code": "raise ConfigError('x')", "why": ""}
    )

    result = save_from_form(db_path, "coding", form, 1, ADMIN, "Add golden example")

    assert result.kind == RESULT_SAVED
    titles = [g.title for g in get_active_version(db_path).rulebook.golden_examples]
    assert "Plain error" in titles


def test_two_golden_examples_with_one_title_are_refused(db_path, published_rulebook):
    form = coding_form(published_rulebook.rulebook)
    one = {"title": "Same", "tags": "", "code": "x = 1", "why": ""}
    form["golden_examples"] = [one, {**one, "title": "same"}]

    result = save_from_form(db_path, "coding", form, 1, ADMIN, "Dup")

    assert result.kind == RESULT_PROBLEMS and any("more than once" in p for p in result.problems)


def test_an_empty_golden_example_row_is_dropped(published_rulebook):
    form = coding_form(published_rulebook.rulebook)
    form["golden_examples"].append({"title": "", "tags": "", "code": "", "why": ""})

    edited = rulebook_from_form(published_rulebook.rulebook, "coding", form)

    assert edited.golden_examples == published_rulebook.rulebook.golden_examples


def test_the_whole_problem_list_comes_back_at_once(db_path, published_rulebook):
    form = coding_form(published_rulebook.rulebook)
    form["approved_libraries"].append("requests")
    form["sonar_map"] = {k: v for k, v in form["sonar_map"].items() if k != "INFO"}

    result = save_from_form(db_path, "coding", form, 1, ADMIN, "Two problems")

    assert len(result.problems) >= 2


def test_cited_counts_only_kept_findings(db_path, published_rulebook):
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        conn.execute("PRAGMA foreign_keys = OFF")
        for cites, kept in [("CV-PY-001", 1), ("CV-PY-001", 1), ("CV-PY-002", 0), ("", 1)]:
            conn.execute(
                "INSERT INTO da_tester_findings (request_id, build_number, review_number,"
                " finding_id, check_number, severity, file, line, quote, cites, message, made_by,"
                " kept, reject_reason, fixable, created_at)"
                " VALUES ('CVDA-2026-0001', 1, 1, 'F1', 1, 'fyi', 'a.py', 1, 'q', ?, 'm', 'tester',"
                " ?, '', 0, '2026-11-01T09:00:00+00:00')",
                (cites, kept),
            )

    assert cited_counts(db_path) == {"CV-PY-001": 2}


def test_cited_counts_on_an_empty_database_is_empty(db_path, published_rulebook):
    assert cited_counts(db_path) == {}
