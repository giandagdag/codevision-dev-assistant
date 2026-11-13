"""Phase 10 step 3: the PR summary builder (spec section 5) and the hand-edited definition."""

import pytest

from agents.da_handoff_facts import hand_edited_paths
from agents.da_handoff_summary import FOOTER, build_summary
from pydantic_classes.da_handoff_models import CriterionFact, FileFact, SummaryFacts

MAX = 6000


def base(**changes) -> SummaryFacts:
    facts = SummaryFacts(
        request_id="CVDA-2026-0001",
        record_version=2,
        summary="Add a daily limit check",
        criteria=[
            CriterionFact(criterion_id="AC-1", tests=2, passed=2),
            CriterionFact(criterion_id="AC-2", tests=1, passed=1),
        ],
        yours=1,
        tester_label="Ready for your review",
        files=[FileFact(path="src/agents/da_limit.py", is_new=True)],
        build_number=3,
        checked_on="2026-11-14",
    )
    return facts.model_copy(update=changes)


def lines_of(facts: SummaryFacts, max_chars: int = MAX) -> list[str]:
    return build_summary(facts, max_chars).split("\n")


def test_new_request_lines_in_order():
    lines = lines_of(base())
    assert lines[0] == "CVDA-2026-0001 v2: Add a daily limit check"
    assert lines[1] == "Kind: new"
    assert lines[2].startswith("Criteria: 2 \u00b7 Tests: 3 of 3 passed (1 written by the dev")
    assert lines[3:5] == ["AC-1: 2 tests, passed", "AC-2: 1 test, passed"]
    assert lines[5].startswith("Tester: Ready for your review (0 Must fix fixed")
    assert lines[6:8] == ["Files:", "- src/agents/da_limit.py (new)"]
    assert "Reuses: none" in lines
    assert "Decisions: none" in lines
    assert "Accepted risks: none" in lines
    assert "Flag-for-review zones: none" in lines
    assert "Safety-net gaps: not applicable (new code)" in lines
    assert "Senior involvement: none" in lines
    assert lines[-2] == "Final check: workspace = last tested (build 3, 2026-11-14)"
    assert lines[-1] == FOOTER


def test_follows_line_only_when_set():
    assert not any(x.startswith("Follows") for x in lines_of(base()))
    assert "Follows: CVDA-2026-0001" in lines_of(base(follows_request_id="CVDA-2026-0001"))


def test_enhancement_open_unassigned_override_and_two_gaps():
    facts = base(
        kind="enhance",
        capability="Limits",
        named_senior="Limits capability lead",
        capability_confirmed=False,
        accepted_risks=["Local changes confirmed as intentional"],
        gaps=["Rounding (reads a screen)", "Audit log (needs a database)"],
        impact_unchecked=True,
        files=[FileFact(path="src/agents/da_limit.py", hand_edited=True)],
    )
    lines = lines_of(facts)
    assert lines[1:3] == [
        "Kind: enhancement",
        "Capability: Limits (picked by developer, not yet confirmed by Admin)",
    ]
    assert "- src/agents/da_limit.py (changed, edited by developer)" in lines
    assert "- Local changes confirmed as intentional" in lines
    assert "- Rounding (reads a screen). Check manually" in lines
    assert "- Audit log (needs a database). Check manually" in lines
    assert "Impact could not be checked" in lines


def test_confirmed_capability_names_the_senior():
    facts = base(kind="enhance", capability="Limits", named_senior="Limits capability lead")
    assert "Capability: Limits (senior: Limits capability lead)" in lines_of(facts)


def test_overruled_finding_and_closed_escalation():
    facts = base(
        must_fixed=1,
        should_fixed=2,
        accepted=1,
        fyi=3,
        overruled=1,
        overruled_by="senior-01",
        senior_involvement=["dispute: senior-01, overruled F-2, 2026-11-14"],
        zones=["Login"],
        named_senior="Login lead",
    )
    lines = lines_of(facts)
    assert any(
        x == "Tester: Ready for your review (1 Must fix fixed, 2 Should fix fixed, 1 accepted, "
        "3 FYI, 1 overruled by senior-01)"
        for x in lines
    )
    assert "- dispute: senior-01, overruled F-2, 2026-11-14" in lines
    assert "- Login (required reviewer: Login lead)" in lines


def test_zone_without_senior_points_to_catalog():
    lines = lines_of(base(zones=["Login"]))
    assert "- Login (required reviewer: see the capability catalog)" in lines


def test_no_tests_path_and_no_folder_path():
    text = build_summary(base(), MAX)
    assert "tests/" not in text
    assert "C:\\" not in text


def test_over_the_guard_cuts_only_the_criteria_list():
    many = [CriterionFact(criterion_id=f"AC-{n}", tests=1, passed=1) for n in range(1, 60)]
    facts = base(criteria=many)
    full = build_summary(facts, 100_000)
    short = build_summary(facts, 1500)
    assert len(short) < len(full)
    assert "AC-30:" not in short
    assert "59 criteria" in short
    # Every other line is still there.
    for kept in ("Tester:", "Files:", "Final check:", FOOTER):
        assert kept in short


def test_five_file_request_is_under_4000_characters():
    files = [FileFact(path=f"src/agents/da_part_{n}.py", is_new=n % 2 == 0) for n in range(5)]
    criteria = [CriterionFact(criterion_id=f"AC-{n}", tests=2, passed=2) for n in range(1, 9)]
    facts = base(
        files=files,
        criteria=criteria,
        reuses=["RU-1: reuse, the helper already exists"],
        decisions=["DD-1: Where does the limit live? In the agent file"],
    )
    assert len(build_summary(facts, MAX)) < 4000


# --- gathering the facts from a real (fake-provider) build ---


def test_gather_facts_from_a_built_request(make_settings, published_rulebook):
    from agents import da_build_flow as flow
    from agents import da_build_loop as loop
    from agents.da_handoff_facts import gather_summary_facts
    from db_table_functions.da_db import open_db
    from tests.da_build_play import ready_with_workspace

    settings = make_settings()
    request_id = ready_with_workspace(settings)[0]
    flow.start_build(settings, request_id, flow.get_revision(settings, request_id))
    assert loop.run_build(settings, request_id) == "done"
    with open_db(settings.db_path) as conn:
        conn.execute("BEGIN")
        facts = gather_summary_facts(conn, request_id)
    assert facts.request_id == request_id
    assert facts.build_number >= 1
    assert facts.files and facts.criteria
    assert facts.tester_label
    text = build_summary(facts, MAX)
    assert text.startswith(request_id)
    assert "tests/" not in text
    assert len(text) < 4000


# --- the hand-edited definition (Words table) ---


def test_hand_edited_when_scanned_fingerprint_is_the_tested_one():
    tested = {"a.py": "f2", "b.py": "f9"}
    scanned = {"a.py": {"f1", "f2"}, "b.py": {"f3"}}
    assert hand_edited_paths(tested, scanned, "build") == {"a.py"}


@pytest.mark.parametrize("kind", ["check"])
def test_hand_edited_after_a_check_run(kind):
    assert hand_edited_paths({"a.py": "f2"}, {"a.py": {"other"}}, kind) == {"a.py"}
    assert hand_edited_paths({"a.py": "f2"}, {}, kind) == set()
