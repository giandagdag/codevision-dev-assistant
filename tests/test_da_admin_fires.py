"""AF-14 and AF-15: rule cards and "fires in N%" (6 of 10 reviews in 30 days is 60%, amber)."""

from datetime import UTC, datetime, timedelta

from agents.da_admin_cited import fires_in
from db_table_functions.da_db import open_db, to_db_time
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_requests import create_request
from layouts.da_admin_page import TAB_CODING, tab_content
from tests.test_da_admin_page import all_text

NOW = datetime(2026, 11, 15, tzinfo=UTC)


def add_reviews(db_path, cited_in: int, total: int, days_ago: int = 1):
    request = create_request(db_path, "Change x", "dev-0001")
    when = to_db_time(NOW - timedelta(days=days_ago))
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        for n in range(1, total + 1):
            conn.execute(
                "INSERT INTO da_tester_reviews VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (request.request_id, 1, n, 1, "m", 1, 1, 1, "done", "[]", "[]", "", when),
            )
            if n <= cited_in:
                conn.execute(
                    "INSERT INTO da_tester_findings (request_id, build_number, review_number,"
                    " finding_id, check_number, severity, file, line, quote, cites, message,"
                    " made_by, kept, reject_reason, fixable, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (request.request_id, 1, n, f"f{n}", 1, "fyi", "a.py", 1, "q", "CV-PY-007",
                     "m", "tester", 1, "", 0, when),
                )


def test_fires_in_is_the_share_of_reviews(db_path, published_rulebook):
    add_reviews(db_path, cited_in=6, total=10)
    assert fires_in(db_path, NOW) == {"CV-PY-007": 60}


def test_old_reviews_do_not_count(db_path, published_rulebook):
    add_reviews(db_path, cited_in=6, total=10, days_ago=40)
    assert fires_in(db_path, NOW) == {}


def test_rule_cards_show_the_card_and_the_amber_warning(published_rulebook):
    rule = published_rulebook.rulebook.rules[0].rule_id
    text = all_text(tab_content(TAB_CODING, published_rulebook, fires={rule: 60}))
    assert "⚠️ fires in 60%" in text
    for word in ("Why", "Tags", "Checked by", "Source", "Fires in", "Good", "Bad"):
        assert word in text
    quiet = all_text(tab_content(TAB_CODING, published_rulebook, fires={rule: 50}))
    assert "⚠️" not in quiet and "fires in 50%" in quiet
