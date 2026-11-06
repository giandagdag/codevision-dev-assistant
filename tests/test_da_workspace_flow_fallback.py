"""The ZIP and upload fallback through the flow (rows 5-22, 5-23, 5-24)."""

import zipfile

import pytest

from agents import da_workspace_flow as flow
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_workspace import WorkspaceError, read_file_versions
from tests.da_approach_play import event_types, events_of
from tests.da_workspace_play import MODIFY, facts_of, good_folder, ready_to_build_id, texts

pytestmark = pytest.mark.usefixtures("published_rulebook")

INIT = "tests/cvda_2026_0001/__init__.py"


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return ready_to_build_id(settings)


@pytest.fixture
def fallback(settings, request_id):
    return flow.use_fallback(settings, request_id, "unsupported", 0)


def test_5_22_a_browser_without_the_picker_gets_the_fallback_step(fallback):
    assert fallback.step == "ws_fallback" and fallback.mode == "download"
    assert [label for _, label in fallback.browser_buttons] == [
        "Download ZIP",
        "Upload folder to check",
        "Try the folder picker again",
    ]


def test_the_fallback_use_is_audited_with_the_reason(settings, request_id, fallback):
    assert events_of(settings, request_id, "workspace_fallback_used")[0].details == {
        "which": "unsupported"
    }


def test_5_23_and_6_40_before_a_build_the_zip_holds_no_tests_folder_only_the_readme(
    settings, request_id, fallback, tmp_path
):
    """Phase 6 (C5): the ZIP holds code files only. Before a build there are none yet."""
    package = flow.prepare_download(settings, request_id, fallback.revision)

    assert package.job.files == []  # no tests/<id>/__init__.py any more
    assert "READ_ME" not in package.readme  # the name is the browser's; the text explains steps
    assert "Unzip this file" in package.readme and "tests" not in package.readme
    with open_db(settings.db_path) as conn:
        assert read_file_versions(conn, request_id, INIT) == []  # nothing recorded as written
    archive = tmp_path / "pack.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for item in package.job.files:
            zf.writestr(item.path, item.text)
        zf.writestr(flow.README_NAME, package.readme)
    with zipfile.ZipFile(archive) as zf:
        assert zf.namelist() == ["READ_ME_FIRST.txt"]
    assert "workspace_written" not in event_types(settings, request_id)


def test_the_download_advice_is_said_only_once(settings, request_id, fallback):
    first = flow.prepare_download(settings, request_id, fallback.revision)
    second = flow.prepare_download(settings, request_id, first.view.revision)

    advice = [t for t in texts(second.view, "assistant") if flow.DOWNLOAD_ADVICE in t]
    assert len(advice) == 1


def test_5_24_an_uploaded_good_folder_passes_and_takes_the_baselines(
    settings, request_id, fallback
):
    folder = good_folder()
    folder.reads.clear()

    view = flow.check_uploaded(
        settings, request_id, facts_of(settings, request_id, folder), fallback.revision
    )

    assert view.step == "ws_ready" and view.mode == "download"
    assert set(folder.reads) <= set(view.planned_paths)  # only planned (and tests) files read
    with open_db(settings.db_path) as conn:
        assert [v.kind for v in read_file_versions(conn, request_id, MODIFY)] == ["baseline"]


def test_5_24_an_upload_that_names_a_file_outside_the_plan_is_refused(
    settings, request_id, fallback
):
    folder = good_folder()
    facts = facts_of(settings, request_id, folder)
    facts.files[0].path = "src/agents/not_planned.py"

    with pytest.raises(WorkspaceError, match="not in the file plan"):
        flow.check_uploaded(settings, request_id, facts, fallback.revision)

    assert flow.get_workspace_view(settings, request_id).revision == fallback.revision


def test_an_uploaded_bad_folder_is_blocked_in_download_mode(settings, request_id, fallback):
    folder = good_folder()
    del folder.files["src/web/da_page.py"]

    view = flow.check_uploaded(
        settings, request_id, facts_of(settings, request_id, folder), fallback.revision
    )

    assert view.step == "ws_blocked" and view.mode == "download"
    assert [label for _, label in view.browser_buttons] == ["Upload folder to check"]


def test_download_is_only_possible_in_download_mode(settings, request_id):
    with pytest.raises(WorkspaceError):
        flow.prepare_download(settings, request_id, 0)
