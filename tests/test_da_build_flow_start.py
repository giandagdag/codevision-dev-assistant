"""Starting a build (rows 6-3, 6-29, rules B1, B4, B8)."""

import pytest

from agents import da_build_flow as flow
from db_table_functions.db_tbl_da_build import BuildError
from db_table_functions.db_tbl_da_understand import STALE_MESSAGE, StaleRevisionError
from tests.da_approach_play import events_of
from tests.da_build_play import (
    build_state,
    chat,
    event_types,
    ready_with_workspace,
    request_status,
)
from tests.da_workspace_play import ready_to_build_id

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def approach_state(settings, request_id):
    from db_table_functions.da_db import open_db
    from db_table_functions.db_tbl_da_approach import read_approach_state

    with open_db(settings.db_path) as conn:
        return read_approach_state(conn, request_id)


@pytest.fixture
def request_id(settings):
    return ready_with_workspace(settings)[0]


def test_6_3_build_starts_in_building_with_a_run_and_the_started_event(settings, request_id):
    assert flow.get_revision(settings, request_id) == 0

    state = flow.start_build(settings, request_id, 0)

    assert (state.step, state.build_number, state.current_round) == ("b_running", 1, 0)
    assert state.write_state == "not_written" and state.revision == 1
    accepted = approach_state(settings, request_id).accepted_approach_version
    assert accepted >= 1 and state.approach_version == accepted  # the ACCEPTED version, not v1
    assert request_status(settings, request_id) == "BUILDING"
    types = event_types(settings, request_id)
    assert "build_started" in types and types.count("status_changed") >= 1
    assert events_of(settings, request_id, "build_started")[0].details == {"build": 1}


def test_the_chat_says_it_is_building_and_asks_once_not_to_edit_the_planned_files(
    settings, request_id
):
    """Rule B8: the line is sent exactly once per build."""
    flow.start_build(settings, request_id, 0)

    lines = chat(settings, request_id, "assistant")

    assert lines.count(flow.DONT_EDIT_MESSAGE) == 1
    assert flow.STARTED_MESSAGE in lines
    assert chat(settings, request_id, "developer")[-1] == "Build"


def test_build_needs_a_checked_workspace(settings):
    """Row 6-1, server half: without workspace step ws_ready there is no build."""
    request_id = ready_to_build_id(settings)  # READY_TO_BUILD, but no folder chosen yet

    with pytest.raises(BuildError, match="workspace folder first"):
        flow.start_build(settings, request_id, 0)

    assert flow.get_state(settings, request_id).step == "start"
    assert request_status(settings, request_id) == "READY_TO_BUILD"


def test_clicking_build_twice_starts_one_build(settings, request_id):
    """Rule B4. The second click carries the old revision, so it is refused as stale."""
    flow.start_build(settings, request_id, 0)

    with pytest.raises(StaleRevisionError, match=STALE_MESSAGE):
        flow.start_build(settings, request_id, 0)

    assert flow.get_state(settings, request_id).build_number == 1


def test_a_window_that_knows_the_new_revision_still_cannot_start_a_second_build(
    settings, request_id
):
    state = flow.start_build(settings, request_id, 0)

    with pytest.raises(BuildError, match="already running|READY TO BUILD"):
        flow.start_build(settings, request_id, state.revision)


def test_6_29_every_action_sent_with_an_old_revision_is_refused(settings, request_id):
    state = flow.start_build(settings, request_id, 0)
    old = state.revision - 1

    for action in (flow.stop_build, flow.try_again, flow.request_help, flow.change_approach):
        with pytest.raises(StaleRevisionError, match=STALE_MESSAGE):
            action(settings, request_id, old)

    assert build_state(settings, request_id).step == "b_running"  # nothing changed


def test_a_request_that_is_not_ready_to_build_cannot_start(settings):
    from tests.da_approach_play import discovery_confirmed_id

    request_id = discovery_confirmed_id(settings)  # still before Approach is finished

    with pytest.raises(BuildError):
        flow.start_build(settings, request_id, 0)


def test_6_2_a_planned_file_edited_before_build_is_saved_as_scanned_and_is_the_starting_text(
    settings, request_id
):
    from agents import da_build_loop as loop
    from db_table_functions.da_db import open_db
    from db_table_functions.db_tbl_da_workspace import read_file_versions
    from tests.da_build_play import MODIFY, ORIGINAL, RecordingFactory
    from tests.da_workspace_play import facts_of, good_folder

    folder = good_folder()  # the same pretend folder the fixture linked
    edited = ORIGINAL + "# edited by the developer before pressing Build\n"
    folder.edit(MODIFY, edited)
    facts = facts_of(settings, request_id, folder)

    state = flow.start_build(settings, request_id, 0, facts=facts)

    assert state.step == "b_running"
    with open_db(settings.db_path) as conn:
        last = read_file_versions(conn, request_id, MODIFY)[-1]
    assert (last.kind, last.text) == ("scanned", edited)
    assert flow.PRESCAN_MESSAGE in chat(settings, request_id, "assistant")
    assert events_of(settings, request_id, "build_prescan")[0].details == {"changed": 1}
    factory = RecordingFactory()
    loop.run_build(settings, request_id, factory)
    assert any(
        edited in prompt for prompt in factory.code_calls()
    )  # the build starts from HIS text


def test_6_2_an_unchanged_folder_scans_nothing_and_a_foreign_path_is_refused(settings, request_id):
    from tests.da_workspace_play import facts_of, good_folder

    facts = facts_of(settings, request_id, good_folder())
    facts.files[0].path = "src/secret.py"

    with pytest.raises(BuildError, match="not in the file plan"):
        flow.start_build(settings, request_id, 0, facts=facts)

    assert flow.get_state(settings, request_id).step == "start"  # nothing was saved
