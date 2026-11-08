"""The bug lane, first half (Phase 8 step 9a): the repro test, the proof that it fails today, and
the one-click confirm that appends it to the frozen test set. Tests 8-22 and 8-23."""

import pytest

from agents import da_build_agent as build_agent
from agents import da_refine_bug as bug
from agents import da_refine_lanes as lanes
from agents.da_refine_merge import method_fingerprints
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import read_build_state, read_frozen_files
from db_table_functions.db_tbl_da_refine import RefineError, read_test_sets
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from pydantic_classes.da_models import STATUS_REVISION
from tests.da_approach_play import events_of
from tests.da_build_play import chat, request_status
from tests.da_refine_play import lane_reply, rev, written_request
from tests.da_stub_client import StubClient

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


class Reproducer(StubClient):
    """A Tester that answers with the scripted repro reply and remembers what it was sent."""

    def __init__(self):
        super().__init__("")
        self.prompts = []

    def complete(self, prompt):
        from agents.da_llm_client import LLMReply
        from agents.da_refine_agent import scripted_refine_reply

        self.prompts.append(prompt)
        return LLMReply(text=scripted_refine_reply(prompt), provider="fake", model="m")


def at_bug_lane(settings):
    request_id, folder = written_request(settings)
    lanes.suggest(settings, request_id, "The upload is wrong", rev(settings, request_id),
                  StubClient(lane_reply("bug", criterion="AC-1")))
    lanes.choose_lane(settings, request_id, "bug", rev(settings, request_id))
    return request_id, folder


def test_8_22_a_test_that_fails_today_is_shown_with_the_failure(settings):
    request_id, _ = at_bug_lane(settings)
    tester = Reproducer()

    state = bug.start_repro(settings, request_id, rev(settings, request_id), client=tester)

    assert state.step == "bug_confirm" and state.repro is not None
    assert state.repro.case_id.startswith("T-") and state.repro.failure
    assert request_status(settings, request_id) == STATUS_REVISION
    assert bug.YES_LABEL in chat(settings, request_id, "assistant")[-1]
    assert "def " not in tester.prompts[0].split("## The contract")[0]  # no code to the Tester
    assert events_of(settings, request_id, "repro_test_written")
    with open_db(settings.db_path) as conn:
        assert read_test_sets(conn, request_id) == []  # nothing appended before his click


def test_8_22_yes_appends_a_test_set_version_and_keeps_earlier_methods(settings):
    request_id, _ = at_bug_lane(settings)
    bug.start_repro(settings, request_id, rev(settings, request_id), client=Reproducer())
    with open_db(settings.db_path) as conn:
        approach = read_build_state(conn, request_id).approach_version
        before = method_fingerprints(read_frozen_files(conn, request_id, approach)["test"].text)

    state = bug.confirm_repro(settings, request_id, rev(settings, request_id))

    assert state.step == "bug_rebuild"
    with open_db(settings.db_path) as conn:
        sets = read_test_sets(conn, request_id)
    assert len(sets) == 1 and sets[0].added_case_ids == [state.repro.case_id]
    after = method_fingerprints(sets[0].text)
    assert len(after) == len(before) + 1
    assert all(after[name] == print_ for name, print_ in before.items())
    assert events_of(settings, request_id, "repro_test_confirmed")


def test_8_23_a_test_that_passes_today_twice_offers_help_and_uses_no_round(settings, monkeypatch):
    request_id, _ = at_bug_lane(settings)
    monkeypatch.setattr(build_agent, "FAKE_SWITCHES", frozenset({"repro_passes_today"}))

    state = bug.start_repro(settings, request_id, rev(settings, request_id), client=Reproducer())
    assert state.step == "bug_start" and state.repro_tries == 1
    assert bug.PASSES_TODAY_LINE in chat(settings, request_id, "assistant")[-1]
    state = bug.start_repro(
        settings, request_id, rev(settings, request_id), description="It is the book file",
        client=Reproducer(),
    )

    assert state.step == "bug_help" and state.repro_passed_today == 2
    assert "Get help" in chat(settings, request_id, "assistant")[-1]
    assert read_build_state_number(settings, request_id) == 1  # no new build, so no round
    with open_db(settings.db_path) as conn:
        assert read_test_sets(conn, request_id) == []


def read_build_state_number(settings, request_id) -> int:
    with open_db(settings.db_path) as conn:
        return read_build_state(conn, request_id).build_number


def test_no_describe_again_clears_the_test_and_the_tries(settings):
    request_id, _ = at_bug_lane(settings)
    bug.start_repro(settings, request_id, rev(settings, request_id), client=Reproducer())

    state = bug.reject_repro(settings, request_id, rev(settings, request_id))

    assert state.step == "bug_start" and state.repro is None and state.repro_tries == 0
    with open_db(settings.db_path) as conn:
        assert read_test_sets(conn, request_id) == []
    assert events_of(settings, request_id, "repro_test_rejected")


def test_cancel_at_the_confirm_gives_everything_back(settings):
    request_id, _ = at_bug_lane(settings)
    bug.start_repro(settings, request_id, rev(settings, request_id), client=Reproducer())

    state = lanes.cancel(settings, request_id, rev(settings, request_id))

    assert state.step == "start" and state.repro is None
    with open_db(settings.db_path) as conn:
        assert read_test_sets(conn, request_id) == []


def test_an_unusable_answer_saves_nothing_and_stays_at_the_start(settings):
    request_id, _ = at_bug_lane(settings)

    state = bug.start_repro(
        settings, request_id, rev(settings, request_id), client=StubClient("no format", "no format")
    )

    assert state.step == "bug_start" and state.repro is None
    assert "describe it again" in chat(settings, request_id, "assistant")[-1].lower()


def test_8_24_the_fix_build_is_fresh_writes_only_traced_files_and_keeps_the_tests(settings):
    from agents import da_build_loop as loop
    from tests.da_build_play import RecordingFactory, files_of, run_row

    request_id, _ = at_bug_lane(settings)
    bug.start_repro(settings, request_id, rev(settings, request_id), client=Reproducer())
    bug.confirm_repro(settings, request_id, rev(settings, request_id))
    frozen_before = files_of(settings, request_id, 1, "test")[0].fingerprint

    state = bug.start_bug_fix(settings, request_id, rev(settings, request_id))

    assert state.step == "bug_fixing"
    assert request_status(settings, request_id) == "BUILDING"
    assert run_row(settings, request_id, 2).kind == "rebuild"
    assert loop.run_build(settings, request_id, RecordingFactory(), build_number=2) == "done"

    written = [f for f in files_of(settings, request_id, 2, "code") if f.made_by != "system"]
    planned = len({f.path for f in files_of(settings, request_id, 1, "code")})
    first_round = {f.path for f in written if f.round == 1}
    assert 1 <= len(first_round) <= planned
    assert files_of(settings, request_id, 2, "test") == []  # the tests are not written again
    assert files_of(settings, request_id, 1, "test")[0].fingerprint == frozen_before
    after = lanes.get_refine_state(settings, request_id)
    assert after.step == "start" and after.repro is None  # the Refine ended with the build


def test_start_bug_fix_only_after_the_confirm(settings):
    request_id, _ = at_bug_lane(settings)

    with pytest.raises(RefineError):
        bug.start_bug_fix(settings, request_id, rev(settings, request_id))


def test_the_steps_run_in_order_and_a_stale_window_is_refused(settings):
    request_id, _ = at_bug_lane(settings)
    old = rev(settings, request_id)

    with pytest.raises(RefineError):
        bug.confirm_repro(settings, request_id, old)
    bug.start_repro(settings, request_id, old, client=Reproducer())
    with pytest.raises(StaleRevisionError):
        bug.start_repro(settings, request_id, old, client=Reproducer())
