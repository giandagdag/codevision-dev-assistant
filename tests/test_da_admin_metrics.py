"""Phase 11c step 1: the health numbers (spec 11-39 to 11-43, 11-45), on made-up databases."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agents import da_approach_flow as approach_flow
from agents import da_build_agent as build_agent
from agents import da_build_flow as build_flow
from agents import da_build_loop as build_loop
from agents import da_enhance_flow as enhance
from agents import da_tester_flow as tester_flow
from agents.da_admin_metrics import (
    NO_DATA,
    WINDOW_30_DAYS,
    WINDOW_ALL,
    health_report,
    window_start,
)
from agents.da_enhance_help import request_help as enhance_help
from db_table_functions.da_db import open_db, to_db_time
from db_table_functions.db_tbl_da_audit import ensure_audit_table, insert_audit_event
from db_table_functions.db_tbl_da_build import (
    close_build_run,
    ensure_build_tables,
    insert_build_run,
    insert_round,
)
from db_table_functions.db_tbl_da_enhance import read_enhance_state, save_enhance_state
from db_table_functions.db_tbl_da_requests import create_request, update_request
from db_table_functions.db_tbl_da_tester import count_kept_cites
from db_table_functions.db_tbl_da_workspace import ensure_workspace_tables
from pydantic_classes.da_build_models import (
    BuildRun,
    LayerAProblem,
    LayerAResult,
    LayerBResult,
    RoundRecord,
    TestOutcome,
)
from tests.da_approach_play import at_review, discovery_confirmed_id
from tests.da_build_play import ready_with_workspace

pytestmark = pytest.mark.usefixtures("published_rulebook")

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
GOOD_B = LayerBResult(tests=[TestOutcome(name="test_a", result="pass")])
BAD_B = LayerBResult(tests=[TestOutcome(name="test_a", result="fail", message="boom")])


def new_request(db_path, when=NOW, title="A made-up change"):
    return create_request(db_path, title, "dev-0001", now=when).request_id


def add_build(
    db_path, request_id, number=1, *, ended=NOW, rounds_used=1, kind="build", round_one="pass"
):
    """A closed build. round_one: "pass", "fail", "zero_tests", "timeout", "layer_a" or None."""
    layers = {
        "pass": (LayerAResult(), GOOD_B),
        "fail": (LayerAResult(), BAD_B),
        "zero_tests": (LayerAResult(), LayerBResult()),
        "timeout": (LayerAResult(), LayerBResult(timed_out=True, tests=GOOD_B.tests)),
        "layer_a": (
            LayerAResult(problems=[LayerAProblem(code="A5", path="a.py", text="eval")]),
            GOOD_B,
        ),
    }
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        run = BuildRun(
            request_id=request_id,
            build_number=number,
            approach_version=1,
            started_at=ended - timedelta(minutes=5),
            kind=kind,
        )
        insert_build_run(conn, run)
        if round_one:
            layer_a, layer_b = layers[round_one]
            record = RoundRecord(
                request_id=request_id,
                build_number=number,
                round=1,
                layer_a=layer_a,
                layer_b=layer_b,
            )
            insert_round(conn, record, ended)
        close_build_run(
            conn,
            request_id,
            number,
            ended_at=ended,
            rounds_used=rounds_used,
            result_status="READY_FOR_REVIEW",
            label="Ready for your review",
            stop_reason="",
        )


def sql(db_path, statement, params=()):
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        ensure_audit_table(conn)
        ensure_workspace_tables(conn)
        conn.execute(statement, params)


def add_record(db_path, request_id, version, kind="new", when=NOW):
    sql(
        db_path,
        "INSERT INTO da_request_records (request_id, version, record, confirmed_by, confirmed_at)"
        " VALUES (?, ?, ?, 'dev-0001', ?)",
        (request_id, version, json.dumps({"kind": kind}), to_db_time(when)),
    )


def add_scanned(db_path, request_id, path, version=1, when=NOW):
    sql(
        db_path,
        "INSERT INTO da_workspace_files (request_id, path, file_version, kind, text, fingerprint,"
        " line_ending, mode, approach_version, created_at)"
        " VALUES (?, ?, ?, 'scanned', 'x = 1', 'f', 'lf', 'x', 1, ?)",
        (request_id, path, version, to_db_time(when)),
    )


def add_finding(db_path, request_id, check, severity="should_fix", cites="", kept=1, when=NOW,
                finding_id="F-1"):
    sql(
        db_path,
        "INSERT INTO da_tester_findings (request_id, build_number, review_number, finding_id,"
        " check_number, severity, file, line, quote, cites, message, made_by, kept, reject_reason,"
        " fixable, created_at) VALUES (?, 1, 1, ?, ?, ?, 'a.py', 1, 'q', ?, 'm', 'tester', ?, '',"
        " 1, ?)",
        (request_id, finding_id, check, severity, cites, kept, to_db_time(when)),
    )


def add_review(db_path, request_id, number, result="done", when=NOW):
    sql(
        db_path,
        "INSERT INTO da_tester_reviews (request_id, build_number, review_number, round, model,"
        " calls, prompt_chars, attempts, result, checks, zone_warnings, label, created_at)"
        " VALUES (?, 1, ?, 1, 'fake', 1, 1, 1, ?, '[]', '[]', 'Ready', ?)",
        (request_id, number, result, to_db_time(when)),
    )


# --- 11-39: the numbers from known rows ---


def test_11_39_four_closed_builds_two_passing_in_round_one(db_path):
    first = new_request(db_path)
    second = new_request(db_path)
    add_build(db_path, first, 1, rounds_used=1, round_one="pass")
    add_build(db_path, first, 2, rounds_used=3, round_one="fail")
    add_build(db_path, second, 1, rounds_used=1, round_one="pass")
    add_build(db_path, second, 2, rounds_used=2, round_one="layer_a")
    add_record(db_path, first, 1)
    add_record(db_path, first, 3)
    add_record(db_path, second, 1)
    add_scanned(db_path, first, "src/a.py")
    add_scanned(db_path, first, "src/b.py")
    add_scanned(db_path, first, "src/a.py", version=2)  # the same file again: counted once

    report = health_report(db_path, WINDOW_ALL, NOW)

    assert report.first_round_pass.value == 50
    assert report.first_round_pass.text.startswith("50%")
    assert report.fix_rounds.value == pytest.approx((0 + 2 + 0 + 1) / 4)
    assert report.revisions.value == pytest.approx((2 + 0) / 2)
    assert report.files_edited.value == 2
    assert "1 of 2 requests (50%)" in report.files_edited.text
    assert report.requests.value == 2


def test_only_closed_build_and_rebuild_runs_count(db_path):
    request_id = new_request(db_path)
    add_build(db_path, request_id, 1, round_one="pass")
    add_build(db_path, request_id, 2, kind="rebuild", round_one="fail", rounds_used=2)
    add_build(db_path, request_id, 3, kind="check", round_one="pass")
    with open_db(db_path) as conn:  # an open build: started, never closed
        insert_build_run(
            conn,
            BuildRun(request_id=request_id, build_number=4, approach_version=1, started_at=NOW),
        )

    report = health_report(db_path, WINDOW_ALL, NOW)

    assert report.first_round_pass.text == "50% (1 of 2 closed builds)"


def test_a_stopped_run_without_a_round_counts_as_not_passed(db_path):
    request_id = new_request(db_path)
    add_build(db_path, request_id, 1, round_one="pass")
    add_build(db_path, request_id, 2, round_one=None, rounds_used=0)

    report = health_report(db_path, WINDOW_ALL, NOW)

    assert report.first_round_pass.value == 50
    assert report.fix_rounds.value == 0  # rounds_used 0 never goes below zero


@pytest.mark.parametrize("round_one", ["zero_tests", "timeout", "fail", "layer_a"])
def test_round_one_passes_only_by_the_build_loops_own_test(db_path, round_one):
    request_id = new_request(db_path)
    add_build(db_path, request_id, 1, round_one=round_one)

    assert health_report(db_path, WINDOW_ALL, NOW).first_round_pass.value == 0


# --- 11-40: nothing yet ---


def test_11_40_an_empty_database_says_no_data_yet_everywhere(db_path):
    report = health_report(db_path, WINDOW_ALL, NOW)

    for metric in report.all_metrics:
        assert metric.text == NO_DATA, metric.label
        assert metric.value is None


def test_a_fresh_install_with_only_the_rulebook_tables_does_not_crash(db_path):
    # published_rulebook made the rulebook tables only: no request, build or Tester table yet.
    with open_db(db_path) as conn:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert "da_build_runs" not in tables

    assert health_report(db_path, WINDOW_30_DAYS, NOW).requests.text == NO_DATA


# --- requests by kind ---


def test_requests_are_split_by_kind_from_the_enhance_state(db_path, make_settings):
    settings = make_settings()
    new_request(db_path)
    started = enhance.start_enhance_request(settings)  # an Enhance state, no confirmed record
    fixing = enhance.start_enhance_request(settings)
    with open_db(db_path) as conn:
        state = read_enhance_state(conn, fixing.request_id)
        save_enhance_state(conn, state.model_copy(update={"kind": "fix"}), state.revision, NOW)

    report = health_report(db_path, WINDOW_ALL)

    assert started.request_id != fixing.request_id
    assert dict(report.requests.items) == {"new": 1, "enhance": 1, "fix": 1}
    assert report.requests.text == "3 (new 1, enhance 1, fix 1)"


# --- 11-41: Get help ---


def test_11_41_get_help_from_the_enhance_screen_counts_once(db_path, make_settings):
    settings = make_settings()
    started = enhance.start_enhance_request(settings)
    new_request(db_path)  # a request that never asked for help
    enhance_help(settings, started.request_id, started.revision)

    report = health_report(db_path, WINDOW_ALL)

    assert report.escalations.value == 1
    assert dict(report.escalations.items)["Get help"] == 1
    assert report.escalations.note == ""  # the old "Get help only" note is gone (10-48)


def test_11_41_get_help_from_approach_counts_once_not_twice(db_path, make_settings):
    settings = make_settings()
    request_id = discovery_confirmed_id(settings)
    view = at_review(settings, request_id)
    approach_flow.request_help(settings, request_id, view.revision)  # writes status AND event

    assert health_report(db_path, WINDOW_ALL).escalations.value == 1


def test_a_dispute_is_counted_under_dispute_and_a_get_help_next_to_it_under_get_help(
    db_path, make_settings, monkeypatch
):
    settings = make_settings()
    disputed_id = ready_with_workspace(settings)[0]
    monkeypatch.setattr(build_agent, "FAKE_SWITCHES", frozenset({"review_must_fix_always"}))
    build_flow.start_build(settings, disputed_id, build_flow.get_revision(settings, disputed_id))
    assert build_loop.run_build(settings, disputed_id) == "done"
    view = tester_flow.get_tester_view(settings, disputed_id)
    must = next(r.finding.finding_id for r in view.rows if r.finding.severity == "must_fix")
    tester_flow.dispute_finding(
        settings, disputed_id, build_flow.get_revision(settings, disputed_id), must, "It is fine"
    )
    tester_flow.send_disputes(settings, disputed_id, build_flow.get_revision(settings, disputed_id))

    report = health_report(db_path, WINDOW_ALL)  # Phase 10: a dispute opens a row of its own
    assert report.escalations.value == 1
    assert dict(report.escalations.items)["Dispute"] == 1

    helped = enhance.start_enhance_request(settings)
    enhance_help(settings, helped.request_id, helped.revision)

    report = health_report(db_path, WINDOW_ALL)
    assert report.escalations.value == 2
    assert dict(report.escalations.items)["Get help"] == 1


def test_get_help_shows_even_when_no_request_was_created_in_the_window(db_path, make_settings):
    settings = make_settings()
    old = enhance.start_enhance_request(settings)
    enhance_help(settings, old.request_id, old.revision)  # the help event is stamped now
    sql(db_path, "UPDATE da_requests SET created_at = ?", (to_db_time(NOW - timedelta(days=400)),))

    report = health_report(db_path, WINDOW_30_DAYS, datetime.now(UTC))

    assert report.requests.text == NO_DATA  # the request itself is older than the window
    assert report.escalations.value == 1  # but the help was pressed inside it


def test_a_recent_scan_on_an_old_request_never_makes_the_share_pass_100(db_path):
    old = new_request(db_path, NOW - timedelta(days=40))
    fresh = new_request(db_path, NOW)
    add_scanned(db_path, old, "a.py", when=NOW)
    add_scanned(db_path, fresh, "b.py", when=NOW)

    report = health_report(db_path, WINDOW_30_DAYS, NOW)

    assert report.files_edited.text == "1 files; 1 of 1 requests (100%)"


def test_another_status_move_is_not_a_get_help(db_path):
    request_id = new_request(db_path)
    with open_db(db_path) as conn:
        ensure_audit_table(conn)
        update_request(conn, request_id, now=NOW, status="CLARIFICATION_IN_PROGRESS")
        insert_audit_event(
            conn, request_id, "system", "status_changed",
            {"from": "DRAFT", "to": "CLARIFICATION_IN_PROGRESS"}, NOW,
        )

    report = health_report(db_path, WINDOW_ALL, NOW)

    assert report.escalations.value == 0
    assert report.escalations.text == "0"  # requests exist, so a real zero


# --- 11-42: findings and rules cited ---


def test_11_42_findings_by_check_and_severity_and_rules_cited(db_path):
    request_id = new_request(db_path)
    add_finding(db_path, request_id, 1, "must_fix", finding_id="F-1")
    add_finding(db_path, request_id, 4, "should_fix", cites="CV-PY-001", finding_id="F-2")
    add_finding(db_path, request_id, 6, "fyi", cites="CV-PY-002", finding_id="F-3")
    add_finding(db_path, request_id, 6, "should_fix", cites="CV-PY-002", finding_id="F-4")
    add_finding(db_path, request_id, 6, "must_fix", cites="CV-PY-009", kept=0, finding_id="F-5")
    add_review(db_path, request_id, 1)
    add_review(db_path, request_id, 2, result="unable")

    report = health_report(db_path, WINDOW_ALL, NOW)

    assert report.findings_by_check.items == (
        ("1. Every criterion has a test", 1),
        ("4. Approach decisions followed", 1),
        ("6. Judgement rules kept", 2),
    )
    assert report.findings_by_severity.items == (("must_fix", 1), ("should_fix", 2), ("fyi", 1))
    assert report.rules_cited.items[0] == ("CV-PY-002", 2)  # the rejected finding is not counted
    assert ("CV-PY-009", 1) not in report.rules_cited.items
    assert report.unable_reviews.text == "1 of 2 reviews"


def test_rules_cited_shows_the_top_five_only(db_path):
    request_id = new_request(db_path)
    for number in range(1, 8):
        add_finding(db_path, request_id, 6, cites=f"CV-PY-00{number}", finding_id=f"F-{number}")

    assert len(health_report(db_path, WINDOW_ALL, NOW).rules_cited.items) == 5


def test_kept_cites_without_a_window_is_unchanged(db_path):
    request_id = new_request(db_path)
    add_finding(db_path, request_id, 6, cites="CV-PY-001", when=NOW - timedelta(days=90))
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        assert count_kept_cites(conn) == {"CV-PY-001": 1}
        assert count_kept_cites(conn, to_db_time(NOW - timedelta(days=30))) == {}


# --- 11-43: the time window ---


def test_window_start_is_none_for_all_time_and_thirty_days_back_otherwise():
    assert window_start(WINDOW_ALL, NOW) is None
    assert window_start(WINDOW_30_DAYS, NOW) == to_db_time(NOW - timedelta(days=30))


def test_11_43_rows_older_than_thirty_days_only_count_in_all_time(db_path):
    old = new_request(db_path, NOW - timedelta(days=31))
    recent = new_request(db_path, NOW - timedelta(days=29))
    add_build(db_path, old, 1, ended=NOW - timedelta(days=31), round_one="fail", rounds_used=3)
    add_build(db_path, recent, 1, ended=NOW - timedelta(days=29), round_one="pass")
    add_record(db_path, old, 4, when=NOW - timedelta(days=31))
    add_record(db_path, recent, 1, when=NOW - timedelta(days=29))
    add_scanned(db_path, old, "src/a.py", when=NOW - timedelta(days=31))
    add_finding(db_path, old, 6, cites="CV-PY-001", when=NOW - timedelta(days=31))
    add_review(db_path, old, 1, result="unable", when=NOW - timedelta(days=31))

    month = health_report(db_path, WINDOW_30_DAYS, NOW)
    everything = health_report(db_path, WINDOW_ALL, NOW)

    assert month.requests.value == 1 and everything.requests.value == 2
    assert month.first_round_pass.value == 100 and everything.first_round_pass.value == 50
    assert month.fix_rounds.value == 0 and everything.fix_rounds.value == 1
    assert month.revisions.value == 0 and everything.revisions.value == pytest.approx(1.5)
    assert month.files_edited.value == 0 and everything.files_edited.value == 1
    assert month.findings_by_check.text == NO_DATA and everything.findings_by_check.value == 1
    assert month.rules_cited.text == NO_DATA and everything.rules_cited.value == 1
    assert month.unable_reviews.text == NO_DATA and everything.unable_reviews.value == 1


# --- 11-45: the new SQL file stays inside the rules ---


def test_the_metrics_files_neither_touch_the_rulebook_table_nor_call_an_ai():
    src = Path(__file__).resolve().parents[1] / "src"
    files = [
        src / "db_table_functions" / "db_tbl_da_metrics.py",
        src / "agents" / "da_admin_metrics.py",
    ]
    for file in files:
        text = file.read_text(encoding="utf-8")
        assert "da_rulebook_versions" not in text, file
        for word in ("get_llm_client", "get_build_client", "get_tester_client", ".complete("):
            assert word not in text, (file, word)
        for word in ("INSERT", "UPDATE", "DELETE", "DROP"):
            assert word not in text, (file, word)  # upper case: the SQL words, not the prose


def test_the_metrics_leave_every_row_as_it_was(db_path):
    request_id = new_request(db_path)
    add_build(db_path, request_id)
    add_finding(db_path, request_id, 6, cites="CV-PY-001")

    def snapshot():
        with open_db(db_path) as conn:
            return [
                tuple(row)
                for table in ("da_requests", "da_build_runs", "da_tester_findings")
                for row in conn.execute(f"SELECT * FROM {table}")
            ]

    before = snapshot()
    health_report(db_path, WINDOW_ALL, NOW)

    assert snapshot() == before
