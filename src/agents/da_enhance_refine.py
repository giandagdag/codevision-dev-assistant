"""The safety net in a requirement-lane Refine (Phase 9 spec section 10, tests 9-44 and 9-46).

When Confirm v(N+1) saves a new record version of an enhance request, the accepted safety net is
carried to that version. The tests themselves never change: they capture the ORIGINAL behaviour
(Phase 9 decision 5). Plain code only re-marks the "expected to change" links:

- a case linked to a criterion that is unchanged keeps its link;
- a case linked to a CHANGED criterion keeps its link, and he is asked to look at it;
- a case linked to a REMOVED criterion becomes "Must still pass", and he is asked to look at it;
- a must-not-change item with no proven case is listed as "not covered, check manually".

Nothing to look at: the carried net is accepted at once. Something to look at: the net waits at
step `s_review` (Safety net tab); he can change a mark, use Correct something to ask for a test
for a new item (it runs against the baseline, never his edited code), then Continue.

AS400 picture: the regression test pack stays as it was; only the "this will now behave
differently" stickers are looked at again after a change request amendment.
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from agents.da_safety_net_checks import complete_not_covered
from db_table_functions.db_tbl_da_audit import insert_audit_event
from db_table_functions.db_tbl_da_enhance import (
    insert_safety_net,
    next_net_version,
    read_accepted_net,
    read_enhance_state,
    save_enhance_state,
)
from db_table_functions.db_tbl_da_understand import add_message
from pydantic_classes.da_enhance_models import SafetyNet, SafetyNetRow
from pydantic_classes.da_refine_models import RecordDiff
from pydantic_classes.da_request_record_models import RequestRecord

TEXT_PREFIX = "Safety net carried to version {version}."


@dataclass
class CarryResult:
    net: SafetyNet
    # (case ID, criterion ID, "changed" or "removed"): marks he should look at.
    remarks: list[tuple[str, str, str]] = field(default_factory=list)
    # Must-not-change items that were not in the old net's coverage.
    new_uncovered: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return bool(self.remarks or self.new_uncovered)


def remark_net(net: SafetyNet, diff: RecordDiff, new: RequestRecord) -> CarryResult:
    """The pure part: the net for the new record version, and what he has to look at."""
    changes = {item.id: item.change for item in diff.criteria}
    remarks: list[tuple[str, str, str]] = []
    cases = []
    for case in net.cases:
        link = case.expected_to_change
        kind = changes.get(link) if link else None
        if kind == "removed":
            remarks.append((case.id, link, "removed"))
            case = case.model_copy(update={"expected_to_change": None})
        elif kind == "changed":
            remarks.append((case.id, link, "changed"))
        cases.append(case)
    carried = net.model_copy(update={"cases": cases})
    extended = complete_not_covered(carried, new)
    before = {item.item for item in net.not_covered}
    fresh = [item.item for item in extended.not_covered if item.item not in before]
    return CarryResult(net=extended, remarks=remarks, new_uncovered=fresh)


def carry_net_forward(
    conn: sqlite3.Connection,
    old: RequestRecord,
    new: RequestRecord,
    diff: RecordDiff,
    now: datetime,
) -> CarryResult | None:
    """Inside Confirm v(N+1)'s write transaction. None for a request with no accepted net."""
    state = read_enhance_state(conn, new.request_id)
    accepted = read_accepted_net(conn, new.request_id, old.version) if state else None
    if state is None or accepted is None:
        return None
    result = remark_net(accepted.net, diff, new)
    insert_safety_net(
        conn,
        SafetyNetRow(
            request_id=new.request_id,
            net_version=next_net_version(conn, new.request_id),
            record_version=new.version,
            net=result.net,
            fingerprint=accepted.fingerprint,
            proof=accepted.proof,
            accepted=not result.needs_review,
        ),
        now,
    )
    details = {
        "from": old.version,
        "to": new.version,
        "remarks": [list(item) for item in result.remarks],
        "new_uncovered": result.new_uncovered,
    }
    insert_audit_event(conn, new.request_id, "system", "safety_net_carried", details, now)
    add_message(conn, new.request_id, "assistant", _text(new.version, result), now)
    if result.needs_review:
        waiting = state.model_copy(update={"step": "s_review", "corrections_used": 0})
        save_enhance_state(conn, waiting, state.revision, now)
    return result


def _text(version: int, result: CarryResult) -> str:
    lines = [TEXT_PREFIX.format(version=version) + " The tests are not changed."]
    for case_id, criterion, kind in result.remarks:
        if kind == "removed":
            lines.append(
                f"{case_id} was expected to change under {criterion}, which was removed. "
                "It now says: must still pass. Change it on the Safety net tab if that is wrong."
            )
        else:
            lines.append(
                f"{criterion} changed. {case_id} is still marked as expected to change under it. "
                "Check the mark on the Safety net tab."
            )
    for item in result.new_uncovered:
        lines.append(
            f"{item} is not covered by the safety net, check manually. "
            "Use Correct something to ask for a test for it."
        )
    if result.needs_review:
        lines.append("Press Continue to Approach when the marks are right.")
    return "\n".join(lines)
