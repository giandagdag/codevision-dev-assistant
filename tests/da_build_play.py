"""Test helpers for the Build: a made-up build context and the nine scripted test cases.
Nothing here calls an AI."""

from agents.da_build_agent import BuildContext
from pydantic_classes.da_approach_models import ApproachReply, ApproachVersion, TestCase
from tests.da_approach_samples import REQUEST_ID, good_plan, sample_record

CREATE = "src/agents/excel_processor.py"
MODIFY = "src/agents/upload_validator.py"
ORIGINAL = "def validate(path):\n    return True\n"


def make_cases(count: int = 9, developer: tuple[int, ...] = ()) -> list[TestCase]:
    """T-1 to T-<count> over criteria AC-1 to AC-3. Numbers in `developer` are 'Yours' cases."""
    return [
        TestCase(
            test_id=f"T-{number}",
            criterion_id=f"AC-{(number - 1) % 3 + 1}",
            given=f"a workbook for case {number}",
            expect=f"the result for case {number} is visible",
            source="developer" if number in developer else "tester",
        )
        for number in range(1, count + 1)
    ]


def make_approach(request_id: str = REQUEST_ID) -> ApproachVersion:
    return ApproachVersion(
        request_id=request_id,
        approach_version=1,
        source="proposal",
        record_version=1,
        rulebook_version=1,
        discovery_round=1,
        plan=ApproachReply.model_validate(good_plan()),
    )


def make_context(seed_rulebook, cases: int = 9, **policy_changes) -> BuildContext:
    policy = seed_rulebook.policy.model_copy(update=policy_changes)
    return BuildContext(
        charter=seed_rulebook.charter,
        record=sample_record(),
        approach=make_approach(),
        cases=make_cases(cases),
        policy=policy,
    )
