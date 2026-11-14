"""Handoff's two plain-code checks (Phase 10 spec section 2, H2 and H4). No AI, no database.

AS400 picture: the checklist the change-control clerk ticks before a promotion. H2 asks "is the
review clean?", H4 asks "is the member in the library the one we tested?". Both take plain data
in and give plain data out, so they are tested with made-up values.
"""

from pydantic_classes.da_build_models import (
    LABEL_NOT_PASSING,
    LABEL_READY,
    LABEL_UNABLE,
    LABEL_WITH_WARNINGS,
)
from pydantic_classes.da_handoff_models import Blocker, PathCheck
from pydantic_classes.da_tester_models import FindingRow

# A finding in one of these states no longer blocks Handoff (accepted by him or overruled).
CLOSED_STATES = ("accepted", "overruled")

UNABLE_TEXT = "The Tester could not assess this build. Run the Tester review again."
NOT_PASSING_TEXT = "The build is Not passing. Refine, or Get help."
LAST_RUN_TEXT = "The last test run did not finish. Build or check again."


def findings_check(
    label: str, rows: list[FindingRow], last_tested_finished: bool
) -> list[Blocker]:
    """H2: every reason Handoff is refused, all at once (the chat shows the whole list).

    `rows` are the kept findings of the newest review with their current state. A finding fixed
    by a later build is simply not in the newest review, so it never blocks."""
    blockers: list[Blocker] = []
    if label == LABEL_UNABLE:
        blockers.append(Blocker(kind="label", text=UNABLE_TEXT))
    elif label == LABEL_NOT_PASSING:
        blockers.append(Blocker(kind="label", text=NOT_PASSING_TEXT))
    elif label not in (LABEL_READY, LABEL_WITH_WARNINGS):
        blockers.append(Blocker(kind="label", text=f"The label is not ready for handoff: {label}."))
    for row in rows:
        blocker = _finding_blocker(row)
        if blocker is not None:
            blockers.append(blocker)
    if not last_tested_finished:
        blockers.append(Blocker(kind="last_tested", text=LAST_RUN_TEXT))
    return blockers


def _finding_blocker(row: FindingRow) -> Blocker | None:
    finding = row.finding
    if row.state in CLOSED_STATES:
        return None
    if finding.severity == "must_fix":
        # A Must fix can only be closed by a senior's overrule.
        text = f"{finding.finding_id} (Must fix) is still open: Fix it, or Get help."
        return Blocker(kind="must_fix", finding_id=finding.finding_id, text=text)
    if finding.severity == "should_fix":
        text = f"{finding.finding_id} (Should fix) is still open: Fix it or Accept, with reason."
        return Blocker(kind="should_fix", finding_id=finding.finding_id, text=text)
    return None  # FYI never blocks


def compare_fingerprints(
    planned: list[str], seen: dict[str, str], expected: dict[str, str]
) -> list[PathCheck]:
    """H4: per planned path, equal, changed or missing. Files in the folder that are not planned
    are ignored (R1: planned files only). `seen` has no entry for a file the browser did not
    find."""
    checks = []
    for path in planned:
        got = seen.get(path, "")
        want = expected.get(path, "")
        if not got:
            result = "missing"
        elif got == want:
            result = "equal"
        else:
            result = "changed"
        checks.append(PathCheck(path=path, seen=got, expected=want, result=result))
    return checks


def folder_blockers(checks: list[PathCheck]) -> list[str]:
    """The plain words for every path that is not equal (spec section 2, h_blocked_folder)."""
    words = {"changed": "Changed since the last test", "missing": "Missing"}
    return [f"{item.path}: {words[item.result]}" for item in checks if item.result != "equal"]
