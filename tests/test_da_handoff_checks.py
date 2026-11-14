"""Phase 10 step 2: the Handoff findings check (H2) and the fingerprint compare (H4)."""

from datetime import UTC, datetime

import pytest

from agents.da_handoff_checks import compare_fingerprints, findings_check, folder_blockers
from db_table_functions.da_db import begin_write, open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables, insert_build_file
from db_table_functions.db_tbl_da_handoff import get_last_tested_fingerprints
from db_table_functions.db_tbl_da_refine import set_last_tested
from db_table_functions.db_tbl_da_requests import create_request
from pydantic_classes.da_build_models import (
    LABEL_NOT_PASSING,
    LABEL_READY,
    LABEL_UNABLE,
    LABEL_WITH_WARNINGS,
    BuildFile,
)
from pydantic_classes.da_tester_models import Finding, FindingRow

NOW = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)


def row(finding_id: str, severity: str, state: str = "open") -> FindingRow:
    finding = Finding(finding_id=finding_id, check=4, severity=severity, message="made up")
    return FindingRow(finding=finding, state=state)


# --- H2 ---


@pytest.mark.parametrize("label", [LABEL_READY, LABEL_WITH_WARNINGS])
def test_clean_review_passes(label):
    rows = [
        row("F-1", "should_fix", "accepted"),
        row("F-2", "fyi"),
        row("F-3", "must_fix", "overruled"),
    ]
    assert findings_check(label, rows, True) == []


def test_open_must_fix_blocks_and_names_it():
    blockers = findings_check(LABEL_READY, [row("F-1", "must_fix")], True)
    assert [b.kind for b in blockers] == ["must_fix"]
    assert blockers[0].finding_id == "F-1"
    assert "F-1 (Must fix) is still open" in blockers[0].text


def test_open_should_fix_wording():
    blockers = findings_check(LABEL_WITH_WARNINGS, [row("F-3", "should_fix")], True)
    assert blockers[0].text == "F-3 (Should fix) is still open: Fix it or Accept, with reason."


def test_disputed_should_fix_still_blocks():
    assert findings_check(LABEL_READY, [row("F-3", "should_fix", "disputed")], True)


def test_unable_to_assess_names_the_rerun():
    blockers = findings_check(LABEL_UNABLE, [], True)
    assert "Run the Tester review again" in blockers[0].text


def test_not_passing_and_unknown_label_block():
    assert findings_check(LABEL_NOT_PASSING, [], True)[0].kind == "label"
    assert findings_check("", [], True)[0].kind == "label"


def test_unfinished_last_run_blocks():
    assert findings_check(LABEL_READY, [], False)[0].kind == "last_tested"


def test_all_reasons_are_listed_together():
    rows = [row("F-1", "must_fix"), row("F-2", "should_fix")]
    kinds = [b.kind for b in findings_check(LABEL_UNABLE, rows, False)]
    assert kinds == ["label", "must_fix", "should_fix", "last_tested"]


# --- H4 ---


def test_compare_equal_changed_missing_and_extra_ignored():
    planned = ["src/a.py", "src/b.py", "src/c.py"]
    seen = {"src/a.py": "aa", "src/b.py": "XX", "src/extra.py": "zz"}
    expected = {"src/a.py": "aa", "src/b.py": "bb", "src/c.py": "cc"}
    checks = compare_fingerprints(planned, seen, expected)
    assert [(c.path, c.result) for c in checks] == [
        ("src/a.py", "equal"),
        ("src/b.py", "changed"),
        ("src/c.py", "missing"),
    ]
    assert folder_blockers(checks) == [
        "src/b.py: Changed since the last test",
        "src/c.py: Missing",
    ]


def test_all_equal_has_no_blockers():
    checks = compare_fingerprints(["src/a.py"], {"src/a.py": "aa"}, {"src/a.py": "aa"})
    assert folder_blockers(checks) == []


# --- the last tested fingerprints, read from the database ---


def test_last_tested_fingerprints(db_path, published_rulebook):
    request_id = create_request(db_path, "Add a limit check", "dev-home-01", NOW).request_id
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        assert get_last_tested_fingerprints(conn, request_id) == {}
        begin_write(conn)
        for number, fp in ((1, "old"), (2, "new")):
            insert_build_file(
                conn,
                BuildFile(
                    request_id=request_id,
                    build_number=number,
                    round=1,
                    path="src/a.py",
                    kind="code",
                    text="x",
                    fingerprint=fp,
                    made_by="generator",
                ),
                NOW,
            )
        conn.commit()
        # No Refine yet: the current build counts (build state absent here, so still empty).
        set_last_tested(conn, request_id, 1, "build", NOW)
        assert get_last_tested_fingerprints(conn, request_id) == {"src/a.py": "old"}
        set_last_tested(conn, request_id, 2, "check", NOW)
        assert get_last_tested_fingerprints(conn, request_id) == {"src/a.py": "new"}
        conn.commit()
