"""The workspace check through the flow (rows 5-1 to 5-10)."""

import pytest

from agents import da_workspace_flow as flow
from agents.da_workspace_checks import fingerprint
from tests.da_approach_play import event_types, events_of
from tests.da_workspace_play import (
    MODIFY,
    ORIGINAL,
    facts_of,
    good_folder,
    pick,
    ready_to_build_id,
    texts,
)

pytestmark = pytest.mark.usefixtures("published_rulebook")

TESTS_INIT = "tests/cvda_2026_0001/__init__.py"


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return ready_to_build_id(settings)


def test_5_1_before_any_folder_the_step_is_start_with_only_the_choose_button(settings, request_id):
    view = flow.get_workspace_view(settings, request_id)

    assert view.step == "start" and view.revision == 0
    assert view.browser_buttons == [("choose", "Choose workspace folder")]
    assert view.buttons == []
    assert view.request.status == "READY_TO_BUILD"


def test_5_10_a_good_folder_takes_baselines_writes_the_tests_folder_and_is_ready(
    settings, request_id
):
    folder = good_folder()

    view, _ = pick(settings, request_id, folder)

    assert view.step == "ws_ready" and view.revision == 1
    assert view.request.status == "READY_TO_BUILD"
    assert folder.files[TESTS_INIT].startswith("# Tests for this request")
    types = event_types(settings, request_id)
    assert {"workspace_check_passed", "workspace_baseline_taken", "workspace_written"} <= set(types)
    baseline = events_of(settings, request_id, "workspace_baseline_taken")[0]
    assert baseline.details["files"] == {MODIFY: fingerprint(ORIGINAL)}
    rows = {row.path: row for row in view.rows}
    assert rows[MODIFY].baseline_at is not None and rows[MODIFY].status == "Not written yet"
    assert rows["tests/cvda_2026_0001/"].status == "Created"
    assert any("Tests folder created" in t for t in texts(view, "assistant"))


def test_5_9_no_git_folder_passes_and_the_information_is_saved(settings, request_id):
    view, _ = pick(settings, request_id, good_folder(git=False))

    assert view.step == "ws_ready"
    assert view.check.has_git is False
    assert "not a Git clone" in view.check.info[0]
    assert any("not a Git clone" in t for t in texts(view, "assistant"))


def test_5_2_a_folder_without_callbacks_is_blocked_and_nothing_is_written(settings, request_id):
    folder = good_folder()
    del folder.files["src/callbacks/da_calls.py"]

    view, judgement = pick(settings, request_id, folder)

    assert judgement.job is None
    assert view.step == "ws_blocked" and view.request.status == "READY_TO_BUILD"
    assert [b.code for b in view.check.blockers] == ["B1"]
    assert TESTS_INIT not in folder.files
    assert "workspace_check_failed" in event_types(settings, request_id)
    assert "workspace_written" not in event_types(settings, request_id)
    assert any(t.startswith("B1:") for t in texts(view, "assistant"))
    assert ("choose", "Choose another folder") in view.browser_buttons
    assert [key for key, _ in view.buttons] == ["change_approach", "help"]


def test_5_4_a_missing_file_to_change_names_the_path(settings, request_id):
    folder = good_folder()
    del folder.files[MODIFY]
    folder.files["src/agents/other.py"] = "x\n"  # keep the folder src/agents there

    view, _ = pick(settings, request_id, folder)

    assert [b.code for b in view.check.blockers] == ["B3"]
    assert MODIFY in view.check.blockers[0].text


def test_a_blocked_folder_can_be_followed_by_a_good_one(settings, request_id):
    bad = good_folder()
    del bad.files["src/callbacks/da_calls.py"]
    view, _ = pick(settings, request_id, bad)

    view, _ = pick(settings, request_id, good_folder(), view.revision)

    assert view.step == "ws_ready" and view.revision == 2


def test_the_different_folder_name_warning_shows_in_the_chat(settings, request_id):
    view, _ = pick(settings, request_id, good_folder("first-clone"))

    view, _ = pick(settings, request_id, good_folder("second-clone"), view.revision)

    assert "This request was linked to first-clone. You picked second-clone." in texts(
        view, "assistant"
    )
    assert view.folder_name == "second-clone"


def test_a_second_check_after_the_tests_folder_exists_does_not_block_itself(settings, request_id):
    folder = good_folder()
    view, _ = pick(settings, request_id, folder)

    view, _ = pick(settings, request_id, folder, view.revision)  # the P7 case

    assert view.step == "ws_ready"
    assert len(events_of(settings, request_id, "workspace_written")) == 2


def test_facts_the_server_cannot_trust_are_refused_and_nothing_is_saved(settings, request_id):
    folder = good_folder()
    facts = facts_of(settings, request_id, folder)
    facts.files[0].fingerprint = "0" * 64 if facts.files[0].text else None
    facts.files[1].path = "src/secret.py"

    from db_table_functions.db_tbl_da_workspace import WorkspaceError

    with pytest.raises(WorkspaceError, match="not in the file plan"):
        flow.judge_facts(settings, request_id, facts, 0)

    assert flow.get_workspace_view(settings, request_id).revision == 0


def test_5_32_p29_the_practice_folder_from_the_work_test_passes_the_check(settings, request_id):
    from tests.da_workspace_play import practice_folder

    view, _ = pick(settings, request_id, practice_folder())

    assert view.step == "ws_ready"  # a copy of the real repo would stop at B3
    assert view.check.blockers == []


def test_5_32_p29_the_work_test_docs_build_exactly_that_folder_with_command_prompt():
    from pathlib import Path

    from tests.da_workspace_play import PRACTICE_FILE, PRACTICE_FOLDERS, PRACTICE_TEXT

    docs = (Path(__file__).resolve().parent.parent / "docs" / "workspace-work-test.md").read_text(
        encoding="utf-8"
    )

    for folder in PRACTICE_FOLDERS:
        assert f"mkdir C:\\Dev\\practice\\{folder.replace('/', chr(92))}" in docs
    one_line = PRACTICE_TEXT.strip()
    assert f"echo {one_line}> C:\\Dev\\practice\\{PRACTICE_FILE.replace('/', chr(92))}" in docs
    assert "Command Prompt" in docs
    # Part 1 (DevTools) is gone: no console steps, no PowerShell steps.
    assert "F12" not in docs and "await showDirectoryPicker" not in docs
    assert "typeof window" not in docs
    assert "Do not pick a copy of the real CodeVision" in docs
