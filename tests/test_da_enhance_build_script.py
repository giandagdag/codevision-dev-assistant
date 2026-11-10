"""Phase 9 step 14c: the scripted Build replies for the made-up limits program.

The replies must pass the real checks of the Build (contract, test file, edit blocks) and the real
sandbox, and the two test-only switches must trip A8 and A9. No AI is called."""

from pathlib import Path

import pytest

from agents import da_build_agent as build_agent
from agents.da_build_agent import BuildContext, ScriptedBuildClient, build_code_prompt
from agents.da_build_checks import apply_edits
from agents.da_enhance_build_checks import scope_problems, scoped_view, signature_problems
from agents.da_sandbox import run_tests
from pydantic_classes.da_approach_models import ApproachReply, ApproachVersion
from pydantic_classes.da_enhance_models import ImpactRow
from pydantic_classes.da_request_record_models import MustNotChange
from tests.da_approach_samples import REQUEST_ID, good_plan, sample_record
from tests.da_build_play import make_cases

TARGET = "src/agents/limits_expiry_report.py"
ORIGINAL = (
    Path(__file__).parents[1] / "src" / "data" / "da_fake_codevision" / TARGET
).read_text(encoding="utf-8")
REFERENCE = Path(__file__).parent / "fixtures" / "da_reference_codevision"
EXCLUDE = [".env", "*.db", ".git", "*.key", "*.pem"]
IN_SCOPE = ["ExpiryReport.build_line"]


@pytest.fixture
def context(seed_rulebook):
    record = sample_record().model_copy(
        update={
            "kind": "enhance",
            "targets": [TARGET],
            "functions_in_scope": IN_SCOPE,
            "must_not_change": [MustNotChange(id="NC-1", text="The date text stays")],
        }
    )
    plan = good_plan(
        files=[{"path": TARGET, "action": "modify", "purpose": "Say expires today", "reuses": []}],
        reuse_decisions=[],
        libraries=[],
    )
    approach = ApproachVersion(
        request_id=REQUEST_ID, approach_version=1, source="proposal", record_version=1,
        rulebook_version=1, discovery_round=1, plan=ApproachReply.model_validate(plan),
    )
    return BuildContext(
        charter=seed_rulebook.charter, record=record, approach=approach,
        cases=make_cases(3), policy=seed_rulebook.policy,
    )


def client():
    return ScriptedBuildClient("generator")


def contract_of(context):
    result = build_agent.write_contract(client(), context, {TARGET: ORIGINAL})
    assert result.ok, result.problems
    return result.value


def edits_of(context, contract):
    view = scoped_view(TARGET, ORIGINAL, IN_SCOPE)
    prompt = build_code_prompt(context, contract, TARGET, "modify", 1, "tests", view)
    result = build_agent.write_code(client(), context, prompt, "modify")
    assert result.ok, result.problems
    return result.value.edits


def switch(monkeypatch, name):
    monkeypatch.setattr(build_agent, "FAKE_SWITCHES", frozenset({name}))


# --- the contract and the criterion tests pass the real checks ---


def test_the_scripted_contract_keeps_every_public_name_of_the_target(context):
    contract = contract_of(context)

    names = [item.name for item in contract.files[0].items]
    assert names == ["format_expiry", "days_left", "ExpiryReport"]


def test_the_scripted_criterion_tests_have_one_method_per_case_and_pass_the_real_checks(context):
    contract = contract_of(context)

    result = build_agent.write_tests(client(), context, contract)

    assert result.ok, result.problems
    assert result.value.count("    def test_t") == 3


# --- the edit blocks: in scope, applied, and the criterion tests pass in the sandbox ---


def test_the_scripted_edit_is_inside_the_scope_and_turns_the_criterion_tests_green(context):
    contract = contract_of(context)
    tests = build_agent.write_tests(client(), context, contract).value
    edits = edits_of(context, contract)

    text, problems = apply_edits(ORIGINAL, edits, TARGET)

    assert problems == [] and "expires today" in text
    assert scope_problems(TARGET, ORIGINAL, edits, IN_SCOPE) == []
    old = run_tests(REFERENCE, {TARGET: ORIGINAL}, "t1", tests, exclude=EXCLUDE, timeout_seconds=30)
    new = run_tests(REFERENCE, {TARGET: text}, "t1", tests, exclude=EXCLUDE, timeout_seconds=30)
    assert old.ran and not old.ok  # the new behaviour is missing on today's code
    assert new.ran and new.ok, [(t.name, t.result) for t in new.tests]


def test_a_fix_round_gets_a_harmless_block_that_still_applies(context):
    contract = contract_of(context)
    first = edits_of(context, contract)
    text, _ = apply_edits(ORIGINAL, first, TARGET)
    view = scoped_view(TARGET, text, IN_SCOPE)
    prompt = build_code_prompt(
        context, contract, TARGET, "modify", 2, "tests", view, "Test T-1 failed."
    )

    result = build_agent.write_code(client(), context, prompt, "modify")

    again, problems = apply_edits(text, result.value.edits, TARGET)
    assert problems == [] and again == text
    assert scope_problems(TARGET, text, result.value.edits, IN_SCOPE) == []


# --- the two switches ---


def test_the_edit_outside_scope_switch_trips_a8(context, monkeypatch):
    contract = contract_of(context)
    switch(monkeypatch, "edit_outside_scope")

    edits = edits_of(context, contract)

    problems = scope_problems(TARGET, ORIGINAL, edits, IN_SCOPE)
    assert [(p.code, p.path) for p in problems] == [("A8", TARGET)]
    assert "format_expiry" in problems[0].text


def test_the_signature_change_switch_trips_a9_only_when_a_caller_is_outside_the_plan(
    context, monkeypatch
):
    contract = contract_of(context)
    switch(monkeypatch, "signature_change")
    edits = edits_of(context, contract)
    text, problems = apply_edits(ORIGINAL, edits, TARGET)
    row = ImpactRow(
        caller_path="src/agents/limits_batch.py", caller_function="run", line=5,
        function_in_scope="days_left", kind="direct",
    )

    assert problems == []
    locked = signature_problems(TARGET, ORIGINAL, text, [row], [TARGET])
    assert [(p.code, "days_left" in p.text) for p in locked] == [("A9", True)]
    free = signature_problems(TARGET, ORIGINAL, text, [row], [TARGET, row.caller_path])
    assert free == []


def test_a_prompt_of_a_new_request_still_gets_the_excel_script(seed_rulebook):
    from tests.da_build_play import make_context

    context = make_context(seed_rulebook)

    result = build_agent.write_contract(client(), context, {})

    assert result.ok
    assert [f.path for f in result.value.files][0] == "src/agents/excel_processor.py"
