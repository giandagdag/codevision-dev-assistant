"""Lane suggestion, lane start, revision mode, Confirm v2 and Cancel (Phase 8 step 7a).

Tests 8-9, 8-10, 8-11, 8-12, 8-13, 8-14, 8-18, 8-37 (the Refine side)."""

import pytest

from agents import da_refine_lanes as lanes
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_refine import RefineError, read_refines
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from pydantic_classes.da_models import STATUS_READY_FOR_REVIEW, STATUS_REVISION
from tests.da_approach_play import events_of
from tests.da_build_play import chat, request_status
from tests.da_refine_play import lane_reply, records_of, rev, written_request
from tests.da_stub_client import FailingClient, StubClient

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def written(settings):
    return written_request(settings)


def first_criterion(settings, request_id):
    return records_of(settings, request_id)[-1].acceptance_criteria[0].id


def suggest(settings, request_id, client, text="Please change something"):
    return lanes.suggest(settings, request_id, text, rev(settings, request_id), client)


# --- 8-9, 8-10, 8-11: the suggestion ---


def test_8_9_one_lane_call_then_three_buttons_and_no_chat_or_code_in_the_prompt(settings, written):
    request_id, _ = written
    client = StubClient(lane_reply("requirement", "The request itself must change."))

    state = suggest(settings, request_id, client, "Reject files over 5 MB")

    assert state.step == "lane_choice" and state.suggested_lane == "requirement"
    assert request_status(settings, request_id) == STATUS_READY_FOR_REVIEW
    assert len(client.prompts) == 1
    prompt = client.prompts[0]
    assert "Reject files over 5 MB" in prompt
    assert "def " not in prompt and "import " not in prompt  # no code
    assert "Reject files over 5 MB" not in "".join(chat(settings, request_id, "assistant"))
    assert "The request itself must change." in chat(settings, request_id, "assistant")[-1]
    assert events_of(settings, request_id, "lane_suggested")[0].details["lane"] == "requirement"


def test_8_10_a_bug_with_no_criterion_is_shown_as_a_requirement(settings, written):
    request_id, _ = written

    state = suggest(settings, request_id, StubClient(lane_reply("bug", "It is broken.")))

    assert state.suggested_lane == "requirement"
    assert "No criterion covers this" in state.suggested_reason


def test_8_11_an_unusable_reply_twice_gives_no_suggestion_and_pick_one(settings, written):
    request_id, _ = written
    client = StubClient("not json", "still not json")

    state = suggest(settings, request_id, client)

    assert len(client.prompts) == 2
    assert state.lane_unusable and state.suggested_lane == ""
    assert chat(settings, request_id, "assistant")[-1] == "I could not suggest a lane. Pick one."
    assert events_of(settings, request_id, "lane_unusable")


def test_an_ai_that_does_not_answer_gives_no_suggestion_either(settings, written):
    request_id, _ = written

    state = suggest(settings, request_id, FailingClient())

    assert state.lane_unusable
    assert request_status(settings, request_id) == STATUS_READY_FOR_REVIEW


def test_an_empty_or_secret_message_is_refused_before_any_call(settings, written):
    request_id, _ = written
    client = StubClient()

    with pytest.raises(RefineError):
        suggest(settings, request_id, client, "   ")

    assert client.prompts == []


# --- the lane click ---


def test_choosing_a_lane_moves_the_status_and_saves_a_refine_row(settings, written):
    request_id, _ = written
    suggest(settings, request_id, StubClient(lane_reply("requirement")), "Reject big files")

    state = lanes.choose_lane(settings, request_id, "bug", rev(settings, request_id))

    assert request_status(settings, request_id) == STATUS_REVISION
    assert state.step == "bug_start" and state.refine_count == 1
    with open_db(settings.db_path) as conn:
        row = read_refines(conn, request_id)[0]
    assert (row.refine_number, row.suggested_lane, row.chosen_lane) == (1, "requirement", "bug")
    assert row.from_status == STATUS_READY_FOR_REVIEW and row.feedback == "Reject big files"
    details = events_of(settings, request_id, "refine_started")[0].details
    assert details == {"refine": 1, "suggested": "requirement", "chosen": "bug"}


def test_a_lane_needs_a_suggestion_step_first(settings, written):
    request_id, _ = written

    with pytest.raises(RefineError, match="press Refine first"):
        lanes.choose_lane(settings, request_id, "bug", 0)


def test_8_12_the_cap_stops_a_new_refine(settings, written):
    request_id, _ = written
    for _ in range(5):
        suggest(settings, request_id, StubClient(lane_reply("requirement")))
        lanes.choose_lane(settings, request_id, "requirement", rev(settings, request_id))
        lanes.cancel(settings, request_id, rev(settings, request_id))

    with pytest.raises(RefineError, match="refined 5 times"):
        suggest(settings, request_id, StubClient())


# --- 8-13, 8-14, 8-18: revision mode ---

CHANGE_AND_ADD = {
    "criteria_ops": [
        {"op": "change", "id": "AC-2", "then": "a clearer message is shown"},
        {
            "op": "add",
            "kind": "failure",
            "given": "a file over 5 MB",
            "when": "it is uploaded",
            "then": "a message says it is too big",
        },
    ],
    "field_updates": {},
}


def start_requirement_lane(settings, request_id):
    suggest(settings, request_id, StubClient(lane_reply("requirement")), "Reject big files")
    return lanes.choose_lane(settings, request_id, "requirement", rev(settings, request_id))


def test_8_13_the_revision_changes_only_what_it_names_and_shows_a_diff(settings, written):
    request_id, _ = written
    start_requirement_lane(settings, request_id)
    old = records_of(settings, request_id)[-1]
    assert [c.id for c in old.acceptance_criteria][:2] == ["AC-1", "AC-2"]

    client = StubClient(CHANGE_AND_ADD)
    state = lanes.revise(settings, request_id, rev(settings, request_id), client=client)

    assert state.step == "req_checkpoint"
    new = state.pending_record
    assert new.version == old.version + 1
    by_id = {c.id: c for c in new.acceptance_criteria}
    assert by_id["AC-2"].then == "a clearer message is shown"
    new_id = f"AC-{len(old.acceptance_criteria) + 1}"
    assert by_id[new_id].given == "a file over 5 MB"
    for kept in old.acceptance_criteria:
        if kept.id != "AC-2":
            assert by_id[kept.id] == kept  # byte for byte the same
    diff = lanes.get_pending_diff(settings, request_id)
    assert {(c.id, c.change) for c in diff.criteria} == {("AC-2", "changed"), (new_id, "added")}
    assert "Confirm v2" in chat(settings, request_id, "assistant")[-1]
    assert len(records_of(settings, request_id)) == 1  # nothing saved until he confirms


def test_confirm_saves_the_next_version_with_the_same_request_number(settings, written):
    request_id, _ = written
    start_requirement_lane(settings, request_id)
    lanes.revise(settings, request_id, rev(settings, request_id), client=StubClient(CHANGE_AND_ADD))

    state = lanes.confirm_revision(settings, request_id, rev(settings, request_id))

    saved = records_of(settings, request_id)
    assert [r.version for r in saved] == [1, 2] and saved[1].request_id == request_id
    assert state.step == "req_discover" and state.pending_record is None
    assert request_status(settings, request_id) == "CONFIRMED_FOR_DISCOVERY"
    revised = events_of(settings, request_id, "record_revised")[0].details
    assert (revised["from"], revised["to"]) == (1, 2)


def test_8_14_a_removed_id_is_never_given_out_again(settings, written):
    request_id, _ = written
    start_requirement_lane(settings, request_id)
    top = len(records_of(settings, request_id)[-1].acceptance_criteria)
    remove_last = {"criteria_ops": [{"op": "remove", "id": f"AC-{top}"}], "field_updates": {}}
    lanes.revise(settings, request_id, rev(settings, request_id), client=StubClient(remove_last))
    lanes.confirm_revision(settings, request_id, rev(settings, request_id))
    # a later Refine (v3) adds a criterion
    with open_db(settings.db_path) as conn:
        conn.execute("UPDATE da_refine_state SET state = json_set(state, '$.step', 'req_revise')")
        conn.commit()
    add_one = {
        "criteria_ops": [
            {"op": "add", "kind": "success", "given": "g", "when": "w", "then": "a result is shown"}
        ],
        "field_updates": {},
    }

    client = StubClient(add_one)
    state = lanes.revise(settings, request_id, rev(settings, request_id), client=client)

    ids = [c.id for c in state.pending_record.acceptance_criteria]
    assert f"AC-{top}" not in ids and f"AC-{top + 1}" in ids


def test_a_reply_naming_a_missing_criterion_is_explained_and_proposes_nothing(settings, written):
    request_id, _ = written
    start_requirement_lane(settings, request_id)
    bad = {"criteria_ops": [{"op": "remove", "id": "AC-99"}], "field_updates": {}}

    state = lanes.revise(settings, request_id, rev(settings, request_id), client=StubClient(bad))

    assert state.step == "req_revise" and state.pending_record is None
    assert "AC-99" in chat(settings, request_id, "assistant")[-1]


def test_a_correction_at_the_checkpoint_runs_the_revision_again(settings, written):
    request_id, _ = written
    start_requirement_lane(settings, request_id)
    lanes.revise(settings, request_id, rev(settings, request_id), client=StubClient(CHANGE_AND_ADD))
    client = StubClient(CHANGE_AND_ADD)

    lanes.revise(settings, request_id, rev(settings, request_id), "Make it 10 MB", client)

    assert "Make it 10 MB" in client.prompts[0] and "Reject big files" in client.prompts[0]


def test_8_18_cancel_revision_saves_nothing_and_goes_back(settings, written):
    request_id, _ = written
    start_requirement_lane(settings, request_id)
    lanes.revise(settings, request_id, rev(settings, request_id), client=StubClient(CHANGE_AND_ADD))

    state = lanes.cancel(settings, request_id, rev(settings, request_id))

    assert len(records_of(settings, request_id)) == 1
    assert request_status(settings, request_id) == STATUS_READY_FOR_REVIEW
    assert state.step == "start" and state.pending_record is None
    assert events_of(settings, request_id, "refine_cancelled")
    with open_db(settings.db_path) as conn:
        assert read_refines(conn, request_id)[0].result == "cancelled"


def test_cancel_before_the_click_changes_no_status(settings, written):
    request_id, _ = written
    suggest(settings, request_id, StubClient(lane_reply("requirement")))

    lanes.cancel(settings, request_id, rev(settings, request_id))

    assert request_status(settings, request_id) == STATUS_READY_FOR_REVIEW


# --- 8-37: the stale check ---


@pytest.mark.parametrize("action", ["suggest", "choose", "revise", "confirm", "cancel"])
def test_8_37_an_old_refine_revision_is_refused(settings, written, action):
    request_id, _ = written
    start_requirement_lane(settings, request_id)
    old = rev(settings, request_id) - 1
    calls = {
        "suggest": lambda: lanes.suggest(settings, request_id, "x", old, StubClient()),
        "choose": lambda: lanes.choose_lane(settings, request_id, "bug", old),
        "revise": lambda: lanes.revise(settings, request_id, old, client=StubClient()),
        "confirm": lambda: lanes.confirm_revision(settings, request_id, old),
        "cancel": lambda: lanes.cancel(settings, request_id, old),
    }

    with pytest.raises(StaleRevisionError):
        calls[action]()
