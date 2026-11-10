"""Phase 9 step 9a: start, switch offer, find, pick, fix and confirm (tests 9-1 flow part, 9-2 to
9-11, 9-49). No AI is called by any of these; the search index is a made-up in-memory one."""

import pytest

from agents import da_enhance_flow as flow
from agents import da_understand_flow as understand
from agents.da_search_index import FakeSearchIndex, IndexData, IndexPiece
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_enhance import EnhanceError, list_unassigned
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from tests import da_play

pytestmark = pytest.mark.usefixtures("published_rulebook")

LIMITS = "src/agents/limits_expiry_report.py"
BATCH = "src/agents/limits_batch.py"
ODD = "src/agents/tidy_helper.py"


def piece(number, path, symbol="", snippet="", **flags):
    return IndexPiece(
        piece_no=number, path=path, symbol=symbol, line_start=1, kind="code", language="python",
        snippet=snippet, **flags,
    )


@pytest.fixture
def index():
    pieces = (
        piece(0, LIMITS, "format_expiry", "def format_expiry(day, month, year): date text"),
        piece(1, LIMITS, "days_left", "def days_left(expiry_day, today_day): days remaining"),
        piece(2, BATCH, "run_batch", "def run_batch(): runs the nightly batch of limits"),
        piece(3, ODD, "tidy_values", "def tidy_values(): cleans up stray values"),
        piece(4, "src/agents/old_report.py", "old_report", "def old_report(): deprecated report",
              deprecated=True),
        piece(5, "src/agents/secret_report.py", "secret_report", "def secret_report(): report"),
        piece(6, "src/agents/restricted_report.py", "restricted_report",
              "def restricted_report(): report", restricted=True),
    )
    return FakeSearchIndex(IndexData(build_id="test", built_at="", pieces=pieces))


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def started(settings):
    return flow.start_enhance_request(settings)


# --- start (9-1, flow part) ---


def test_9_1_card_2_creates_a_request_of_kind_enhance_at_e_find(settings):
    view = flow.start_enhance_request(settings)

    assert view.kind == "enhance" and view.step == "e_find"
    assert view.label == "FIND THE PROGRAM"
    assert view.request_id.startswith("CVDA-")
    assert view.messages[-1].text == flow.WELCOME
    assert view.searches_left == 3
    events = [e.event_type for e in list_audit_events(settings.db_path, view.request_id)]
    assert events == ["request_created", "enhance_started"]


# --- find (9-5 to 9-8, 9-10) ---


def test_9_5_a_message_naming_a_file_stem_gives_a_best_match_found_by_name(
    settings, started, index
):
    view = flow.find_program(
        settings, started.request_id, "limits_expiry_report shows the wrong date",
        started.revision, index=index,
    )

    best = view.candidates[0]
    assert best.path == LIMITS and best.best_match and best.how_found.startswith("name")
    assert view.step == "e_pick"
    assert "Best match: `src/agents/limits_expiry_report.py`" in view.messages[-1].text
    assert "`Limits` capability" in view.messages[-1].text
    assert len([c for c in view.candidates if c.how_found == "name"]) <= 5


def test_9_6_a_description_only_gives_meaning_candidates_merged_by_path(
    settings, started, index
):
    view = flow.find_program(
        settings, started.request_id, "the nightly batch that sets limits", started.revision,
        index=index,
    )

    paths = [c.path for c in view.candidates]
    assert BATCH in paths and len(paths) == len(set(paths))
    assert len([c for c in view.candidates if c.how_found == "meaning"]) <= 3
    assert not any(c.best_match for c in view.candidates)
    assert "possible program" in view.messages[-1].text


def test_9_7_deprecated_restricted_and_secret_looking_files_are_never_candidates(
    settings, started, index
):
    view = flow.find_program(
        settings, started.request_id, "report old_report secret_report restricted_report",
        started.revision, index=index,
    )

    shown = {c.path for c in view.candidates}
    assert shown.isdisjoint(
        {"src/agents/old_report.py", "src/agents/secret_report.py",
         "src/agents/restricted_report.py"}
    )


def test_9_8_a_candidate_matching_a_catalog_pattern_shows_capability_and_senior(
    settings, started, index
):
    view = flow.find_program(
        settings, started.request_id, "limits_batch", started.revision, index=index
    )

    first = view.candidates[0]
    assert (first.path, first.capability) == (BATCH, "Limits")
    assert first.named_senior == "Limits capability lead"


def test_9_10_three_searches_with_nothing_found_leave_only_get_help(settings, started, index):
    view = started
    for _ in range(3):
        view = flow.find_program(
            settings, view.request_id, "zzzz qqqq", view.revision, index=index
        )
    assert view.candidates == [] and view.step == "e_find" and view.searches_left == 0
    assert view.messages[-1].text.startswith("I could not find that program")

    with pytest.raises(EnhanceError, match="Get help"):
        flow.find_program(settings, view.request_id, "zzzz", view.revision, index=index)


def test_a_search_with_a_secret_looking_message_is_refused_and_a_stale_window_too(
    settings, started, index
):
    with pytest.raises(EnhanceError):
        flow.find_program(settings, started.request_id, "  ", started.revision, index=index)
    flow.find_program(settings, started.request_id, "limits_batch", started.revision, index=index)
    with pytest.raises(StaleRevisionError):
        flow.find_program(
            settings, started.request_id, "limits_batch", started.revision, index=index
        )


# --- confirm (9-9, 9-11) ---


def found(settings, started, index, text="limits_expiry_report tidy_values"):
    return flow.find_program(settings, started.request_id, text, started.revision, index=index)


def test_confirming_a_catalog_program_saves_the_target_with_its_capability(
    settings, started, index
):
    view = found(settings, started, index)

    done = flow.confirm_targets(settings, view.request_id, [LIMITS], {}, view.revision)

    target = done.targets[0]
    assert (target.path, target.capability, target.capability_confirmed) == (LIMITS, "Limits", True)
    assert target.named_senior == "Limits capability lead"
    audit = {e.event_type: e.details for e in list_audit_events(settings.db_path, view.request_id)}
    assert audit["targets_confirmed"]["paths"] == [LIMITS]
    assert list_unassigned_rows(settings) == []


def list_unassigned_rows(settings):
    with open_db(settings.db_path) as conn:
        return list_unassigned(conn)


def test_9_9_a_program_in_no_capability_needs_a_pick_and_opens_one_unassigned_row(
    settings, started, index
):
    view = found(settings, started, index)
    assert ODD in [c.path for c in view.candidates]

    with pytest.raises(EnhanceError, match="Pick the capability"):
        flow.confirm_targets(settings, view.request_id, [ODD], {}, view.revision)
    with pytest.raises(EnhanceError, match="Pick the capability"):
        flow.confirm_targets(settings, view.request_id, [ODD], {ODD: "Nonsense"}, view.revision)
    done = flow.confirm_targets(settings, view.request_id, [ODD], {ODD: "Reports"}, view.revision)

    target = done.targets[0]
    assert (target.capability, target.capability_confirmed) == ("Reports", False)
    assert "not yet confirmed by Admin" in done.messages[-1].text
    rows = list_unassigned_rows(settings)
    assert [(r.path, r.picked_capability, r.state) for r in rows] == [(ODD, "Reports", "open")]
    events = [e.event_type for e in list_audit_events(settings.db_path, view.request_id)]
    assert "capability_picked" in events


def test_9_9_a_second_request_on_the_same_path_links_to_the_same_row(settings, index):
    first = flow.start_enhance_request(settings)
    second = flow.start_enhance_request(settings)
    for request in (first, second):
        view = flow.find_program(
            settings, request.request_id, "tidy_values", request.revision, index=index
        )
        flow.confirm_targets(settings, view.request_id, [ODD], {ODD: "Uploads"}, view.revision)

    rows = list_unassigned_rows(settings)
    assert len(rows) == 1 and rows[0].picked_capability == "Uploads"
    assert rows[0].request_id == first.request_id  # the open row stays the first one


def test_9_11_a_target_outside_the_allowed_folders_or_not_python_is_refused(
    settings, started
):
    outside = FakeSearchIndex(
        IndexData(
            build_id="t", built_at="",
            pieces=(
                piece(0, "docs/limits_helper.py", "limits_helper", "def limits_helper(): x"),
                piece(1, "src/agents/limits_notes.txt", "limits_notes", "limits notes text"),
            ),
        )
    )
    view = flow.find_program(
        settings, started.request_id, "limits_helper limits_notes", started.revision, index=outside
    )
    assert {c.path for c in view.candidates} == {"docs/limits_helper.py",
                                                 "src/agents/limits_notes.txt"}

    with pytest.raises(EnhanceError, match="not in an allowed folder"):
        flow.confirm_targets(
            settings, view.request_id, ["docs/limits_helper.py"], {}, view.revision
        )
    with pytest.raises(EnhanceError, match=r"only Python \(\.py\)"):
        flow.confirm_targets(
            settings, view.request_id, ["src/agents/limits_notes.txt"], {}, view.revision
        )


def test_a_path_no_search_showed_cannot_be_confirmed(settings, started, index):
    view = found(settings, started, index)

    with pytest.raises(EnhanceError, match="Search for it first"):
        flow.confirm_targets(
            settings, view.request_id, ["src/agents/other.py"], {}, view.revision
        )


def test_a_new_search_clears_an_earlier_confirmation(settings, started, index):
    view = found(settings, started, index)
    done = flow.confirm_targets(settings, view.request_id, [LIMITS], {}, view.revision)

    again = flow.find_program(settings, view.request_id, "limits_batch", done.revision, index=index)

    assert again.targets == [] and again.step == "e_pick"


# --- This is a fix (9-49) ---


def test_9_49_this_is_a_fix_sets_kind_fix_and_prefills_what_should_change(
    settings, started, index
):
    view = flow.find_program(
        settings, started.request_id, "limits_expiry_report shows the wrong date",
        started.revision, index=index,
    )

    done = flow.mark_as_fix(settings, view.request_id, view.revision)

    assert done.kind == "fix"
    assert done.change_prefill == (
        "Make it work as intended: limits_expiry_report shows the wrong date"
    )
    fresh = flow.start_enhance_request(settings)  # still at e_find: nothing to mark yet
    with pytest.raises(EnhanceError, match="not available"):
        flow.mark_as_fix(settings, fresh.request_id, fresh.revision)


# --- the switch offer from card 1 (9-2, 9-3, 9-4) ---


@pytest.fixture
def card_1(settings, monkeypatch, index):
    monkeypatch.setattr(flow, "get_search_index", lambda _settings: index)
    view = understand.create_understand_request(
        settings, "limits_expiry_report shows the wrong date at weekends"
    )
    return da_play.submit_form(settings, view)


def offers(settings, request_id):
    return [
        m.text for m in flow.list_messages(settings.db_path, request_id)
        if "Switch to Enhance or fix?" in m.text
    ]


def test_9_2_a_card_1_opening_naming_a_file_stem_shows_the_switch_offer(settings, card_1):
    request_id = card_1.request.request_id

    assert offers(settings, request_id) == [
        "This sounds like a change to `src/agents/limits_expiry_report.py`, which already "
        "exists. Switch to Enhance or fix?"
    ]
    events = [e.event_type for e in list_audit_events(settings.db_path, request_id)]
    assert events.count("switch_offered") == 1


def test_9_2_no_offer_when_nothing_matches_by_name(settings, monkeypatch, index):
    monkeypatch.setattr(flow, "get_search_index", lambda _settings: index)
    view = understand.create_understand_request(settings, "Can we support Excel uploads?")

    view = da_play.submit_form(settings, view)

    assert offers(settings, view.request.request_id) == []


def test_9_3_switch_keeps_the_number_sets_kind_enhance_and_lists_the_offered_file_first(
    settings, card_1
):
    request_id = card_1.request.request_id

    view = flow.switch_to_enhance(settings, request_id, card_1.revision)

    assert view.request_id == request_id
    assert (view.kind, view.step) == ("enhance", "e_pick")
    assert view.candidates[0].path == LIMITS and view.candidates[0].capability == "Limits"
    events = [e.event_type for e in list_audit_events(settings.db_path, request_id)]
    assert "switched_to_enhance" in events
    assert flow.get_enhance_view(settings, request_id) is not None
    # The opening statement is kept in the chat.
    assert flow._first_developer_text(settings, request_id).startswith("limits_expiry_report")


def test_9_4_no_this_is_new_is_audited_and_the_offer_never_comes_again(
    settings, card_1, monkeypatch, index
):
    request_id = card_1.request.request_id

    flow.decline_switch(settings, request_id, card_1.revision)

    events = [e.event_type for e in list_audit_events(settings.db_path, request_id)]
    assert "switch_declined" in events
    assert flow.maybe_offer_switch(settings, request_id, index=index) is None
    assert len(offers(settings, request_id)) == 1
    with pytest.raises(EnhanceError, match="no switch offer"):
        flow.switch_to_enhance(settings, request_id, card_1.revision)


def test_an_answered_offer_cannot_be_answered_twice_and_a_stale_window_is_refused(
    settings, card_1
):
    request_id = card_1.request.request_id
    with pytest.raises(StaleRevisionError):
        flow.switch_to_enhance(settings, request_id, card_1.revision + 5)

    flow.switch_to_enhance(settings, request_id, card_1.revision)

    with pytest.raises(EnhanceError, match="no switch offer"):
        flow.decline_switch(settings, request_id, card_1.revision)


def test_9_2_the_offer_makes_no_ai_call(settings, monkeypatch, index):
    def no_ai(*_args, **_kwargs):
        raise AssertionError("The switch offer must not call the AI.")

    monkeypatch.setattr(flow, "get_search_index", lambda _settings: index)
    view = understand.create_understand_request(settings, "limits_expiry_report is wrong")
    view = da_play.submit_form(settings, view)  # the form's own scripted call is allowed here
    monkeypatch.setattr(understand, "interpret", no_ai)
    monkeypatch.setattr(understand, "_interpret", no_ai)

    # The offer was shown by the form submit above. Asking again does nothing and calls nothing.
    assert flow.maybe_offer_switch(settings, view.request.request_id, index=index) is None
    assert len(offers(settings, view.request.request_id)) == 1


def test_a_missing_search_index_never_breaks_the_form(settings, monkeypatch):
    def broken(_settings):
        raise flow.IndexFormatError("broken index")

    monkeypatch.setattr(flow, "get_search_index", broken)
    view = understand.create_understand_request(settings, "limits_expiry_report is wrong")

    # get_search_index is called inside the offer; an index problem must not fail the form.
    assert flow.maybe_offer_switch(settings, view.request.request_id) is None
