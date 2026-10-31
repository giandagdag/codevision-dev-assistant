import pytest
from pydantic import ValidationError

from pydantic_classes.da_approach_models import (
    ApproachReply,
    DesignChoice,
    PlannedFile,
    TestCaseReply,
    TestPlanReply,
)


def plan(**changes):
    values = {"summary": "Add Excel support", "files": []}
    values.update(changes)
    return values


def file_entry(**changes):
    values = {"path": "src/agents/excel_processor.py", "action": "create", "purpose": "Read sheets"}
    values.update(changes)
    return values


def test_a_minimal_reply_is_valid():
    reply = ApproachReply.model_validate(plan())

    assert reply.files == [] and reply.design_choices == []


@pytest.mark.parametrize(
    "changes",
    [
        {"summary": ""},
        {"summary": "x" * 301},
        {"files": [file_entry()] * 13},
        {"files": [file_entry(path="x" * 201)]},
        {"files": [file_entry(action="delete")]},
        {"files": [file_entry(reuses=[1, 2, 3, 4])]},
        {"needs_people": [{"path": "p", "reason": "r"}] * 6},
        {"reuse_decisions": [{"hit_id": 1, "decision": "copy", "reason": "r"}]},
        {"libraries": ["x" * 51]},
        {"libraries": ["a"] * 13},
        {"unknown_field": 1},
    ],
)
def test_limits_are_refused_never_cut(changes):
    with pytest.raises(ValidationError):
        ApproachReply.model_validate(plan(**changes))


def test_design_choice_needs_two_or_three_options():
    base = {"question": "Where?", "impact": "Changes the screen"}

    with pytest.raises(ValidationError):
        DesignChoice.model_validate(base | {"options": ["only one"]})
    with pytest.raises(ValidationError):
        DesignChoice.model_validate(base | {"options": ["a", "b", "c", "d"]})
    assert DesignChoice.model_validate(base | {"options": ["a", "b"]})


def test_planned_file_unknown_field_is_refused():
    with pytest.raises(ValidationError):
        PlannedFile.model_validate(file_entry(recommended=True))


def test_test_plan_reply_limits():
    case = {"criterion_id": "AC-1", "given": "g", "expect": "e"}

    assert TestPlanReply.model_validate({"cases": [case]})
    for bad in ([], [case] * 31, [case | {"criterion_id": "1"}], [case | {"given": "x" * 301}]):
        with pytest.raises(ValidationError):
            TestPlanReply.model_validate({"cases": bad})
    assert TestCaseReply.model_validate(case).criterion_id == "AC-1"
