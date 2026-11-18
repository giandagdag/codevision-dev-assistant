"""Which Refine buttons show at each step and what each key calls (Phase 8 step 16a)."""

import pytest

from agents import da_build_flow as flow
from agents import da_build_loop as loop
from agents import da_refine_actions as actions
from agents import da_refine_flow as rflow
from agents import da_refine_lanes as lanes
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import read_build_state
from db_table_functions.db_tbl_da_refine import RefineError, read_test_sets
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from tests.da_build_play import MODIFY, request_status
from tests.da_refine_play import rev, written_request
from tests.da_workspace_play import facts_of

pytestmark = pytest.mark.usefixtures("published_rulebook")


@pytest.fixture
def settings(make_settings):
    return make_settings()


def keys_of(box):
    return [key for key, _ in box.buttons]


def go(settings, request_id, key, text="", arg=""):
    """One click, the way the page makes it: both revisions are read fresh."""
    return actions.perform_refine(
        settings, key, request_id, rev(settings, request_id), text, arg,
        build_revision=flow.get_revision(settings, request_id),
    )


def rescan(settings, request_id, folder):
    facts = facts_of(settings, request_id, folder)
    rflow.rescan(settings, request_id, facts, flow.get_revision(settings, request_id))


# The single list (plan 16a): step -> the keys of its buttons (Get help is added while a lane is
# open, in REVISION_IN_PROGRESS).
EXPECTED = {
    "req_revise": ["revise", "cancel"],
    "req_checkpoint": ["confirm_v2", "cancel"],
    "req_discover": ["discover"],
    "req_findings": ["findings_ok", "findings_escalate"],
    "req_approach": ["rev_approach"],
    "approach_start": ["approach_change", "cancel"],
    "approach_refused": ["switch", "cancel"],
    "bug_start": ["cancel"],
    "bug_confirm": ["repro_yes", "repro_no", "cancel"],
    "bug_help": ["repro_no", "cancel"],
    "bug_rebuild": ["bug_fix"],
    "own_confirm": ["own_add", "own_drop"],
    "own_fails": ["own_bug", "own_drop"],
}


@pytest.mark.parametrize("step", sorted(EXPECTED))
def test_each_lane_step_offers_its_buttons_and_get_help_while_a_lane_is_open(step):
    revision_box = actions._lane_bar(step, "REVISION_IN_PROGRESS", 7)
    assert keys_of(revision_box) == [*EXPECTED[step], "help"]
    assert revision_box.refine_revision == 7 and revision_box.lane
    plain = actions._lane_bar(step, "CONFIRMED_FOR_DISCOVERY", 7)
    assert keys_of(plain) == EXPECTED[step]  # the engine refuses Get help outside REVISION


def test_text_box_opens_only_for_a_correction_and_the_bug_description():
    for step in EXPECTED:
        box = actions._lane_bar(step, "REVISION_IN_PROGRESS", 1)
        assert box.text_open == (step in ("req_checkpoint", "bug_start", "req_findings"))
    assert actions._lane_bar("req_checkpoint", "REVISION_IN_PROGRESS", 1).send_label == (
        lanes.CORRECT_LABEL
    )


def test_every_key_a_bar_draws_is_handled_and_browser_keys_are_not():
    # Keys come from the module's own tables, so a new button without a handler fails here.
    drawn = {key for _, buttons, _, _ in actions.LANE_STEPS.values() for key, _ in buttons}
    drawn |= set(actions.LABELS) - set(actions.BROWSER_KEYS)
    drawn |= {key for step in EXPECTED for key in EXPECTED[step]} | {"help"}
    drawn |= {f"lane_{lane}" for lane in lanes.LANE_LABELS}
    drawn |= {"check_edits", "restore", "restore_cancel", "restore_pick", "fix_edit",
              "edit_right", "fix_myself", "apply", "send", "fixit", "add_case"}
    assert drawn <= set(actions.HANDLERS)
    for key in actions.BROWSER_KEYS:
        assert key not in actions.HANDLERS


def test_every_engine_function_the_table_names_exists():
    names = {
        "da_refine_lanes": ["suggest", "choose_lane", "cancel", "revise", "confirm_revision"],
        "da_refine_flow": ["start_check", "fix_myself", "restore_preview", "rescan"],
        "da_refine_edit": ["fix_edit", "edit_right", "open_restore", "pick_restore"],
        "da_refine_revision": ["run_discover", "confirm_findings", "start_revision_approach"],
        "da_refine_approach": ["start_approach_change", "switch_to_requirement"],
        "da_refine_bug": ["start_repro", "confirm_repro", "reject_repro", "start_bug_fix"],
        "da_refine_owntest": ["confirm_own_test", "drop_own_test", "treat_as_bug",
                              "add_test_case"],
        "da_refine_fixit": ["fix_it"],
        "da_refine_picks": ["pick", "apply_choices"],
        "da_refine_help": ["request_help"],
    }
    for module, functions in names.items():
        loaded = __import__(f"agents.{module}", fromlist=["x"])
        for name in functions:
            assert callable(getattr(loaded, name)), f"{module}.{name}"


def test_an_unknown_or_browser_key_is_refused(settings):
    request_id, _ = written_request(settings)
    for key in ("rescan", "restore_go", "nothing"):
        with pytest.raises(RefineError):
            go(settings, request_id, key)


def test_at_b_written_the_bar_offers_the_box_and_send_calls_suggest(settings):
    request_id, _ = written_request(settings)
    bar = actions.get_refine_bar(settings, request_id)
    assert bar.offered and bar.text_open and not bar.lane
    assert bar.browser_buttons[0][0] == "rescan"

    outcome = go(settings, request_id, "send", "The upload is wrong")

    assert outcome.job == "" and outcome.message == ""
    bar = actions.get_refine_bar(settings, request_id)
    assert keys_of(bar) == [
        "lane_bug", "lane_requirement", "lane_approach", "explain_simple", "decide_help", "cancel"
    ]
    assert bar.lane and not bar.text_open  # the suggestion (bug) comes first, he still decides


def test_a_stale_refine_revision_is_refused_and_a_second_click_too(settings):
    request_id, _ = written_request(settings)
    old = rev(settings, request_id)
    actions.perform_refine(settings, "send", request_id, old, "The upload is wrong")

    with pytest.raises(StaleRevisionError):
        actions.perform_refine(settings, "send", request_id, old, "The upload is wrong")
    with pytest.raises(StaleRevisionError):
        actions.perform_refine(settings, "lane_bug", request_id, old)


def test_the_bug_lane_end_to_end_through_the_callback_functions(settings):
    request_id, _ = written_request(settings)

    go(settings, request_id, "send", "The upload is wrong")
    outcome = go(settings, request_id, "lane_bug")  # the repro runs by itself
    assert lanes.get_refine_state(settings, request_id).step == "bug_confirm" and not outcome.job
    assert request_status(settings, request_id) == "REVISION_IN_PROGRESS"
    assert keys_of(actions.get_refine_bar(settings, request_id)) == [
        "repro_yes", "repro_no", "cancel", "help"
    ]

    outcome = go(settings, request_id, "repro_yes")  # the fix build starts by itself

    assert outcome.job == "build"
    assert request_status(settings, request_id) == "BUILDING"
    assert loop.run_build(settings, request_id, build_number=2) == "done"
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"
    with open_db(settings.db_path) as conn:
        assert len(read_test_sets(conn, request_id)) == 1
        assert read_build_state(conn, request_id).build_number == 2


def test_cancel_in_lane_choice_and_bug_start_give_everything_back(settings):
    request_id, _ = written_request(settings)
    go(settings, request_id, "send", "The upload is wrong")
    go(settings, request_id, "cancel")
    assert lanes.get_refine_state(settings, request_id).step == "start"
    assert request_status(settings, request_id) == "READY_FOR_REVIEW"


def test_check_my_edits_returns_the_build_job(settings):
    request_id, folder = written_request(settings)
    folder.edit(MODIFY, "# my own note\n" + folder.files[MODIFY])
    rescan(settings, request_id, folder)
    assert "check_edits" in keys_of(actions.get_refine_bar(settings, request_id))

    outcome = go(settings, request_id, "check_edits")

    assert outcome.job == "build"
    assert request_status(settings, request_id) == "BUILDING"


def test_the_r3_buttons_show_after_a_failed_check_and_fix_myself_works(settings):
    request_id, folder = written_request(settings)
    folder.edit(MODIFY, "def validate(path):\n    return False\n")
    rescan(settings, request_id, folder)
    go(settings, request_id, "check_edits")
    assert loop.run_build(settings, request_id) == "done"

    keys = keys_of(actions.get_refine_bar(settings, request_id))

    assert keys[:3] == ["fix_edit", "edit_right", "fix_myself"]
    go(settings, request_id, "fix_myself")
    assert request_status(settings, request_id) == "NOT_PASSING"
    outcome = go(settings, request_id, "fix_edit")
    assert outcome.job == "build" and request_status(settings, request_id) == "BUILDING"


def test_restore_list_warning_and_cancel(settings):
    request_id, folder = written_request(settings)
    folder.edit(MODIFY, "# my own note\n" + folder.files[MODIFY])
    rescan(settings, request_id, folder)
    go(settings, request_id, "check_edits")
    assert loop.run_build(settings, request_id) == "done"
    assert "restore" in keys_of(actions.get_refine_bar(settings, request_id))

    go(settings, request_id, "restore")
    bar = actions.get_refine_bar(settings, request_id)
    assert keys_of(bar) == ["restore_pick:1", "restore_cancel"]

    go(settings, request_id, "restore_pick:1")
    bar = actions.get_refine_bar(settings, request_id)
    assert keys_of(bar) == ["restore_cancel"] and bar.browser_buttons[-1] == (
        "restore_go", "Restore build 1"
    )

    go(settings, request_id, "restore_cancel")
    assert "restore" in keys_of(actions.get_refine_bar(settings, request_id))
    assert lanes.get_refine_state(settings, request_id).restore_pick == 0
