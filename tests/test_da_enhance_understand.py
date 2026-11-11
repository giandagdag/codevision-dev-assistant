"""Phase 9 step 10: Understand in enhance mode (tests 9-18, 9-20, 9-21 flow, 9-22). The AI is the
fake provider; the made-up main folder shipped under src/data is the program's text."""

import json

import pytest

from agents import da_build_agent as build_agent
from agents import da_enhance_flow as enhance
from agents import da_understand_flow as understand
from agents.da_search_index import FakeSearchIndex, IndexData, IndexPiece
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_understand import UnderstandError, get_session, read_session
from pydantic_classes.da_request_record_models import RequestRecord
from pydantic_classes.da_workspace_models import FileFact
from tests import da_play

pytestmark = pytest.mark.usefixtures("published_rulebook")

LIMITS = "src/agents/limits_expiry_report.py"


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def fresh(settings):
    """An enhance request at e_fresh: found, confirmed and checked against the shipped main."""
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
    view = enhance.run_freshness(settings, done.request_id, [fact], done.revision)
    assert view.step == "e_fresh"
    return view


def session_of(settings, request_id):
    return get_session(settings.db_path, request_id)


# --- 9-18: the today-draft call ---


def test_9_18_one_today_draft_call_sends_function_bodies_and_no_chat(
    settings, fresh, monkeypatch
):
    prompts = []
    original = build_agent.ScriptedBuildClient.complete

    def spy(self, prompt, system=None):
        prompts.append(prompt)
        return original(self, prompt, system)

    monkeypatch.setattr(build_agent.ScriptedBuildClient, "complete", spy)

    enhance.start_understand(settings, fresh.request_id, fresh.revision)

    assert len(prompts) == 1
    assert "def format_expiry" in prompts[0]  # a function body, line-numbered
    assert "limits_expiry_report" in prompts[0]  # what he typed at Find: the request text
    assert "Is this the right program" not in prompts[0]  # no chat lines
    record = session_of(settings, fresh.request_id).record
    assert record.kind == "enhance" and record.targets == [LIMITS]
    assert record.today and "```" not in record.today and "def " not in record.today
    assert record.capability == "Limits" and record.freshness.result == "equal"
    assert record.functions_in_scope  # the AI's guess, real symbols only
    events = [e.event_type for e in list_audit_events(settings.db_path, fresh.request_id)]
    assert "today_drafted" in events


def test_9_18_an_unusable_draft_twice_leaves_the_box_empty(settings, fresh, monkeypatch):
    monkeypatch.setattr(build_agent, "FAKE_SWITCHES", frozenset({"today_unusable"}))

    view = enhance.start_understand(settings, fresh.request_id, fresh.revision)

    record = session_of(settings, fresh.request_id).record
    assert record.today == "" and record.functions_in_scope == []
    assert "write it yourself" in view.messages[-1].text


def test_start_understand_moves_the_request_and_cannot_run_twice(settings, fresh):
    view = enhance.start_understand(settings, fresh.request_id, fresh.revision)

    assert session_of(settings, fresh.request_id).step == "form"
    shown = understand.get_understand_view(settings, fresh.request_id)
    assert shown.status_label != "" and shown.input_mode == "form"
    with pytest.raises(UnderstandError):
        enhance.start_understand(settings, fresh.request_id, view.revision)


# --- 9-20: the form ---


def test_9_20_the_enhance_form_has_the_new_boxes_and_numbers_the_nc_items():
    titles = [title for _, title in understand.form_boxes("enhance")]

    assert titles[0] == "What does it do today?" and titles[1] == "What should change?"
    assert titles[2].startswith("What must NOT change?")
    assert understand.form_boxes("fix") == understand.form_boxes("enhance")
    assert understand.form_boxes("new") == understand.FORM_BOXES


def submit(settings, request_id, keep):
    session = session_of(settings, request_id)
    answers = ["It shows the date.", "Show the month name.", keep, "Date in, text out.", ""]
    return understand.submit_form(settings, request_id, answers, session.revision)


def test_9_20_submitting_saves_today_and_numbered_nc_items(settings, fresh):
    enhance.start_understand(settings, fresh.request_id, fresh.revision)

    submit(settings, fresh.request_id, "Keep the day number format\n- Keep the year as 4 digits\n")

    record = session_of(settings, fresh.request_id).record
    assert record.today == "It shows the date."
    assert [(i.id, i.text) for i in record.must_not_change] == [
        ("NC-1", "Keep the day number format"),
        ("NC-2", "Keep the year as 4 digits"),
    ]


def test_nothing_special_gives_no_nc_items_and_too_many_items_are_refused(settings, fresh):
    enhance.start_understand(settings, fresh.request_id, fresh.revision)

    with pytest.raises(understand.FormError) as error:
        submit(settings, fresh.request_id, "\n".join(f"item {n}" for n in range(1, 10)))
    assert 3 in error.value.problems and "At most 8" in error.value.problems[3]
    assert session_of(settings, fresh.request_id).step == "form"  # nothing was saved

    submit(settings, fresh.request_id, "Nothing special")
    assert session_of(settings, fresh.request_id).record.must_not_change == []


def test_the_ai_cannot_change_the_enhance_fields(settings, fresh):
    enhance.start_understand(settings, fresh.request_id, fresh.revision)
    before = session_of(settings, fresh.request_id).record

    submit(settings, fresh.request_id, "Keep it")

    after = session_of(settings, fresh.request_id).record
    assert (after.kind, after.targets, after.capability) == (
        before.kind, before.targets, before.capability,
    )


# --- 9-21: functions in scope ---


def to_checkpoint(settings, request_id):
    view = submit(settings, request_id, "Keep it")
    return da_play.choose(settings, view, view.choices[0])


def test_9_21_a_symbol_not_in_the_split_is_refused_and_one_must_stay_ticked(settings, fresh):
    enhance.start_understand(settings, fresh.request_id, fresh.revision)
    checkpoint = to_checkpoint(settings, fresh.request_id)

    with pytest.raises(UnderstandError, match="not a function in the chosen programs"):
        understand.set_functions_in_scope(
            settings, fresh.request_id, ["no_such_function"], checkpoint.revision
        )
    with pytest.raises(UnderstandError, match="Tick at least one"):
        understand.set_functions_in_scope(settings, fresh.request_id, [], checkpoint.revision)

    view = understand.set_functions_in_scope(
        settings, fresh.request_id, ["format_expiry"], checkpoint.revision
    )
    assert view.record.functions_in_scope == ["format_expiry"]
    events = [e.event_type for e in list_audit_events(settings.db_path, fresh.request_id)]
    assert "functions_in_scope_set" in events


def test_proceed_needs_a_function_in_scope_and_then_saves_record_v1(settings, fresh, monkeypatch):
    monkeypatch.setattr(build_agent, "FAKE_SWITCHES", frozenset({"today_unusable"}))
    enhance.start_understand(settings, fresh.request_id, fresh.revision)
    checkpoint = to_checkpoint(settings, fresh.request_id)
    assert checkpoint.record.functions_in_scope == []

    with pytest.raises(UnderstandError, match="Tick at least one function"):
        da_play.choose(settings, checkpoint, understand.PROCEED_OPTION)

    ticked = understand.set_functions_in_scope(
        settings, fresh.request_id, ["format_expiry"], checkpoint.revision
    )
    done = da_play.choose(settings, ticked, understand.PROCEED_OPTION)
    assert done.record.kind == "enhance" and done.record.functions_in_scope == ["format_expiry"]
    assert done.record.must_not_change[0].id == "NC-1"


def test_set_functions_in_scope_refuses_a_new_program_request(settings):
    view = da_play.to_checkpoint(settings)

    with pytest.raises(UnderstandError):
        understand.set_functions_in_scope(
            settings, view.request.request_id, ["anything"], view.revision
        )


# --- 9-22: an older record ---


def test_9_22_a_record_saved_before_phase_9_loads_with_empty_new_fields():
    current = RequestRecord(request_id="CVDA-2026-0001", rulebook_version=1)
    old = json.loads(current.model_dump_json())
    for name in ("kind", "targets", "today", "must_not_change", "functions_in_scope",
                 "capability", "capability_confirmed", "named_senior", "freshness"):
        old.pop(name)

    record = RequestRecord.model_validate(old)

    assert (record.kind, record.targets, record.today, record.must_not_change) == (
        "new", [], "", [],
    )
    assert record.functions_in_scope == [] and record.freshness.override == ""


def test_a_new_program_request_still_uses_the_four_old_boxes(settings):
    view = da_play.submit_form(settings, da_play.start(settings))

    assert understand.form_boxes("new") == understand.FORM_BOXES
    assert view.record.today == "" and view.record.must_not_change == []
    with open_db(settings.db_path) as conn:
        assert read_session(conn, view.request.request_id).record.kind == "new"
