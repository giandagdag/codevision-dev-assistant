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


def test_5_10_and_6_35_a_good_folder_takes_baselines_and_is_ready_and_writes_nothing(
    settings, request_id
):
    folder = good_folder()
    before = dict(folder.files)

    view, _ = pick(settings, request_id, folder)

    assert view.step == "ws_ready" and view.revision == 1
    assert view.request.status == "READY_TO_BUILD"
    assert folder.files == before and not folder.folder_exists("tests")  # C1: no write
    types = event_types(settings, request_id)
    assert {"workspace_check_passed", "workspace_baseline_taken"} <= set(types)
    assert "workspace_written" not in types
    baseline = events_of(settings, request_id, "workspace_baseline_taken")[0]
    assert baseline.details["files"] == {MODIFY: fingerprint(ORIGINAL)}
    rows = {row.path: row for row in view.rows}
    assert rows[MODIFY].baseline_at is not None and rows[MODIFY].status == "Not written yet"
    assert not any("tests" in path for path in rows)  # the file table drops the tests row
    assert not any("Tests folder" in t for t in texts(view, "assistant"))


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
    assert "This folder doesn't match the plan yet:" in texts(view, "assistant")
    assert not any("I cannot use this folder" in t for t in texts(view, "assistant"))
    assert ("choose", "Choose another folder") in view.browser_buttons
    # B1 is about the folder, not the plan: changing the approach cannot fix it (F6).
    assert [key for key, _ in view.buttons] == ["help"]


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


def test_6_38_an_old_tests_folder_from_the_phase_5_work_test_does_not_block_or_get_read(
    settings, request_id
):
    folder = good_folder(
        files={"tests/cvda_2026_0001/__init__.py": "# old\n", "tests/cvda_2026_0001/t.py": "x\n"}
    )
    folder.reads.clear()

    view, _ = pick(settings, request_id, folder)

    assert view.step == "ws_ready" and view.check.blockers == []  # no B7
    assert not any(path.startswith("tests/") for path in folder.reads)  # never read


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


def test_6_32_p26_the_different_folder_line_names_the_linked_folder_and_changes_nothing(
    settings, request_id
):
    view, _ = pick(settings, request_id, good_folder())

    after = flow.different_folder(settings, request_id, view.revision)

    assert texts(after, "assistant")[-1] == (
        "This is a different folder that is also called codevision. Use Change to link it."
    )
    assert after.revision == view.revision and after.step == "ws_ready"
    assert "Re-scan first" not in " ".join(texts(after, "assistant"))


def test_p26_with_no_linked_folder_there_is_nothing_to_compare(settings, request_id):
    from db_table_functions.db_tbl_da_workspace import WorkspaceError

    with pytest.raises(WorkspaceError, match="nothing to compare"):
        flow.different_folder(settings, request_id, 0)


def test_p26_change_is_offered_at_start_once_a_folder_was_linked(settings, request_id):
    # Reopening the approach resets the check but keeps the linked folder's name (Phase 5), so
    # start can have a linked folder. The view passes that fact in; here it is passed directly.
    unlinked_start = [label for _, label in flow._buttons_for("start", "picker", False, False)[1]]
    linked_start = [label for _, label in flow._buttons_for("start", "picker", False, True)[1]]

    assert unlinked_start == ["Choose workspace folder"]
    assert linked_start == ["Choose workspace folder", "Change folder"]


# --- Phase 6 fixes, F6: which buttons a blocked folder offers ---


def wrong_folder_b1():
    folder = good_folder()
    del folder.files["src/callbacks/da_calls.py"]
    return folder


def wrong_folder_b2():
    """The developer picked the src folder itself: its children are web and callbacks."""
    from web.da_fake_browser_folder import FakeBrowserFolder

    return FakeBrowserFolder(
        name="src", files={"web/da_page.py": "# web\n", "callbacks/da_calls.py": "# c\n"}
    )


def b3_missing_file():
    folder = good_folder()
    del folder.files[MODIFY]
    folder.files["src/agents/other.py"] = "x\n"
    return folder


def b4_file_already_exists():
    return good_folder(files={"src/agents/excel_processor.py": "# already here\n"})


def b5_folder_missing():
    folder = good_folder()
    del folder.files[MODIFY]  # also B3; the folder src/agents is not there at all
    return folder


def b6_too_big():
    return good_folder(files={MODIFY: "x = 1\n" * 200_000})


@pytest.mark.parametrize(
    ("make_folder", "code"), [(wrong_folder_b1, "B1"), (wrong_folder_b2, "B2")]
)
def test_f6_a_wrong_folder_offers_only_choose_another_folder_and_get_help(
    settings, request_id, make_folder, code
):
    view, _ = pick(settings, request_id, make_folder())

    assert [b.code for b in view.check.blockers] == [code]
    assert [label for _, label in view.buttons] == ["Get help"]
    assert [label for _, label in view.browser_buttons] == ["Choose another folder"]
    assert "Change the approach" not in view.note
    assert view.note.startswith("This folder doesn't match the plan yet.")


@pytest.mark.parametrize(
    ("make_folder", "code"),
    [
        (b3_missing_file, "B3"),
        (b4_file_already_exists, "B4"),
        (b5_folder_missing, "B5"),
        (b6_too_big, "B6"),
    ],
)
def test_f6_a_blocker_about_a_planned_file_also_offers_change_the_approach(
    settings, request_id, make_folder, code
):
    view, _ = pick(settings, request_id, make_folder())

    assert code in [b.code for b in view.check.blockers]
    assert [label for _, label in view.buttons] == ["Change the approach", "Get help"]
    assert [label for _, label in view.browser_buttons] == ["Choose another folder"]
    assert "This folder doesn't match the plan yet:" in texts(view, "assistant")


def test_f8_the_folder_button_is_called_change_folder(settings, request_id):
    assert flow.CHANGE_FOLDER_LABEL == "Change folder"
    view, _ = pick(settings, request_id, good_folder())

    assert [label for _, label in view.browser_buttons] == ["Change folder"]


def test_f7_there_is_no_manual_rescan_button_at_ready_to_build(settings, request_id):
    view, _ = pick(settings, request_id, good_folder())

    assert view.step == "ws_ready"
    assert "Re-scan" not in [label for _, label in view.browser_buttons]
    assert "Re-scan" not in [label for _, label in view.buttons]


def test_f7_download_mode_keeps_its_upload_button_because_that_is_its_scan():
    server, browser, _ = flow._buttons_for("ws_ready", "download", False, True)

    assert server == []
    assert [label for _, label in browser] == ["Download ZIP", "Upload folder to re-scan"]
