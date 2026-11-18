"""Collect the facts for the PR summary (Phase 10 spec section 5). The only reader of tables here.

`gather_summary_facts` reads on the caller's connection and writes nothing. `hand_edited_paths`
is plain code so the definition of "hand-edited" (spec Words table) is tested without a database.
"""

import sqlite3

from agents.da_build_checks import case_ids_from_method
from db_table_functions.db_tbl_da_approach import (
    read_approach_state,
    read_approach_versions,
    read_latest_plan,
)
from db_table_functions.db_tbl_da_build import read_build_state, read_rounds
from db_table_functions.db_tbl_da_discovery import read_latest_result
from db_table_functions.db_tbl_da_enhance import read_latest_safety_net
from db_table_functions.db_tbl_da_handoff import get_last_tested_fingerprints
from db_table_functions.db_tbl_da_refine import read_tested
from db_table_functions.db_tbl_da_requests import read_request
from db_table_functions.db_tbl_da_tester import read_actions, read_reviews
from db_table_functions.db_tbl_da_understand import read_confirmed_record
from db_table_functions.db_tbl_da_workspace import read_file_versions
from pydantic_classes.da_handoff_models import CriterionFact, FileFact, SummaryFacts


def hand_edited_paths(
    tested: dict[str, str], scanned: dict[str, set[str]], tested_kind: str
) -> set[str]:
    """Planned files whose last tested text came from the developer.

    `tested` is path -> last tested fingerprint, `scanned` is path -> fingerprints of the
    `scanned` rows (his re-scans). A file counts when a scanned fingerprint equals the tested one,
    or, after a Check my edits run, when he has any scanned text for it."""
    found = set()
    for path in tested:
        fingerprints = scanned.get(path, set())
        if tested[path] in fingerprints or (tested_kind == "check" and fingerprints):
            found.add(path)
    return found


def gather_summary_facts(conn: sqlite3.Connection, request_id: str) -> SummaryFacts:
    request = read_request(conn, request_id)
    version = _top_record_version(conn, request_id)
    record = read_confirmed_record(conn, request_id, version)
    state = read_build_state(conn, request_id)
    approach = _accepted_approach(conn, request_id)
    build = _tested_build(conn, request_id, state.build_number if state else 0)
    tested = get_last_tested_fingerprints(conn, request_id)
    kind = read_tested(conn, request_id)["last_tested_kind"]
    facts = SummaryFacts(
        request_id=request_id,
        record_version=version,
        summary=record.title or record.objective[:100],
        kind=record.kind,
        capability=record.capability,
        named_senior=record.named_senior,
        capability_confirmed=record.capability_confirmed,
        no_negative_reason=record.no_negative_reason,
        follows_request_id=request.follows_request_id,
        build_number=build,
    )
    facts = _with_tests(conn, facts, request_id, build)
    facts = _with_tester(conn, facts, request_id, build)
    facts = _with_files(conn, facts, request_id, approach, tested, kind)
    facts = _with_decisions(facts, approach)
    return _with_enhance(conn, facts, request_id, record)


def _top_record_version(conn: sqlite3.Connection, request_id: str) -> int:
    row = conn.execute(
        "SELECT MAX(version) AS top FROM da_request_records WHERE request_id = ?", (request_id,)
    ).fetchone()
    return row["top"] or 1


def _accepted_approach(conn: sqlite3.Connection, request_id: str):
    state = read_approach_state(conn, request_id)
    versions = {v.approach_version: v for v in read_approach_versions(conn, request_id)}
    number = state.accepted_approach_version if state else 0
    return versions.get(number) or (versions[max(versions)] if versions else None)


def _tested_build(conn: sqlite3.Connection, request_id: str, current: int) -> int:
    return read_tested(conn, request_id)["last_tested_build"] or current


def _with_tests(conn, facts: SummaryFacts, request_id: str, build: int) -> SummaryFacts:
    """Criteria -> tests -> results from the plan and the last round's sandbox outcomes."""
    plan = read_latest_plan(conn, request_id)
    rounds = read_rounds(conn, request_id, build) if build else []
    results = {}
    if rounds and rounds[-1].layer_b:
        for outcome in rounds[-1].layer_b.tests:
            ids = case_ids_from_method(outcome.name)
            if ids:
                results[ids[0]] = outcome.result == "pass"
    per = {}
    for case in plan.cases if plan else []:
        item = per.setdefault(case.criterion_id, CriterionFact(criterion_id=case.criterion_id))
        item.tests += 1
        item.passed += 1 if results.get(case.test_id) else 0
    yours = sum(1 for case in plan.cases if case.source == "developer") if plan else 0
    return facts.model_copy(
        update={"criteria": sorted(per.values(), key=lambda x: x.criterion_id), "yours": yours}
    )


def _with_tester(conn, facts: SummaryFacts, request_id: str, build: int) -> SummaryFacts:
    reviews = read_reviews(conn, request_id, build) if build else []
    if not reviews:
        return facts
    review = reviews[-1]
    actions = read_actions(conn, request_id, build)
    accepted = [a for a in actions if a.action == "accepted"]
    risks = [
        f"{a.finding_id}: {a.reason} (accepted by {a.actor}, "
        f"{a.created_at.date().isoformat() if a.created_at else 'unknown date'})"
        for a in accepted
    ]
    kept = [f for f in review.findings if f.kept]
    overruled = [a for a in actions if a.action == "overruled"]
    must_fixed, should_fixed = _fixed_counts(reviews)
    return facts.model_copy(
        update={
            "tester_label": review.label,
            "must_fixed": must_fixed,
            "should_fixed": should_fixed,
            "overruled": len(overruled),
            "overruled_by": overruled[-1].actor if overruled else "",
            "accepted": len(accepted),
            "fyi": sum(1 for f in kept if f.severity == "fyi"),
            "accepted_risks": risks,
            "zones": list(review.zone_warnings),
        }
    )


def _fixed_counts(reviews: list) -> tuple[int, int]:
    """Findings of any earlier review that the newest review no longer lists were fixed. The same
    finding is recognised by check, file and quote (the F-numbers restart in every review)."""

    def key(item) -> tuple:
        return (item.check, item.file, item.quote)

    still = {key(f) for f in reviews[-1].findings if f.kept}
    seen: dict[tuple, str] = {}
    for review in reviews[:-1]:
        for item in review.findings:
            if item.kept and key(item) not in still:
                seen[key(item)] = item.severity
    return (
        sum(1 for s in seen.values() if s == "must_fix"),
        sum(1 for s in seen.values() if s == "should_fix"),
    )


def _with_files(conn, facts, request_id, approach, tested, kind) -> SummaryFacts:
    if approach is None:
        return facts
    scanned = {}
    for path in tested:
        rows = [v for v in read_file_versions(conn, request_id, path) if v.kind == "scanned"]
        scanned[path] = {v.fingerprint for v in rows}
    edited = hand_edited_paths(tested, scanned, kind)
    files = [
        FileFact(path=f.path, is_new=f.action == "create", hand_edited=f.path in edited)
        for f in approach.plan.files
    ]
    return facts.model_copy(update={"files": files})


def _with_decisions(facts: SummaryFacts, approach) -> SummaryFacts:
    if approach is None:
        return facts
    reuses = [
        f"RU-{d.hit_id}: {d.decision}, {d.reason}" for d in approach.plan.reuse_decisions
    ]
    decisions = [f"DD-{n}: {d.question} {d.choice}" for n, d in enumerate(approach.decisions, 1)]
    return facts.model_copy(update={"reuses": reuses, "decisions": decisions})


def _with_enhance(conn, facts: SummaryFacts, request_id: str, record) -> SummaryFacts:
    changes: dict = {}
    if record.freshness.override == "intentional":
        changes["accepted_risks"] = [
            *facts.accepted_risks,
            "Local changes confirmed as intentional",
        ]
    elif record.freshness.override == "unchecked":
        changes["accepted_risks"] = [
            *facts.accepted_risks,
            "Freshness not checked: Bitbucket main unreachable",
        ]
    net = read_latest_safety_net(conn, request_id)
    if net is not None:
        changes["safety_net"] = len(net.net.cases)
        changes["gaps"] = [f"{item.item} ({item.reason})" for item in net.net.not_covered]
    found = read_latest_result(conn, request_id)
    if found is not None and found.impact is not None and not found.impact.available:
        changes["impact_unchecked"] = True
    return facts.model_copy(update=changes)
