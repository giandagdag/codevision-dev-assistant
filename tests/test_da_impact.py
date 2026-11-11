"""Phase 9, step 4: impact by `ast` (9-23, 9-24, 9-25 pure part, 9-26 pure part)."""

import shutil
from pathlib import Path

from agents.da_impact import (
    LIMITS_LINE,
    UNAVAILABLE_TEXT,
    find_impact,
    locked_signatures,
    module_name,
    summary_line,
    zone_reasons,
)
from pydantic_classes.da_rulebook_models import FlagReviewZone

DATA = Path(__file__).resolve().parents[1] / "src" / "data"
REFERENCE = DATA / "da_fake_codevision"
TARGET = "src/agents/limits_expiry_report.py"
SCOPE = {TARGET: ["format_expiry", "days_left", "ExpiryReport.build_line"]}


def run(reference=REFERENCE, scope=SCOPE, caps=(), zones=(), cap=30):
    return find_impact(reference, scope, list(caps), list(zones), cap)


def as_tuples(result):
    return [(r.kind, r.caller_path, r.function_in_scope) for r in result.rows]


def test_module_name_drops_src_and_the_extension():
    assert module_name("src/agents/limits_expiry_report.py") == "agents.limits_expiry_report"
    assert module_name("src\\agents\\x.py") == "agents.x"


def test_9_23_direct_aliased_possible_and_imports_only_rows_and_the_target_is_skipped():
    result = run()

    assert as_tuples(result) == [
        ("direct", "src/agents/limits_batch.py", "days_left"),
        ("direct", "src/layouts/limits_screen.py", "format_expiry"),
        ("possible", "src/agents/limits_batch.py", "ExpiryReport.build_line"),
        ("imports_only", "src/layouts/limits_menu.py", ""),
    ]
    assert all(r.caller_path != TARGET for r in result.rows)
    assert result.available and result.more == 0
    assert "not by running it" in LIMITS_LINE
    assert "getattr" in LIMITS_LINE


def test_9_23_rows_name_the_caller_function_and_line():
    screen = next(r for r in run().rows if r.caller_path.endswith("limits_screen.py"))
    batch = next(r for r in run().rows if r.function_in_scope == "days_left")

    assert screen.caller_function == "show_expiry"
    assert screen.line == 7
    assert batch.caller_function == "run_batch"


def test_a_function_not_in_scope_is_not_listed():
    result = run(scope={TARGET: ["format_expiry"]})

    assert as_tuples(result) == [
        ("direct", "src/layouts/limits_screen.py", "format_expiry"),
        # limits_batch calls only functions that are not in scope, so it falls back to imports.
        ("imports_only", "src/agents/limits_batch.py", ""),
        ("imports_only", "src/layouts/limits_menu.py", ""),
    ]


def test_9_24_the_cap_keeps_the_most_important_rows_and_counts_the_rest():
    result = run(cap=2)

    assert [r.kind for r in result.rows] == ["direct", "direct"]
    assert result.more == 2
    assert summary_line(result) == "2 caller(s) found and 2 more."


def test_9_25_no_reference_copy_is_reported_not_raised(tmp_path):
    for reference in (None, tmp_path / "missing"):
        result = run(reference=reference)

        assert result.available is False
        assert result.rows == []
        assert summary_line(result) == UNAVAILABLE_TEXT


def test_9_26_a_caller_in_a_zone_gives_a_zone_reason(tmp_path, seed_rulebook):
    shutil.copytree(REFERENCE, tmp_path / "ref")
    login = tmp_path / "ref" / "src" / "layouts" / "login_page.py"
    lines = [
        "from agents.limits_expiry_report import days_left",
        "",
        "",
        "def page():",
        "    return days_left(1, 0)",
        "",
    ]
    login.write_text("\n".join(lines), encoding="utf-8")
    zones = seed_rulebook.policy.flag_review_zones

    result = run(reference=tmp_path / "ref", zones=zones)

    row = next(r for r in result.rows if r.caller_path.endswith("login_page.py"))
    assert row.zone == "Login"
    assert zone_reasons(result.rows) == {"Login": "a caller is in this zone"}


def test_callers_show_their_capability(seed_rulebook):
    result = run(caps=seed_rulebook.policy.capabilities)

    assert {r.capability for r in result.rows} == {"Limits"}


def test_signature_lock_unless_the_caller_file_is_also_planned():
    rows = run().rows

    assert locked_signatures(rows, set()) == ["days_left", "format_expiry"]
    assert locked_signatures(rows, {"src/layouts/LIMITS_screen.py"}) == ["days_left"]


def test_a_file_that_does_not_parse_is_skipped(tmp_path):
    shutil.copytree(REFERENCE, tmp_path / "ref")
    (tmp_path / "ref" / "src" / "agents" / "broken.py").write_text("def (:\n", encoding="utf-8")

    assert run(reference=tmp_path / "ref").rows == run().rows


def test_a_zone_that_matches_nothing_gives_no_reason():
    zone = FlagReviewZone(name="Z", description="d", path_patterns=["*nothing*"])

    assert zone_reasons(run(zones=[zone]).rows) == {}
