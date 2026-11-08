"""Phase 8 plain rules, record side (tests 8-10, 8-12 rule side, 8-13, 8-14)."""

from agents.da_refine_checks import (
    NO_CRITERION_REASON,
    apply_revision,
    cap_message,
    check_lane_suggestion,
    criterion_marks,
    diff_records,
    next_criterion_number,
    refine_cap_reached,
)
from pydantic_classes.da_refine_models import CriterionOp, LaneSuggestion, RevisionReply
from pydantic_classes.da_request_record_models import AcceptanceCriterion, RequestRecord

RID = "CVDA-2026-0001"


def criterion(number: int, then: str = "a message says the file was saved") -> AcceptanceCriterion:
    return AcceptanceCriterion(
        id=f"AC-{number}",
        kind="success",
        given=f"given number {number}",
        when=f"when number {number}",
        then=then,
    )


def record(version: int = 1, count: int = 5) -> RequestRecord:
    return RequestRecord(
        request_id=RID,
        version=version,
        rulebook_version=1,
        title="Upload",
        objective="Accept uploads",
        acceptance_criteria=[criterion(n) for n in range(1, count + 1)],
    )


def test_8_13_add_one_and_change_one_leaves_the_rest_byte_for_byte_the_same():
    v1 = record()
    reply = RevisionReply(
        criteria_ops=[
            CriterionOp(
                op="add",
                kind="failure",
                given="a file over 5 MB",
                when="the user uploads it",
                then="a message says the file is too big",
            ),
            CriterionOp(op="change", id="AC-2", then="a message says the file was rejected"),
        ]
    )

    v2, problems = apply_revision(v1, reply, [v1])

    assert problems == []
    assert v2.version == 2
    assert [c.id for c in v2.acceptance_criteria] == [
        "AC-1",
        "AC-2",
        "AC-3",
        "AC-4",
        "AC-5",
        "AC-6",
    ]
    assert v2.acceptance_criteria[1].then == "a message says the file was rejected"
    assert v2.acceptance_criteria[1].given == v1.acceptance_criteria[1].given
    for index in (0, 2, 3, 4):
        assert v2.acceptance_criteria[index] == v1.acceptance_criteria[index]
    assert v1.version == 1  # the old record is never touched
    assert v1.acceptance_criteria[1].then == "a message says the file was saved"


def test_8_13_the_diff_shows_the_added_and_the_changed_criterion():
    v1 = record()
    reply = RevisionReply(
        criteria_ops=[
            CriterionOp(
                op="add",
                kind="failure",
                given="g new",
                when="w new",
                then="a message shows an error",
            ),
            CriterionOp(op="change", id="AC-2", then="a message says the file was rejected"),
        ],
        field_updates={"objective": "Accept uploads under 5 MB"},
    )
    v2, _ = apply_revision(v1, reply, [v1])

    diff = diff_records(v1, v2)

    assert (diff.from_version, diff.to_version) == (1, 2)
    assert [f.field for f in diff.fields] == ["objective"]
    kinds = {c.id: c.change for c in diff.criteria}
    assert kinds == {"AC-6": "added", "AC-2": "changed"}
    changed = next(c for c in diff.criteria if c.id == "AC-2")
    assert changed.old["then"] != changed.new["then"]


def test_8_14_an_id_removed_in_v2_is_never_given_out_again_in_v3():
    v1 = record(count=6)
    v2, _ = apply_revision(
        v1, RevisionReply(criteria_ops=[CriterionOp(op="remove", id="AC-6")]), [v1]
    )
    assert [c.id for c in v2.acceptance_criteria] == ["AC-1", "AC-2", "AC-3", "AC-4", "AC-5"]

    add = RevisionReply(
        criteria_ops=[
            CriterionOp(
                op="add", kind="success", given="g", when="w", then="a message shows a total"
            )
        ]
    )
    v3, problems = apply_revision(v2, add, [v1, v2])

    assert problems == []
    assert v3.acceptance_criteria[-1].id == "AC-7"
    assert next_criterion_number([v1, v2]) == 7


def test_the_removed_criterion_shows_as_removed_in_the_diff():
    v1 = record()
    v2, _ = apply_revision(
        v1, RevisionReply(criteria_ops=[CriterionOp(op="remove", id="AC-3")]), [v1]
    )

    diff = diff_records(v1, v2)

    assert [(c.id, c.change) for c in diff.criteria] == [("AC-3", "removed")]
    assert criterion_marks([diff]) == {"AC-3": ["removed in v2"]}


def test_changing_or_removing_an_unknown_criterion_is_refused_in_plain_words():
    v1 = record()
    reply = RevisionReply(criteria_ops=[CriterionOp(op="change", id="AC-9", then="x y z")])

    v2, problems = apply_revision(v1, reply, [v1])

    assert v2 is None
    assert "AC-9" in problems[0]


def test_a_vague_then_a_repeat_and_the_limit_of_12_are_refused():
    v1 = record(count=12)
    too_many = RevisionReply(
        criteria_ops=[
            CriterionOp(op="add", kind="success", given="g", when="w", then="a message shows it")
        ]
    )
    assert "limit is 12" in apply_revision(v1, too_many, [v1])[1][0]

    v1 = record()
    vague = RevisionReply(criteria_ops=[CriterionOp(op="change", id="AC-1", then="it works")])
    assert "can see" in apply_revision(v1, vague, [v1])[1][0]

    same = RevisionReply(
        criteria_ops=[
            CriterionOp(
                op="add",
                kind="success",
                given="given number 1",
                when="when number 1",
                then="a message says the file was saved",
            )
        ]
    )
    assert "repeats AC-1" in apply_revision(v1, same, [v1])[1][0]


def test_a_field_update_may_only_name_a_record_field_with_the_right_type():
    v1 = record()
    reply = RevisionReply(field_updates={"decisions": "x", "in_scope": "not a list"})

    v2, problems = apply_revision(v1, reply, [v1])

    assert v2 is None
    assert len(problems) == 2


def test_an_add_without_all_parts_is_refused():
    v1 = record()
    reply = RevisionReply(criteria_ops=[CriterionOp(op="add", kind="success", given="g")])

    v2, problems = apply_revision(v1, reply, [v1])

    assert v2 is None
    assert "needs a kind" in problems[0]


# --- the lane suggestion ---


def test_8_10_a_bug_with_no_criterion_becomes_a_requirement_suggestion():
    suggestion = LaneSuggestion(lane="bug", reason="It crashes on big files.")

    checked, why = check_lane_suggestion(suggestion, record())

    assert why == ""
    assert checked.lane == "requirement"
    assert checked.reason == NO_CRITERION_REASON


def test_a_bug_naming_an_unknown_criterion_is_unusable():
    suggestion = LaneSuggestion(lane="bug", reason="It breaks AC-9.", criterion_id="AC-9")

    checked, why = check_lane_suggestion(suggestion, record())

    assert checked is None
    assert "AC-9" in why


def test_a_good_bug_suggestion_is_kept_and_an_empty_reason_is_unusable():
    good = LaneSuggestion(lane="bug", reason="  It breaks AC-2.  ", criterion_id="AC-2")
    assert check_lane_suggestion(good, record())[0].reason == "It breaks AC-2."

    empty = LaneSuggestion(lane="approach", reason="   ")
    assert check_lane_suggestion(empty, record())[0] is None


def test_8_12_the_refine_cap_is_reached_at_the_limit():
    assert not refine_cap_reached(4, 5)
    assert refine_cap_reached(5, 5)
    assert cap_message(5) == (
        "This request has been refined 5 times. Get help, or hand off what you have."
    )
