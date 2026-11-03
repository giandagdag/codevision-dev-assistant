import pytest
from pydantic import ValidationError

from pydantic_classes.da_build_models import (
    BuildState,
    CodeReply,
    Contract,
    ContractFile,
    ContractItem,
    FileEdit,
    LayerAProblem,
    LayerAResult,
    LayerBResult,
    TestOutcome,
)

REQUEST_ID = "CVDA-2026-0001"


def outcome(result, name="test_t1_ac1_x"):
    return TestOutcome(name=name, result=result)


def test_a_new_build_state_starts_with_no_build_and_nothing_written():
    state = BuildState(request_id=REQUEST_ID)

    assert (state.step, state.build_number, state.write_state) == ("start", 0, "not_written")
    assert state.revision == 1


@pytest.mark.parametrize(
    "changes",
    [{"step": "b_prescan"}, {"write_state": "half"}, {"build_number": -1}, {"extra": 1}],
)
def test_a_build_state_with_a_wrong_value_is_refused(changes):
    with pytest.raises(ValidationError):
        BuildState(request_id=REQUEST_ID, **changes)


def test_contract_needs_at_least_one_file_and_valid_kinds():
    item = ContractItem(name="validate", kind="function", args=["path"], summary="Checks a file")

    assert Contract(files=[ContractFile(path="src/a.py", items=[item])]).files[0].items == [item]
    with pytest.raises(ValidationError):
        Contract(files=[])
    with pytest.raises(ValidationError):
        ContractItem(name="x", kind="module", summary="s")


def test_code_reply_holds_text_or_edits():
    assert CodeReply(text="x = 1\n").edits is None
    assert CodeReply(edits=[FileEdit(find="a", replace="b")]).text is None
    with pytest.raises(ValidationError):
        FileEdit(find="", replace="b")


def test_layer_a_is_ok_only_without_problems():
    assert LayerAResult().ok
    bad = LayerAResult(problems=[LayerAProblem(code="A1", path="src/a.py", text="Syntax error")])
    assert not bad.ok


def test_layer_b_counts_and_ok():
    result = LayerBResult(tests=[outcome("pass"), outcome("fail"), outcome("error")])

    assert (result.passed, result.failed, result.ok) == (1, 2, False)
    assert LayerBResult(tests=[outcome("pass"), outcome("skipped")]).ok


def test_layer_b_is_not_ok_when_timed_out_not_run_or_empty():
    assert not LayerBResult(tests=[outcome("pass")], timed_out=True).ok
    assert not LayerBResult(ran=False, error="no python").ok
    assert not LayerBResult().ok  # no tests found is never a pass


def test_traceback_tail_is_limited_to_20_lines():
    with pytest.raises(ValidationError):
        TestOutcome(name="t", result="fail", traceback_tail=["x"] * 21)
