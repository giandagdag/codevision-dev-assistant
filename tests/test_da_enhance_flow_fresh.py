"""Phase 9 step 9b: the freshness run, the stale buttons, the baseline and the browser read list
(tests 9-12 to 9-17 flow part, 9-48). The main source is a made-up folder; no AI is called."""

import pytest

from agents import da_enhance_flow as flow
from agents.da_main_source import stale_options
from agents.da_search_index import FakeSearchIndex, IndexData, IndexPiece
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_enhance import EnhanceError, read_freshness_checks
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from db_table_functions.db_tbl_da_workspace import read_file_versions
from pydantic_classes.da_enhance_models import FreshnessResult, PathFreshness
from pydantic_classes.da_workspace_models import FileFact

pytestmark = pytest.mark.usefixtures("published_rulebook")

LIMITS = "src/agents/limits_expiry_report.py"
MAIN_TEXT = "def format_expiry(day):\n    return day\n"


@pytest.fixture
def main_dir(tmp_path):
    target = tmp_path / "main" / LIMITS
    target.parent.mkdir(parents=True)
    target.write_bytes(MAIN_TEXT.encode("utf-8"))
    return tmp_path / "main"


@pytest.fixture
def settings(make_settings, main_dir):
    return make_settings(fake_main_dir=main_dir)


@pytest.fixture
def confirmed(settings):
    pieces = (
        IndexPiece(
            piece_no=0, path=LIMITS, symbol="format_expiry", line_start=1, kind="code",
            language="python", snippet="def format_expiry(day): date text",
        ),
    )
    index = FakeSearchIndex(IndexData(build_id="t", built_at="", pieces=pieces))
    started = flow.start_enhance_request(settings)
    found = flow.find_program(
        settings, started.request_id, "limits_expiry_report", started.revision, index=index
    )
    return flow.confirm_targets(settings, found.request_id, [LIMITS], {}, found.revision)


def fact(text=MAIN_TEXT, path=LIMITS, **flags):
    if text is None:
        return FileFact(path=path, exists=False, parent_exists=True)
    return FileFact(path=path, exists=True, parent_exists=True, text=text, **flags)


def baselines(settings, request_id):
    with open_db(settings.db_path) as conn:
        return read_file_versions(conn, request_id, LIMITS)


def checks(settings, request_id):
    with open_db(settings.db_path) as conn:
        return read_freshness_checks(conn, request_id)


def events(settings, request_id):
    return [e.event_type for e in list_audit_events(settings.db_path, request_id)]


# --- 9-12, 9-17: equal copy ---


def test_9_12_an_equal_copy_passes_and_9_17_its_text_becomes_the_baseline(settings, confirmed):
    his = "﻿" + MAIN_TEXT.replace("\n", "\r\n")  # a BOM and CRLF do not count

    view = flow.run_freshness(settings, confirmed.request_id, [fact(his)], confirmed.revision)

    assert view.step == "e_fresh" and view.label == "PROGRAM CONFIRMED"
    assert "Freshness check passed" in view.messages[-1].text
    assert view.stale_options == []
    saved = baselines(settings, view.request_id)
    assert [(v.kind, v.text, v.line_ending) for v in saved] == [("baseline", his, "\r\n")]
    [row] = checks(settings, view.request_id)
    assert row.result.all_equal and row.result.main_source == "fake" and row.result.override == ""
    assert "freshness_checked" in events(settings, view.request_id)


# --- 9-13: differs ---


def test_9_13_a_different_copy_is_stale_and_no_baseline_is_taken(settings, confirmed):
    view = flow.run_freshness(
        settings, confirmed.request_id, [fact(MAIN_TEXT + "# mine\n")], confirmed.revision
    )

    assert view.step == "e_stale" and view.label == "FRESHNESS CHECK"
    text = view.messages[-1].text
    assert LIMITS in text and "git pull" in text and "fresh ZIP" in text
    assert view.stale_options == ["check_again", "intentional"]
    assert baselines(settings, view.request_id) == []


def test_a_path_missing_from_his_folder_offers_only_check_again(settings, confirmed):
    view = flow.run_freshness(settings, confirmed.request_id, [fact(None)], confirmed.revision)

    assert view.step == "e_stale" and view.stale_options == ["check_again"]
    assert "Your folder does not have" in view.messages[-1].text


# --- 9-14: check again ---


def test_9_14_after_updating_the_folder_check_again_passes(settings, confirmed):
    stale = flow.run_freshness(
        settings, confirmed.request_id, [fact(MAIN_TEXT + "# old\n")], confirmed.revision
    )

    again = flow.run_freshness(settings, stale.request_id, [fact()], stale.revision)

    assert again.step == "e_fresh"
    assert len(checks(settings, again.request_id)) == 2
    assert [v.text for v in baselines(settings, again.request_id)] == [MAIN_TEXT]


# --- 9-15: intentional ---


def test_9_15_intentional_moves_on_and_stores_and_audits_the_override(settings, confirmed):
    mine = MAIN_TEXT + "# mine\n"
    stale = flow.run_freshness(settings, confirmed.request_id, [fact(mine)], confirmed.revision)

    view = flow.override_freshness(
        settings, stale.request_id, "intentional", [fact(mine)], stale.revision
    )

    assert view.step == "e_fresh"
    assert checks(settings, view.request_id)[-1].result.override == "intentional"
    assert "freshness_override" in events(settings, view.request_id)
    assert [v.text for v in baselines(settings, view.request_id)] == [mine]
    assert "PR summary" in view.messages[-1].text


def test_an_override_is_refused_when_the_folder_changed_since_the_check(settings, confirmed):
    stale = flow.run_freshness(
        settings, confirmed.request_id, [fact(MAIN_TEXT + "# a\n")], confirmed.revision
    )

    with pytest.raises(EnhanceError, match="changed since the check"):
        flow.override_freshness(
            settings, stale.request_id, "intentional", [fact(MAIN_TEXT + "# b\n")], stale.revision
        )


def test_the_unchecked_choice_is_not_offered_for_a_plain_difference(settings, confirmed):
    stale = flow.run_freshness(
        settings, confirmed.request_id, [fact(MAIN_TEXT + "# a\n")], confirmed.revision
    )

    with pytest.raises(EnhanceError, match="not available"):
        flow.override_freshness(
            settings, stale.request_id, "unchecked", [fact(MAIN_TEXT + "# a\n")], stale.revision
        )


# --- 9-16: main unreachable ---


def test_9_16_main_not_configured_is_never_a_silent_pass(make_settings, main_dir):
    settings = make_settings(fake_main_dir=main_dir, main_source="bitbucket")
    started = flow.start_enhance_request(settings)
    index = FakeSearchIndex(IndexData(build_id="t", built_at="", pieces=(
        IndexPiece(piece_no=0, path=LIMITS, symbol="format_expiry", line_start=1, kind="code",
                   language="python", snippet="def format_expiry(day): x"),
    )))
    found = flow.find_program(
        settings, started.request_id, "limits_expiry_report", started.revision, index=index
    )
    done = flow.confirm_targets(settings, found.request_id, [LIMITS], {}, found.revision)

    stale = flow.run_freshness(settings, done.request_id, [fact()], done.revision)

    assert stale.step == "e_stale"
    assert "could not reach Bitbucket main" in stale.messages[-1].text
    assert stale.stale_options == ["check_again", "unchecked"]
    view = flow.override_freshness(
        settings, stale.request_id, "unchecked", [fact()], stale.revision
    )
    assert view.step == "e_fresh"
    assert checks(settings, view.request_id)[-1].result.override == "unchecked"
    assert "Continue without the check" in [m.text for m in view.messages]


def test_stale_options_rule():
    def result(*states):
        return FreshnessResult(paths=[PathFreshness(path=f"a{i}.py", state=s)
                                      for i, s in enumerate(states)])

    assert stale_options(result("equal")) == ["check_again"]
    assert stale_options(result("not_on_main")) == ["check_again", "intentional"]
    assert stale_options(result("unreachable", "equal")) == ["check_again", "unchecked"]
    assert stale_options(result("differs", "missing_in_folder")) == ["check_again"]


# --- 9-48: the browser read list ---


def test_9_48_only_the_confirmed_targets_may_be_read_and_nothing_else(settings, confirmed):
    assert flow.browser_read_paths(settings, confirmed.request_id) == [LIMITS]

    with pytest.raises(EnhanceError, match="not the confirmed"):
        flow.run_freshness(
            settings, confirmed.request_id,
            [fact(), fact(path="src/agents/other.py")], confirmed.revision,
        )
    with pytest.raises(EnhanceError, match="not the confirmed"):
        flow.run_freshness(
            settings, confirmed.request_id, [fact(path="src/agents/other.py")], confirmed.revision
        )
    assert checks(settings, confirmed.request_id) == []


def test_before_confirming_nothing_may_be_read(settings):
    started = flow.start_enhance_request(settings)

    assert flow.browser_read_paths(settings, started.request_id) == []
    with pytest.raises(EnhanceError, match="not available at this step"):
        flow.run_freshness(settings, started.request_id, [fact()], started.revision)


def test_a_file_too_big_or_not_utf8_or_altered_in_transit_is_refused(settings, confirmed):
    skipped = {"path": LIMITS, "exists": True, "parent_exists": True}
    for bad, match in (
        (FileFact(**skipped, too_big=True), "too big"),
        (FileFact(**skipped, not_utf8=True), "not UTF-8"),
        (fact(fingerprint="0" * 64), "did not arrive intact"),
    ):
        with pytest.raises(EnhanceError, match=match):
            flow.run_freshness(settings, confirmed.request_id, [bad], confirmed.revision)


def test_a_stale_window_is_refused_before_anything_is_read(settings, confirmed):
    flow.run_freshness(settings, confirmed.request_id, [fact()], confirmed.revision)

    with pytest.raises(StaleRevisionError):
        flow.run_freshness(settings, confirmed.request_id, [fact()], confirmed.revision)
