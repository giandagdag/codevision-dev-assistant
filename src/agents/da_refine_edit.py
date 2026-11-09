"""The two R3 buttons that need new engine code (Phase 8 spec section 3, tests 8-6 and 8-8).

After "Check my edits" ends NOT_PASSING the developer picks one of three buttons:
- Fix my edit: the bug lane, with the failing frozen tests as the repro. No new test is needed and
  the rebuild starts at once (like Fix it, but the input is the failure report).
- My edit is right, the requirement was wrong: the requirement lane, with the feedback pre-filled.
- I'll fix it myself: `da_refine_flow.fix_myself` (already built).

AS400 picture: a PTF test failed after the programmer's own change. He can send the member back to
be corrected, say the test spec is out of date, or take the member back and fix it himself.
"""

from datetime import UTC, datetime

from agents.da_llm_client import LLMClient
from agents.da_refine_bug import _request_of, begin_rebuild
from agents.da_refine_checks import cap_message, refine_cap_reached
from agents.da_refine_flow import list_versions, restore_preview
from agents.da_refine_lanes import (
    STEP_START,
    RefineTx,
    _load_state,
    _require_refinable,
    _save,
    _write,
    choose_lane,
    get_refine_revision,
    suggest,
)
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables, read_build_run, read_rounds
from db_table_functions.db_tbl_da_refine import RefineError, insert_refine
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request
from db_table_functions.db_tbl_da_understand import read_confirmed_record
from pydantic_classes.da_models import STATUS_NOT_PASSING, STATUS_REVISION
from pydantic_classes.da_refine_models import STEP_BUG_FIXING, RefineRow, RefineState

FIX_EDIT_KEY, FIX_EDIT_LABEL = "fix_edit", "Fix my edit"
EDIT_RIGHT_KEY, EDIT_RIGHT_LABEL = "edit_right", "My edit is right, the requirement was wrong"
NOT_FAILED_LINE = "This is only possible right after Check my edits ended Not passing."


class _Failure:
    """What the failed check run told us: the tests and the file, in plain words."""

    def __init__(self, test_ids: list[str], path: str, expected: str):
        self.test_ids, self.path, self.expected = test_ids, path, expected

    def feedback(self) -> str:
        names = ", ".join(self.test_ids) or "a test"
        return f"My edit failed {names}."[:300]

    def pre_filled(self) -> str:
        name = self.test_ids[0] if self.test_ids else "a test"
        text = f"My edit to `{self.path}` is intended: {name} expects the old behaviour."
        if self.expected:
            text += f" It expects: {self.expected}"
        return text[:1000]


def fix_edit(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> RefineState:
    """Fix my edit: a bug lane Refine (source `failed_check`) that goes straight to the rebuild.
    The caller then runs the build loop. REVISION_IN_PROGRESS then BUILDING, both audited."""
    now = now or datetime.now(UTC)
    failure = _read_failure(settings, request_id)
    policy = get_rulebook_for_request(settings.db_path, request_id).rulebook.policy
    with _write(settings.db_path) as conn:
        state = _load_state(conn, request_id, base_revision)
        if state.step != STEP_START:
            raise RefineError("A Refine is already in progress. Finish or cancel it first.")
        request = _request_of(conn, request_id)
        build = _require_refinable(conn, request)
        if request.status != STATUS_NOT_PASSING:
            raise RefineError(NOT_FAILED_LINE)
        if refine_cap_reached(state.refine_count, policy.refine_max_per_request):
            raise RefineError(cap_message(state.refine_count))
        number = state.refine_number + 1
        record = read_confirmed_record(conn, request_id, request.version)
        insert_refine(
            conn,
            RefineRow(
                request_id=request_id,
                refine_number=number,
                source="failed_check",
                feedback=failure.feedback(),
                chosen_lane="bug",
                from_status=request.status,
                record_version_before=record.version if record else request.version,
                approach_version_before=build.approach_version,
            ),
            now,
        )
        tx = RefineTx(conn, request, state, now)
        tx.say("developer", FIX_EDIT_LABEL)
        tx.move_to(STATUS_REVISION)
        started = {"refine": number, "chosen": "bug", "from": "failed_check"}
        tx.audit("developer", "refine_started", started)
        tx.request = begin_rebuild(conn, tx.request, now)
        tx.set(
            step=STEP_BUG_FIXING,
            refine_number=number,
            refine_count=state.refine_count + 1,
            chosen_lane="bug",
            from_status=request.status,
            fix_finding=None,
            restore_pick=0,
            repro=None,
            repro_tries=0,
            repro_passed_today=0,
        )
        return _save(tx, base_revision)


def edit_right(
    settings,
    request_id: str,
    base_revision: int,
    client: LLMClient | None = None,
    now: datetime | None = None,
) -> RefineState:
    """My edit is right: the feedback is pre-filled and the requirement lane starts. The lane
    suggestion is still asked for (and shown in the audit), but his click decides, so the lane is
    chosen here. Ends at `req_revise`; the caller runs the revision call."""
    failure = _read_failure(settings, request_id)
    suggest(
        settings,
        request_id,
        failure.pre_filled(),
        base_revision,
        client,
        source="failed_check",
        now=now,
    )
    return choose_lane(
        settings, request_id, "requirement", get_refine_revision(settings, request_id), now
    )


# --- Restore: the list, the warning and Cancel (the write itself is da_refine_flow, spec 9) ---

RESTORE_CANCEL_LABEL = "Cancel"


def open_restore(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> RefineState:
    """Restore an earlier version: open the list of builds he can go back to."""
    if not [v for v in list_versions(settings, request_id) if not v.is_last_tested]:
        raise RefineError("There is no earlier version to restore yet.")
    return _set_restore(settings, request_id, base_revision, -1, "", now)


def pick_restore(
    settings, request_id: str, build_number: int, base_revision: int, now: datetime | None = None
) -> RefineState:
    """He chose one build. The chat says which of his edits it would replace; nothing is written."""
    if build_number not in [v.build_number for v in list_versions(settings, request_id)]:
        raise RefineError(f"Build {build_number} has no saved code to restore.")
    preview = restore_preview(settings, request_id, build_number)
    text = f"Restore build {build_number} ({preview.label or 'earlier version'}) puts back "
    text += ", ".join(preview.files) + "."
    if preview.warning:
        text += f" {preview.warning}"
    if preview.left_out:
        text += f" Files the set did not have stay as they are: {', '.join(preview.left_out)}."
    text += f" Press {preview.button_label}, or {RESTORE_CANCEL_LABEL}."
    return _set_restore(settings, request_id, base_revision, build_number, text, now)


def close_restore(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> RefineState:
    """Cancel the Restore. Nothing was written, so there is nothing to give back."""
    return _set_restore(settings, request_id, base_revision, 0, "", now)


def _set_restore(
    settings, request_id: str, base_revision: int, pick: int, line: str, now: datetime | None
) -> RefineState:
    now = now or datetime.now(UTC)
    with _write(settings.db_path) as conn:
        state = _load_state(conn, request_id, base_revision)
        if state.step != STEP_START:
            raise RefineError("A Refine is already in progress. Finish or cancel it first.")
        _require_refinable(conn, _request_of(conn, request_id))
        tx = RefineTx(conn, _request_of(conn, request_id), state, now)
        if pick == 0:
            tx.say("developer", RESTORE_CANCEL_LABEL)
        elif line:
            tx.say("developer", f"Restore build {pick}?")
            tx.say("assistant", line)
        tx.set(restore_pick=pick)
        return _save(tx, base_revision)


def _read_failure(settings, request_id: str) -> _Failure:
    """The newest run must be a check run that ended NOT_PASSING; read what failed."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        conn.execute("BEGIN")
        request = _request_of(conn, request_id)
        build = _require_refinable(conn, request)
        run = read_build_run(conn, request_id, build.build_number)
        if request.status != STATUS_NOT_PASSING or run is None or run.kind != "check":
            raise RefineError(NOT_FAILED_LINE)
        rounds = read_rounds(conn, request_id, build.build_number)
    report = rounds[-1].failure_report if rounds else None
    items = report.items if report else []
    files = report.files_to_fix if report else []
    return _Failure(
        [item.test_id for item in items],
        files[0] if files else "the planned file",
        items[0].expected if items else "",
    )
