"""Phase 9 step 11: Discover with impact (tests 9-23 to 9-26 flow part, spec section 7). The
reference copy is a made-up folder written by each test; no AI or internet."""

import pytest

from agents import da_discover_flow as discover
from agents import da_enhance_flow as enhance
from agents import da_understand_flow as understand
from agents.da_approach_checks import compute_warnings
from agents.da_discover_queries import MAX_QUERIES, build_queries
from agents.da_impact import LIMITS_LINE
from agents.da_search_index import FakeSearchIndex, IndexData, IndexPiece
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_discovery import get_results
from db_table_functions.db_tbl_da_understand import get_session
from pydantic_classes.da_approach_models import ApproachReply
from pydantic_classes.da_request_record_models import RequestRecord
from pydantic_classes.da_workspace_models import FileFact
from tests import da_play

pytestmark = pytest.mark.usefixtures("published_rulebook")

LIMITS = "src/agents/limits_expiry_report.py"
DIRECT = (
    "from agents.limits_expiry_report import format_expiry\n\n\n"
    "def show():\n    return format_expiry(1)\n"
)
ALIASED = (
    "import agents.limits_expiry_report as lim\n\n\n"
    "def run():\n    return lim.format_expiry(2)\n"
)


def write(folder, relative, text):
    target = folder / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@pytest.fixture
def reference(tmp_path):
    folder = tmp_path / "reference"
    write(folder, "src/agents/report_screen.py", DIRECT)
    write(folder, "src/agents/login_banner.py", ALIASED)  # a caller inside the Login zone
    write(folder, LIMITS, "def format_expiry(day):\n    return day\n")  # the target: skipped
    return folder


def confirmed_enhance(settings):
    """An enhance request taken through Find, freshness and Understand to a saved record."""
    text = (settings.fake_main_dir / LIMITS).read_text(encoding="utf-8")
    piece = IndexPiece(
        piece_no=0, path=LIMITS, symbol="format_expiry", line_start=1, kind="code",
        language="python", snippet="def format_expiry(day): date text",
    )
    index = FakeSearchIndex(IndexData(build_id="t", built_at="", pieces=(piece,)))
    started = enhance.start_enhance_request(settings)
    found = enhance.find_program(
        settings, started.request_id, "limits_expiry_report", started.revision, index=index
    )
    done = enhance.confirm_targets(settings, found.request_id, [LIMITS], {}, found.revision)
    fact = FileFact(path=LIMITS, exists=True, parent_exists=True, text=text)
    fresh = enhance.run_freshness(settings, done.request_id, [fact], done.revision)
    request_id = fresh.request_id
    enhance.start_understand(settings, request_id, fresh.revision)
    answers = ["It shows the date.", "Show the month name.", "Keep it", "Date in, text out.", ""]
    view = understand.submit_form(
        settings, request_id, answers, get_session(settings.db_path, request_id).revision
    )
    view = da_play.choose(settings, view, view.choices[0])
    view = understand.set_functions_in_scope(
        settings, request_id, ["format_expiry"], view.revision
    )
    return da_play.choose(settings, view, understand.PROCEED_OPTION).request.request_id


def round_one(settings, request_id):
    return discover.start_discovery(settings, request_id, 0)


def get_latest_result(db_path, request_id):
    return get_results(db_path, request_id)[-1]


# --- the queries ---


def test_an_enhance_record_searches_for_its_targets_and_symbols_within_the_cap():
    record = RequestRecord(
        request_id="CVDA-2026-0001", rulebook_version=1, kind="enhance", targets=[LIMITS],
        functions_in_scope=["format_expiry", "days_left"], title="Fix the date",
        objective="Show the month", expected_behaviour="Month name",
        references=["r1", "r2", "r3"],
    )

    queries = build_queries(record, hint="")

    labels = [q.label() for q in queries]
    assert f"exact: {LIMITS}" in labels and "exact: format_expiry days_left" in labels
    assert len(queries) <= MAX_QUERIES
    new = record.model_copy(update={"kind": "new"})
    assert all(LIMITS not in q.text for q in build_queries(new))


def test_a_hint_is_still_first_for_an_enhance_record():
    record = RequestRecord(
        request_id="CVDA-2026-0001", rulebook_version=1, kind="fix", targets=[LIMITS],
        functions_in_scope=["a"],
    )

    assert build_queries(record, hint="month names")[0].text == "month names"


# --- 9-23: impact stored with the round ---


def test_9_23_impact_rows_are_stored_with_the_round_and_audited(make_settings, reference):
    settings = make_settings(sandbox_source_dir=reference)
    request_id = confirmed_enhance(settings)

    view = round_one(settings, request_id)

    result = get_latest_result(settings.db_path, request_id)
    assert result.impact is not None and result.impact.available
    found = {(r.caller_path, r.kind) for r in result.impact.rows}
    assert found == {
        ("src/agents/report_screen.py", "direct"),
        ("src/agents/login_banner.py", "direct"),
    }
    assert LIMITS not in {r.caller_path for r in result.impact.rows}  # the target is skipped
    assert view.messages[-1].text.startswith("Impact: 2 caller(s) found")
    audit = {e.event_type: e.details for e in list_audit_events(settings.db_path, request_id)}
    assert audit["impact_found"]["direct"] == 2 and audit["impact_found"]["more"] == 0
    assert LIMITS_LINE.startswith("Impact is found by reading the code")


def test_a_new_program_request_has_no_impact(make_settings, reference):
    settings = make_settings(sandbox_source_dir=reference)
    request_id = da_play.to_confirmed(settings).request.request_id

    discover.start_discovery(settings, request_id, 0)

    assert get_latest_result(settings.db_path, request_id).impact is None
    events = [e.event_type for e in list_audit_events(settings.db_path, request_id)]
    assert "impact_found" not in events


# --- 9-25: no reference copy ---


def test_9_25_no_reference_copy_says_so_and_the_request_continues(make_settings, tmp_path):
    settings = make_settings(sandbox_source_dir=tmp_path / "does-not-exist")
    request_id = confirmed_enhance(settings)

    view = round_one(settings, request_id)

    result = get_latest_result(settings.db_path, request_id)
    assert result.impact is not None and not result.impact.available
    assert view.messages[-1].text == "Impact: Impact could not be checked."
    assert view.status_label  # Discover still reached its normal outcome
    assert result.impact.rows == []


# --- 9-26: a caller in a flag-for-review zone ---


def plan(path):
    return ApproachReply.model_validate(
        {
            "summary": "Change the date text.",
            "files": [{"path": path, "action": "modify", "purpose": "Month name"}],
            "libraries": [], "needs_people": [],
        }
    )


def test_9_26_a_caller_in_a_zone_adds_that_zone_with_a_reason(
    make_settings, reference, seed_rulebook
):
    settings = make_settings(sandbox_source_dir=reference)
    request_id = confirmed_enhance(settings)
    round_one(settings, request_id)
    result = get_latest_result(settings.db_path, request_id)

    warnings, zones = compute_warnings(plan(LIMITS), seed_rulebook.policy, result)

    assert zones == ["Login"]
    assert any("a caller is in this zone" in warning for warning in warnings)


def test_a_zone_touched_by_the_plan_itself_is_not_added_twice(
    make_settings, reference, seed_rulebook
):
    settings = make_settings(sandbox_source_dir=reference)
    request_id = confirmed_enhance(settings)
    round_one(settings, request_id)
    result = get_latest_result(settings.db_path, request_id)

    warnings, zones = compute_warnings(
        plan("src/agents/login_banner.py"), seed_rulebook.policy, result
    )

    assert zones == ["Login"]
    assert sum("Touches Login" in warning for warning in warnings) == 1
