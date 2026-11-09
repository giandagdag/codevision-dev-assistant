import pytest
from pydantic import ValidationError

from pydantic_classes.da_refine_models import (
    CriterionOp,
    LaneSuggestion,
    RecordDiff,
    RefineRow,
    RefineState,
    RevisionReply,
)


def test_a_lane_suggestion_needs_a_known_lane():
    LaneSuggestion(lane="bug", reason="It breaks AC-2.", criterion_id="AC-2")

    with pytest.raises(ValidationError):
        LaneSuggestion(lane="rewrite", reason="x")


def test_a_lane_reason_is_limited_to_300_characters():
    with pytest.raises(ValidationError):
        LaneSuggestion(lane="bug", reason="x" * 301)


def test_a_criterion_id_must_look_like_ac_n():
    with pytest.raises(ValidationError):
        LaneSuggestion(lane="bug", reason="x", criterion_id="T-1")


def test_a_revision_reply_names_changes_only():
    reply = RevisionReply(
        criteria_ops=[
            CriterionOp(op="add", kind="failure", given="g", when="w", then="t"),
            CriterionOp(op="remove", id="AC-3"),
        ],
        field_updates={"objective": "New objective"},
    )

    assert [op.op for op in reply.criteria_ops] == ["add", "remove"]


def test_a_revision_reply_refuses_unknown_keys():
    with pytest.raises(ValidationError):
        RevisionReply.model_validate({"criteria_ops": [], "rewrite_all": True})


def test_an_empty_diff_is_empty():
    assert RecordDiff(from_version=1, to_version=2).empty


def test_new_refine_rows_start_blank():
    state = RefineState(request_id="CVDA-2026-0001")
    row = RefineRow(request_id="CVDA-2026-0001", refine_number=1)

    assert state.refine_count == 0
    assert state.last_tested_kind == ""
    assert row.repro_passed_today == 0
