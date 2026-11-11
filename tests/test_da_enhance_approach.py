"""Phase 9 step 13: Approach and the gate for an enhance request (test 9-36 and the file plan line
of 9-9). Targets are planned as `modify`, the prompt carries the enhance section, the test plan view
shows the safety net read-only, and gate check 4 needs the accepted safety net."""

import pytest

from agents import da_approach_flow as flow
from agents import da_safety_net_flow as net_flow
from agents.da_approach_agent import ApproachContext, format_enhance
from agents.da_approach_checks import PROPOSE, compute_gate, find_approach_problems
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import ApproachError
from db_table_functions.db_tbl_da_enhance import read_enhance_state
from pydantic_classes.da_approach_models import (
    ApproachReply,
    ApproachState,
    TestCase,
    TestPlanVersion,
)
from pydantic_classes.da_discovery_models import DiscoveryResult
from pydantic_classes.da_enhance_models import ImpactResult, ImpactRow, SafetyCase
from pydantic_classes.da_request_record_models import AcceptanceCriterion, RequestRecord
from tests.da_approach_play import discovery_confirmed_id
from tests.test_da_safety_net_flow import Runner, at_s_writing, state_of

pytestmark = pytest.mark.usefixtures("published_rulebook")

REQUEST_ID = "CVDA-2026-0001"
TARGET = "src/a/target.py"


@pytest.fixture
def policy(seed_rulebook):
    return seed_rulebook.policy


def make_discovery(impact=None):
    return DiscoveryResult(
        request_id=REQUEST_ID, round=1, record_version=1, rulebook_version=1,
        search_provider="fake", queries=[], hits=[], findings=[], limitations=[],
        summary_source="ai", impact=impact,
    )


def accepted_net_request(settings, tmp_path):
    """An enhance request whose safety net is accepted, ready for Proceed to Approach."""
    request_id = at_s_writing(settings)
    revision = state_of(settings, request_id).revision
    net_flow.run_safety_net(settings, request_id, revision, Runner(tmp_path))
    net_flow.accept_safety_net(settings, request_id, state_of(settings, request_id).revision)
    return request_id


def at_tests_step(settings, request_id):
    """Proceed, answer the design choice, accept the approach: the step is then `tests`."""
    view = flow.start_approach(settings, request_id, 0)
    while view.step == "choices":
        view = flow.choose_design_option(settings, request_id, view.buttons[0][1], view.revision)
    view = flow.accept_approach(settings, request_id, view.revision)
    assert view.step == "tests"
    return view


# --- the plain-code rules ---


def problems_for_targets(policy, files, targets, needs_people=()):
    reply = ApproachReply.model_validate({
        "summary": "x", "files": files, "needs_people": list(needs_people),
        "reuse_decisions": [], "design_choices": [], "libraries": [],
    })
    found = find_approach_problems(reply, policy, make_discovery(), set(), PROPOSE, targets)
    return [p for p in found if "program being enhanced" in p]


def test_a_target_must_be_planned_as_modify(policy):
    create = {"path": TARGET, "action": "create", "purpose": "p", "reuses": []}
    modify = {**create, "action": "modify"}
    people = {"path": TARGET, "reason": "a person changes it"}

    assert problems_for_targets(policy, [modify], [TARGET]) == []
    assert len(problems_for_targets(policy, [create], [TARGET])) == 1
    assert problems_for_targets(policy, [], [TARGET], [people]) == []
    assert problems_for_targets(policy, [create], []) == []  # no targets: nothing is asked


def gate_check_4(kind, net_accepted):
    criterion = AcceptanceCriterion(id="AC-1", kind="success", given="g", when="w", then="t")
    record = RequestRecord(
        request_id=REQUEST_ID, rulebook_version=1, kind=kind, acceptance_criteria=[criterion]
    )
    state = ApproachState(
        request_id=REQUEST_ID, accepted_approach_version=1, accepted_plan_version=1
    )
    plan = TestPlanVersion(
        request_id=REQUEST_ID, plan_version=1, approach_version=1,
        cases=[TestCase(test_id="T-1", criterion_id="AC-1", given="g", expect="e",
                        source="tester")],
        source_of_change="tester_plan",
    )
    return compute_gate(record, 1, None, 0, 0, state, plan, net_accepted=net_accepted)[3]


def test_9_36_check_4_needs_the_accepted_net_for_enhance_and_fix_only():
    for kind in ("enhance", "fix"):
        refused = gate_check_4(kind, net_accepted=False)
        assert refused.passed is False and "safety net" in refused.detail
        assert gate_check_4(kind, net_accepted=True).passed is True
    assert gate_check_4("new", net_accepted=False).passed is True


def test_the_prompt_section_names_targets_scope_callers_and_net_sentences():
    record = RequestRecord(
        request_id=REQUEST_ID, rulebook_version=1, kind="enhance",
        targets=[TARGET], functions_in_scope=["format_expiry"],
    )
    impact = ImpactResult(rows=[ImpactRow(
        caller_path="src/a/caller.py", caller_function="show", line=7,
        function_in_scope="format_expiry", kind="direct",
    )])
    case = SafetyCase(id="S-1", today_behaviour="It prints the day.", function="format_expiry",
                      expected_to_change="AC-1")
    context = ApproachContext(
        charter=None, record=record, discovery=make_discovery(impact), policy=None,
        net_cases=[case],
    )

    text = format_enhance(context)

    assert f"Target (list it in files with action modify): {TARGET}" in text
    assert "format_expiry" in text and "src/a/caller.py :: show (line 7)" in text
    assert "S-1: It prints the day. [expected to change (AC-1)]" in text


def test_a_new_program_gets_no_enhance_section():
    record = RequestRecord(request_id=REQUEST_ID, rulebook_version=1)
    context = ApproachContext(None, record, make_discovery(), None)

    assert format_enhance(context) == ""


# --- the flow ---


def test_9_9_the_plan_modifies_the_target_and_the_net_is_shown_read_only(make_settings, tmp_path):
    settings = make_settings()
    request_id = accepted_net_request(settings, tmp_path)

    view = at_tests_step(settings, request_id)

    assert [(f.path, f.action) for f in view.approach.plan.files] == [
        (path, "modify") for path in view.record.targets
    ]
    assert [c.id for c in view.safety_net_cases] == ["S-1"]


def test_9_36_the_gate_of_an_enhance_request_needs_the_accepted_net(
    make_settings, tmp_path, monkeypatch
):
    settings = make_settings()
    request_id = accepted_net_request(settings, tmp_path)
    view = at_tests_step(settings, request_id)
    # The saved nets cannot be edited (append-only), so arrange "no accepted net" by the read.
    real_read = flow.read_accepted_net
    monkeypatch.setattr(flow, "read_accepted_net", lambda *args: None)

    refused = flow.accept_test_plan(settings, request_id, view.revision)

    assert refused.request.status != "READY_TO_BUILD"
    assert refused.gate[3].passed is False and "safety net" in refused.gate[3].detail
    monkeypatch.setattr(flow, "read_accepted_net", real_read)
    passed = flow.accept_test_plan(settings, request_id, refused.revision)
    assert passed.request.status == "READY_TO_BUILD"


def test_proceed_to_approach_is_refused_until_the_net_is_accepted(make_settings):
    settings = make_settings()
    request_id = at_s_writing(settings)

    with pytest.raises(ApproachError, match="Accept the safety net first"):
        flow.start_approach(settings, request_id, 0)


def test_a_new_program_request_is_not_asked_for_a_net(make_settings):
    settings = make_settings()
    request_id = discovery_confirmed_id(settings)

    view = flow.start_approach(settings, request_id, 0)

    assert view.safety_net_cases == [] and view.step in ("choices", "review")
    with open_db(settings.db_path) as conn:
        assert read_enhance_state(conn, request_id) is None
