"""The developer's actions on the Tester's report (spec 7-12, 7-17 to 7-21, 7-31)."""

import pytest

from agents import da_build_agent as agent
from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents import da_tester_flow as tflow
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import read_approach_state
from db_table_functions.db_tbl_da_build import BuildError
from db_table_functions.db_tbl_da_tester import read_reviews
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from pydantic_classes.da_build_models import (
    LABEL_NOT_PASSING,
    LABEL_READY,
    LABEL_UNABLE,
    LABEL_WITH_WARNINGS,
)
from tests.da_approach_play import events_of
from tests.da_build_play import (
    build_state,
    chat,
    event_types,
    ready_with_workspace,
    request_status,
    run_row,
)

pytestmark = pytest.mark.usefixtures("published_rulebook")

GOOD_REASON = "I checked it and the plan is fine"


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return ready_with_workspace(settings)[0]


def built(settings, request_id, monkeypatch=None, *switches):
    if monkeypatch is not None:
        monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset(switches))
    flow.start_build(settings, request_id, flow.get_revision(settings, request_id))
    assert loop.run_build(settings, request_id) == "done"


def revision(settings, request_id):
    return flow.get_revision(settings, request_id)


def should_fix_id(settings, request_id):
    rows = tflow.get_tester_view(settings, request_id).rows
    return next(r.finding.finding_id for r in rows if r.finding.severity == "should_fix")


def open_item(settings, request_id):
    with open_db(settings.db_path) as conn:
        return read_approach_state(conn, request_id).open_item


# --- reading the report ---


def test_the_view_shows_the_label_the_findings_and_the_dropped_ones(settings, request_id):
    built(settings, request_id)

    view = tflow.get_tester_view(settings, request_id)

    assert view.layer_c_ran and view.label == LABEL_WITH_WARNINGS
    assert [r.finding.severity for r in view.rows] == ["should_fix", "fyi"]
    assert len(view.dropped) == 1 and len(view.earlier) == 1  # round 2's review is "earlier"
    assert view.summary.startswith("Tester review of round 3: 0 Must fix, 1 Should fix, 1 FYI")
    assert not view.can_rerun


def test_a_request_without_a_build_has_an_empty_view(settings, request_id):
    view = tflow.get_tester_view(settings, request_id)

    assert view.review is None and view.rows == [] and not view.can_rerun


# --- accept and reopen (7-17, 7-18, 7-19) ---


def test_7_17_accepting_the_last_should_fix_turns_the_label_green(settings, request_id):
    built(settings, request_id)
    finding = should_fix_id(settings, request_id)

    tflow.accept_finding(settings, request_id, revision(settings, request_id), finding, GOOD_REASON)

    view = tflow.get_tester_view(settings, request_id)
    assert view.label == LABEL_READY
    assert [r.state for r in view.rows] == ["accepted", "open"]
    assert view.rows[0].reason == GOOD_REASON
    types = event_types(settings, request_id)
    assert "finding_accepted" in types and "label_changed" in types
    changed = events_of(settings, request_id, "label_changed")[-1].details
    assert (changed["from"], changed["to"]) == (LABEL_WITH_WARNINGS, LABEL_READY)
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"


@pytest.mark.parametrize("reason", ["short", "", "x" * 301, "    ab    "])
def test_7_18_a_reason_that_is_too_short_or_too_long_is_refused(settings, request_id, reason):
    built(settings, request_id)
    finding = should_fix_id(settings, request_id)
    before = revision(settings, request_id)

    with pytest.raises(BuildError, match="reason of 10 to 300"):
        tflow.accept_finding(settings, request_id, before, finding, reason)

    assert revision(settings, request_id) == before
    assert tflow.get_tester_view(settings, request_id).label == LABEL_WITH_WARNINGS


def test_7_19_reopen_makes_it_open_and_the_label_yellow_again(settings, request_id):
    built(settings, request_id)
    finding = should_fix_id(settings, request_id)
    tflow.accept_finding(settings, request_id, revision(settings, request_id), finding, GOOD_REASON)

    tflow.reopen_finding(settings, request_id, revision(settings, request_id), finding)

    view = tflow.get_tester_view(settings, request_id)
    assert view.label == LABEL_WITH_WARNINGS and view.rows[0].state == "open"
    assert "finding_reopened" in event_types(settings, request_id)
    labels = [e.details["to"] for e in events_of(settings, request_id, "label_changed")]
    assert labels == [LABEL_READY, LABEL_WITH_WARNINGS]


def test_an_fyi_cannot_be_accepted_and_a_not_accepted_finding_cannot_be_reopened(
    settings, request_id
):
    built(settings, request_id)
    finding = should_fix_id(settings, request_id)
    fyi = next(
        r.finding.finding_id
        for r in tflow.get_tester_view(settings, request_id).rows
        if r.finding.severity == "fyi"
    )

    with pytest.raises(BuildError, match="is a FYI"):
        tflow.accept_finding(settings, request_id, revision(settings, request_id), fyi, GOOD_REASON)
    with pytest.raises(BuildError, match="nothing to reopen"):
        tflow.reopen_finding(settings, request_id, revision(settings, request_id), finding)
    with pytest.raises(BuildError, match="no finding F-99"):
        tflow.accept_finding(
            settings, request_id, revision(settings, request_id), "F-99", GOOD_REASON
        )


def test_7_31_an_old_window_is_refused(settings, request_id):
    built(settings, request_id)
    finding = should_fix_id(settings, request_id)
    old = revision(settings, request_id)
    tflow.accept_finding(settings, request_id, old, finding, GOOD_REASON)

    with pytest.raises(StaleRevisionError):
        tflow.reopen_finding(settings, request_id, old, finding)
    with pytest.raises(StaleRevisionError):
        tflow.rerun_review(settings, request_id, old)


# --- dispute (7-20, 7-21) ---


def test_7_21_disputing_a_must_fix_goes_to_a_senior(settings, request_id, monkeypatch):
    built(settings, request_id, monkeypatch, "review_must_fix_always")
    assert request_status(settings, request_id) == "NOT_PASSING"
    view = tflow.get_tester_view(settings, request_id)
    must = next(r.finding.finding_id for r in view.rows if r.finding.severity == "must_fix")

    tflow.dispute_finding(settings, request_id, revision(settings, request_id), must, GOOD_REASON)

    assert request_status(settings, request_id) == "ESCALATION_REQUIRED"
    assert open_item(settings, request_id) == f"Disputed Must fix: {must}"
    assert build_state(settings, request_id).step == "escalated"
    assert "finding_disputed" in event_types(settings, request_id)
    assert f"Dispute {must}: {GOOD_REASON}" in chat(settings, request_id, "developer")


def test_7_20_a_must_fix_cannot_be_accepted(settings, request_id, monkeypatch):
    built(settings, request_id, monkeypatch, "review_must_fix_always")
    view = tflow.get_tester_view(settings, request_id)
    must = next(r.finding.finding_id for r in view.rows if r.finding.severity == "must_fix")

    with pytest.raises(BuildError, match="is a Must fix"):
        tflow.accept_finding(settings, request_id, revision(settings, request_id), must, "A" * 20)
    with pytest.raises(BuildError, match="no finding F-99"):
        tflow.dispute_finding(
            settings, request_id, revision(settings, request_id), "F-99", GOOD_REASON
        )


def test_a_should_fix_cannot_be_disputed(settings, request_id):
    built(settings, request_id)

    with pytest.raises(BuildError, match="is a Should fix"):
        tflow.dispute_finding(
            settings,
            request_id,
            revision(settings, request_id),
            should_fix_id(settings, request_id),
            GOOD_REASON,
        )


# --- run the review again (7-12) ---


def test_7_12_run_again_after_unable_makes_a_new_review_and_uses_no_round(
    settings, request_id, monkeypatch
):
    built(settings, request_id, monkeypatch, "review_unusable")
    first = tflow.get_tester_view(settings, request_id)
    assert first.label == LABEL_UNABLE and first.can_rerun
    used = run_row(settings, request_id).rounds_used
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"review_empty"}))

    tflow.rerun_review(settings, request_id, revision(settings, request_id))

    view = tflow.get_tester_view(settings, request_id)
    assert view.label == LABEL_READY and not view.can_rerun
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"
    assert run_row(settings, request_id).rounds_used == used  # no round used
    with open_db(settings.db_path) as conn:
        reviews = read_reviews(conn, request_id, 1)
    assert [r.review_number for r in reviews] == [1, 2]
    assert "tester_review_rerun" in event_types(settings, request_id)
    moves = [
        (e.details["from"], e.details["to"])
        for e in events_of(settings, request_id, "status_changed")
    ][-2:]
    assert moves == [("READY_FOR_REVIEW", "TESTER_REVIEW"), ("TESTER_REVIEW", "READY_FOR_REVIEW")]


def test_a_rerun_that_finds_a_must_fix_ends_not_passing(settings, request_id, monkeypatch):
    built(settings, request_id, monkeypatch, "review_unusable")
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"review_must_fix_always"}))

    tflow.rerun_review(settings, request_id, revision(settings, request_id))

    assert request_status(settings, request_id) == "NOT_PASSING"
    assert tflow.get_tester_view(settings, request_id).label == LABEL_NOT_PASSING


def test_a_rerun_is_refused_when_the_label_is_not_unable(settings, request_id):
    built(settings, request_id)

    with pytest.raises(BuildError, match="only works when the label is Unable to assess"):
        tflow.rerun_review(settings, request_id, revision(settings, request_id))


def test_a_rerun_when_the_ai_does_not_answer_changes_nothing(settings, request_id, monkeypatch):
    built(settings, request_id, monkeypatch, "review_unusable")
    before = revision(settings, request_id)
    reviews = len(events_of(settings, request_id, "tester_review_done"))
    monkeypatch.setattr(agent, "FAKE_SWITCHES", frozenset({"no_answer"}))

    with pytest.raises(BuildError, match="Nothing was changed"):
        tflow.rerun_review(settings, request_id, before)

    assert revision(settings, request_id) == before
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"
    assert len(events_of(settings, request_id, "tester_review_done")) == reviews
