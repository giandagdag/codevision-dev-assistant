"""Fix it on a Should fix finding (Phase 8 spec section 7, D-H). The greyed Phase 7 button becomes
real: it starts a bug-lane style Refine with NO repro test. The finding (already proven by the
Phase 7 evidence rule) is the fix input. Round 1 rewrites the cited file only, then A, B and a fresh
Layer C run. The finding is `fixed` when the new review no longer has it. It counts in the cap.

AS400 picture: the code reviewer returns a marked-up listing. Fix it sends exactly that markup back
to the programmer for the one source member, then the reviewer reads it again.
"""

from datetime import UTC, datetime

from agents.da_refine_bug import _request_of, begin_rebuild
from agents.da_refine_checks import cap_message, refine_cap_reached
from agents.da_refine_lanes import RefineTx, _load_state, _require_refinable, _save, _write
from db_table_functions.db_tbl_da_refine import RefineError, insert_refine
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request
from db_table_functions.db_tbl_da_tester import read_reviews
from db_table_functions.db_tbl_da_understand import read_confirmed_record
from pydantic_classes.da_models import STATUS_REVISION
from pydantic_classes.da_refine_models import STEP_FINDING_FIXING, RefineRow, RefineState

FIX_IT_LABEL = "Fix it"


def fix_it(
    settings,
    request_id: str,
    base_revision: int,
    finding_id: str,
    now: datetime | None = None,
) -> RefineState:
    """Start the fix build for one open Should fix finding of the newest review. The caller then
    runs the build loop. REVISION_IN_PROGRESS then BUILDING, both audited."""
    now = now or datetime.now(UTC)
    policy = get_rulebook_for_request(settings.db_path, request_id).rulebook.policy
    with _write(settings.db_path) as conn:
        state = _load_state(conn, request_id, base_revision)
        if state.step != "start":
            raise RefineError("A Refine is already in progress. Finish or cancel it first.")
        request = _request_of(conn, request_id)
        build = _require_refinable(conn, request)
        if refine_cap_reached(state.refine_count, policy.refine_max_per_request):
            raise RefineError(cap_message(state.refine_count))
        finding = _open_should_fix(conn, request_id, build.build_number, finding_id)
        number = state.refine_number + 1
        record = read_confirmed_record(conn, request_id, request.version)
        insert_refine(
            conn,
            RefineRow(
                request_id=request_id,
                refine_number=number,
                source="finding",
                feedback=f"{finding.finding_id} {finding.file}: {finding.message}"[:300],
                chosen_lane="bug",
                from_status=request.status,
                record_version_before=record.version if record else request.version,
                approach_version_before=build.approach_version,
            ),
            now,
        )
        tx = RefineTx(conn, request, state, now)
        tx.say("developer", f"{FIX_IT_LABEL} ({finding.finding_id})")
        tx.move_to(STATUS_REVISION)
        tx.audit(
            "developer",
            "refine_started",
            {"refine": number, "chosen": "bug", "from": "finding", "finding": finding_id},
        )
        tx.request = begin_rebuild(conn, tx.request, now)
        tx.set(
            step=STEP_FINDING_FIXING,
            refine_number=number,
            refine_count=state.refine_count + 1,
            chosen_lane="bug",
            from_status=request.status,
            fix_finding=finding,
            restore_pick=0,
            repro=None,
            repro_tries=0,
            repro_passed_today=0,
        )
        return _save(tx, base_revision)


def _open_should_fix(conn, request_id: str, build_number: int, finding_id: str):
    reviews = read_reviews(conn, request_id, build_number)
    if not reviews:
        raise RefineError("There is no review to fix a finding from.")
    for item in reviews[-1].findings:
        if item.finding_id == finding_id and item.kept:
            if item.severity != "should_fix" or not item.fixable:
                raise RefineError("Fix it works on a Should fix finding that can be fixed.")
            return item
    raise RefineError("That finding is not in the newest review.")
