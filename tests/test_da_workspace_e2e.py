"""Row 5-27: a whole request from READY_TO_BUILD to ws_ready in a real browser, against the real
page. The picker is the browser's private test folder; the app itself has no test switch.

Skipped, not failed, when Playwright or its browser is missing.
"""

import threading
import zipfile

import pytest
from werkzeug.serving import make_server

from agents import da_workspace_flow as flow
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from tests.da_browser import READ_JS, SEED_JS
from tests.da_workspace_play import MODIFY, ORIGINAL, ready_to_build_id
from web import da_home_web_server as server_module

pytestmark = pytest.mark.usefixtures("published_rulebook")

INIT = "tests/cvda_2026_0001/__init__.py"
FOLDER = {
    "src/web/da_page.py": "# web\n",
    "src/callbacks/da_calls.py": "# callbacks\n",
    MODIFY: ORIGINAL,
    "src/agents/secret_notes.py": "never read\n",
}
WAIT_MS = 15000


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def request_id(settings):
    return ready_to_build_id(settings)


@pytest.fixture
def live_url(settings, request_id):
    app = server_module.create_app()
    server = make_server("127.0.0.1", 0, app.server, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/?request={request_id}"
    server.shutdown()
    thread.join(timeout=5)


def button(page, name):
    return page.get_by_role("button", name=name, exact=True).first


def wait_for_text(page, text):
    page.get_by_text(text).first.wait_for(timeout=WAIT_MS)


def test_5_27_a_request_runs_from_ready_to_build_to_ws_ready_in_a_real_browser(
    make_live_page, live_url, settings, request_id
):
    page = make_live_page(live_url)
    button(page, "Choose workspace folder").wait_for(timeout=WAIT_MS)
    page.evaluate(SEED_JS, FOLDER)

    button(page, "Choose workspace folder").click()
    wait_for_text(page, "passed the check")

    assert page.evaluate(READ_JS, INIT).startswith("# Tests for this request")
    view = flow.get_workspace_view(settings, request_id)
    assert view.step == "ws_ready" and view.folder_name  # the folder NAME only, never a path
    assert "/" not in view.folder_name and "\\" not in view.folder_name
    assert view.request.status == "READY_TO_BUILD"
    assert page.get_by_text("Build (coming in Phase 6)").count() >= 1
    assert page.evaluate("() => window.__opened.includes('secret_notes.py')") is False
    assert page.get_by_role("tab", name="Build").is_enabled()


def test_a_rescan_in_the_real_browser_lists_the_edited_file(
    make_live_page, live_url, settings, request_id
):
    page = make_live_page(live_url)
    button(page, "Choose workspace folder").wait_for(timeout=WAIT_MS)
    page.evaluate(SEED_JS, FOLDER)
    button(page, "Choose workspace folder").click()
    wait_for_text(page, "passed the check")
    page.evaluate(SEED_JS, {MODIFY: "def validate(path):\n    return False\n"})

    button(page, "Re-scan").first.click()
    wait_for_text(page, "1 file changed by you")

    view = flow.get_workspace_view(settings, request_id)
    assert view.step == "ws_ready" and view.request.status == "READY_TO_BUILD"
    assert {row.path: row.status for row in view.rows}[MODIFY] == "Changed by you"


def test_5_21_a_cancelled_picker_in_the_real_browser_says_no_folder_chosen(
    make_live_page, live_url, settings, request_id
):
    page = make_live_page(live_url)
    button(page, "Choose workspace folder").wait_for(timeout=WAIT_MS)
    page.evaluate(
        "() => { window.showDirectoryPicker = async () => {"
        " throw new DOMException('closed', 'AbortError'); }; }"
    )

    button(page, "Choose workspace folder").click()
    wait_for_text(page, "No folder chosen.")

    view = flow.get_workspace_view(settings, request_id)
    assert view.step == "start" and view.revision == 0


def test_a_blocked_folder_in_the_real_browser_shows_the_blockers(
    make_live_page, live_url, settings, request_id
):
    page = make_live_page(live_url)
    button(page, "Choose workspace folder").wait_for(timeout=WAIT_MS)
    page.evaluate(SEED_JS, {"README.md": "not codevision\n"})

    button(page, "Choose workspace folder").click()
    wait_for_text(page, "does not look like your CodeVision folder")

    assert flow.get_workspace_view(settings, request_id).step == "ws_blocked"
    assert page.evaluate(READ_JS, INIT) is None  # nothing was written
    assert button(page, "Get help").is_visible()


def test_5_22_to_5_24_the_fallback_in_the_real_browser(
    make_live_page, live_url, settings, request_id, tmp_path
):
    page = make_live_page(live_url, picker=False)
    button(page, "Choose workspace folder").wait_for(timeout=WAIT_MS)

    button(page, "Choose workspace folder").click()
    wait_for_text(page, "I cannot reach your folder")
    assert flow.get_workspace_view(settings, request_id).step == "ws_fallback"

    with page.expect_download() as download:
        button(page, "Download ZIP").click()
    target = tmp_path / "pack.zip"
    download.value.save_as(target)
    with zipfile.ZipFile(target) as archive:
        assert sorted(archive.namelist()) == sorted([INIT, "READ_ME_FIRST.txt"])
    wait_for_text(page, "upload your folder before every new download")

    folder = tmp_path / "codevision"
    for path, text in FOLDER.items():
        target_file = folder / path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(text, encoding="utf-8")
    with page.expect_file_chooser() as chooser:
        button(page, "Upload folder to check").click()
    chooser.value.set_files(folder)
    wait_for_text(page, "passed the check")

    view = flow.get_workspace_view(settings, request_id)
    assert view.step == "ws_ready" and view.mode == "download"
    opened = page.evaluate("() => window.__opened")
    assert not any(name.endswith("secret_notes.py") for name in opened)
