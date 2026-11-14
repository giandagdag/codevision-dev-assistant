"""What the developer can do with the Tester's report (spec sections 8, 9 and 15): accept a
Should fix with a reason, reopen it, dispute a Must fix, run the review again, and read the report.

Thin, like da_build_flow: every action is ONE write transaction with the build revision check, so
an old window is refused. The label is never stored on the closed run; plain code works it out from
the newest review plus the developer's actions (like a status box that is recalculated from the
review sheet each time it is printed).
"""

from contextlib import contextmanager
from datetime import UTC, datetime

from agents import da_build_flow as build_flow
from agents import da_build_loop as loop
from agents import da_tester_review as tester
from agents.da_build_flow import BuildTx, _turn, escalate
from agents.da_escalation_flow import escalate as open_escalation
from agents.da_escalation_flow import request_triggers
from agents.da_escalation_triggers import dispute as dispute_trigger
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import (
    BuildError,
    ensure_build_tables,
    read_build_run,
    read_build_state,
    read_rounds,
)
from db_table_functions.db_tbl_da_requests import read_request
from db_table_functions.db_tbl_da_tester import (
    count_unable_reviews,
    insert_action,
    read_actions,
    read_reviews,
)
from pydantic_classes.da_build_models import (
    LABEL_NOT_PASSING,
    LABEL_READY,
    LABEL_UNABLE,
    LABEL_WITH_WARNINGS,
    BuildView,
)
from pydantic_classes.da_models import STATUS_NOT_PASSING, STATUS_READY_FOR_REVIEW
from pydantic_classes.da_tester_models import (
    ACCEPT_MAX_CHARS,
    ACCEPT_MIN_CHARS,
    SEVERITY_TEXT,
    FindingAction,
    FindingRow,
    ReviewRecord,
    TesterView,
)

DONE_STEPS = ("b_done", "b_written", "b_write_stopped")
REASON_MESSAGE = f"Please write a reason of {ACCEPT_MIN_CHARS} to {ACCEPT_MAX_CHARS} characters."
DISPUTE_PREFIX = "Disputed Must fix: "
RERUN_KEY, RERUN_LABEL = "rerun_review", "Run the Tester review again"
LABEL_COLOUR = {
    LABEL_READY: "green",
    LABEL_WITH_WARNINGS: "yellow",
    LABEL_NOT_PASSING: "red",
    LABEL_UNABLE: "gray",
}


# --- actions ---


def accept_finding(
    settings,
    request_id: str,
    base_revision: int,
    finding_id: str,
    reason: str,
    now: datetime | None = None,
) -> None:
    """Accept a Should fix with a reason (7-17, 7-18). The label may turn from yellow to green."""
    reason = _clean_reason(reason)
    with _report_turn(settings, request_id, base_revision, now) as (tx, review, actions):
        item = _finding(review, finding_id, "should_fix")
        held = tester.finding_state(item.finding_id, review.review_number, actions)[0]
        if held in ("accepted", "overruled"):
            raise BuildError(f"{finding_id} is already {held}.")
        before = _label(review, actions)
        _record(tx, review, finding_id, "accepted", reason, actions)
        tx.audit("developer", "finding_accepted", {"finding": finding_id, "reason": reason})
        _audit_label(tx, review, actions, before)


def reopen_finding(
    settings, request_id: str, base_revision: int, finding_id: str, now: datetime | None = None
) -> None:
    """Take an accepted Should fix back (7-19). Audited. The label may turn yellow again."""
    with _report_turn(settings, request_id, base_revision, now) as (tx, review, actions):
        item = _finding(review, finding_id, "should_fix")
        if tester.finding_state(item.finding_id, review.review_number, actions)[0] != "accepted":
            raise BuildError(f"{finding_id} is not accepted, so there is nothing to reopen.")
        before = _label(review, actions)
        _record(tx, review, finding_id, "reopened", "", actions)
        tx.audit("developer", "finding_reopened", {"finding": finding_id})
        _audit_label(tx, review, actions, before)


def dispute_finding(
    settings,
    request_id: str,
    base_revision: int,
    finding_id: str,
    reason: str,
    now: datetime | None = None,
) -> None:
    """Dispute a Must fix (7-21): the request goes to a senior, like Get help, with the open item
    `Disputed Must fix: F-n`. A Must fix can never be accepted away."""
    reason = _clean_reason(reason)
    with _report_turn(settings, request_id, base_revision, now) as (tx, review, actions):
        _finding(review, finding_id, "must_fix")
        decision = dispute_trigger(request_triggers(tx.conn, request_id), finding_id)
        if decision.switched_off:
            # D-I: the Must fix stays open and nothing moves; the chat says so.
            tx.say("developer", f"Dispute {finding_id}: {reason}")
            open_escalation(tx.conn, request_id, decision, tx.now)
            return
        _record(tx, review, finding_id, "disputed", reason, actions)
        tx.say("developer", f"Dispute {finding_id}: {reason}")
        tx.audit("developer", "finding_disputed", {"finding": finding_id, "reason": reason})
        escalate(tx, f"{DISPUTE_PREFIX}{finding_id}", {"step": tx.state.step}, decision)


def rerun_review(
    settings, request_id: str, base_revision: int, client_factory=None, now_fn=None
) -> None:
    """Run the Tester review again (7-12), only for Unable to assess. No round is used."""
    loop.rerun_review(settings, request_id, base_revision, client_factory, now_fn)


# --- reading ---


def get_tester_view(settings, request_id: str) -> TesterView:
    """Everything the Tests tab needs about the Tester's report, read with no lock."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        conn.execute("BEGIN")
        state = read_build_state(conn, request_id)
        request = read_request(conn, request_id)
        if state is None or state.build_number == 0 or request is None:
            return TesterView()
        number = state.build_number
        reviews = read_reviews(conn, request_id, number)
        actions = read_actions(conn, request_id, number)
        rounds = read_rounds(conn, request_id, number)
        run = read_build_run(conn, request_id, number)
        unable_total = count_unable_reviews(conn, request_id)
    if not reviews:
        return TesterView(label=run.label if run else "")
    review = reviews[-1]
    ran = bool(rounds) and review.round == rounds[-1].round
    label = _label(review, actions) if ran else (run.label if run else "")
    rows = []
    for item in _sorted(review):
        if item.kept:
            acted, why = tester.finding_state(item.finding_id, review.review_number, actions)
            who = tester.finding_actor(item.finding_id, review.review_number, actions)
            rows.append(FindingRow(finding=item, state=acted, reason=why, actor=who))
    finished = state.step in DONE_STEPS
    return TesterView(
        review=review,
        label=label,
        rows=rows,
        dropped=[item for item in review.findings if not item.kept],
        earlier=reviews[:-1],
        summary=_summary(review, rows),
        can_rerun=finished
        and request.status == STATUS_READY_FOR_REVIEW
        and review.result == "unable"
        and unable_total > 0,
        layer_c_ran=ran,
    )


def get_build_view(settings, request_id: str) -> BuildView:
    """The Build flow's view plus the Tester's report. The label is the live one (the closed run
    row is never edited), and the banner and the buttons follow it (spec sections 8, 9 and 10)."""
    view = build_flow.get_build_view(settings, request_id)
    if view.state.build_number == 0:
        return view
    report = get_tester_view(settings, request_id)
    changes: dict = {"tester": report}
    if report.layer_c_ran and view.state.step in DONE_STEPS:
        changes["label"] = report.label
        if view.state.step == "b_written":
            changes["banner_kind"] = LABEL_COLOUR.get(report.label, "green")
            changes["banner_text"] = f"{report.label}. The code files are in your folder."
    if report.can_rerun:
        changes["buttons"] = [*view.buttons, (RERUN_KEY, RERUN_LABEL)]
    return view.model_copy(update=changes)


# --- helpers ---


@contextmanager
def _report_turn(settings, request_id, base_revision, now):
    """Open one action's transaction on a finished build with a review, check the revision, and
    hand back (tx, newest review, actions). Refuses to act on a running or escalated build."""
    with _turn(settings.db_path, request_id, base_revision, now or datetime.now(UTC)) as tx:
        if tx.state.step not in DONE_STEPS:
            raise BuildError("The Tester report can only be changed when the build is finished.")
        if tx.request.status not in (STATUS_READY_FOR_REVIEW, STATUS_NOT_PASSING):
            raise BuildError("This request is no longer waiting for your review.")
        number = tx.state.build_number
        reviews = read_reviews(tx.conn, tx.request.request_id, number)
        if not reviews:
            raise BuildError("The Tester has not reviewed this build.")
        rounds = read_rounds(tx.conn, tx.request.request_id, number)
        if not rounds or reviews[-1].round != rounds[-1].round:
            raise BuildError(
                "Layer C did not run in the last round, so there is nothing to answer."
            )
        actions = read_actions(tx.conn, tx.request.request_id, number)
        yield tx, reviews[-1], actions


def _clean_reason(reason: str) -> str:
    text = " ".join((reason or "").split())
    if not ACCEPT_MIN_CHARS <= len(text) <= ACCEPT_MAX_CHARS:
        raise BuildError(REASON_MESSAGE)
    return text


def _finding(review: ReviewRecord, finding_id: str, severity: str):
    for item in review.findings:
        if item.finding_id == finding_id and item.kept:
            if item.severity != severity:
                what = SEVERITY_TEXT[item.severity]
                raise BuildError(f"{finding_id} is a {what}, so that action is not possible.")
            return item
    raise BuildError(f"There is no finding {finding_id} in the newest review.")


def _record(tx: BuildTx, review: ReviewRecord, finding_id: str, action: str, reason: str, actions):
    item = FindingAction(
        request_id=tx.request.request_id,
        build_number=tx.state.build_number,
        review_number=review.review_number,
        finding_id=finding_id,
        action=action,
        reason=reason,
    )
    insert_action(tx.conn, item, tx.now)
    actions.append(item)
    tx.set()  # the revision goes up, so an old window is refused


def _label(review: ReviewRecord, actions: list[FindingAction]) -> str:
    return tester.compute_label(
        review.findings, _zones(review), review.result, review.review_number, actions
    )


def _zones(review: ReviewRecord) -> list[str]:
    """A zone warning keeps the label yellow. The review saved its warnings as text lines."""
    return list(review.zone_warnings)


def _audit_label(tx: BuildTx, review: ReviewRecord, actions, before: str) -> None:
    after = _label(review, actions)
    if after != before:
        tx.audit("developer", "label_changed", {"from": before, "to": after})
        tx.say("assistant", f"The label is now {after}.")


def _sorted(review: ReviewRecord):
    order = {"must_fix": 0, "should_fix": 1, "fyi": 2}
    return sorted(review.findings, key=lambda item: order[item.severity])


def _summary(review: ReviewRecord, rows: list[FindingRow]) -> str:
    if review.result == "unable":
        return f"Tester review of round {review.round}: the reply could not be used."
    count = {key: sum(1 for r in rows if r.finding.severity == key) for key in SEVERITY_TEXT}
    text = (
        f"Tester review of round {review.round}: {count['must_fix']} Must fix, "
        f"{count['should_fix']} Should fix, {count['fyi']} FYI."
    )
    for warning in review.zone_warnings:
        text += f" {warning}"
    return text
