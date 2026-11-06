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
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_workspace import read_file_versions
from tests.da_browser import HAS_DIR_JS, READ_JS, SEED_JS
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

    assert page.evaluate(READ_JS, INIT) is None  # C1: the check wrote no tests folder
    assert page.evaluate(HAS_DIR_JS, "tests") is False
    view = flow.get_workspace_view(settings, request_id)
    assert view.step == "ws_ready" and view.folder_name  # the folder NAME only, never a path
    assert "/" not in view.folder_name and "\\" not in view.folder_name
    assert view.request.status == "READY_TO_BUILD"
    assert button(page, "Build").is_enabled()  # 6-1: a real Build button, not "coming in Phase 6"
    assert page.evaluate("() => window.__opened.includes('secret_notes.py')") is False
    assert page.get_by_role("tab", name="Build").is_enabled()


def test_the_build_button_rescans_the_folder_and_sees_the_edited_file(
    make_live_page, live_url, settings, request_id
):
    """F7: there is no manual Re-scan button; the Build button re-scans by itself first (B1)."""
    page = make_live_page(live_url)
    button(page, "Choose workspace folder").wait_for(timeout=WAIT_MS)
    page.evaluate(SEED_JS, FOLDER)
    button(page, "Choose workspace folder").click()
    wait_for_text(page, "passed the check")
    assert page.get_by_role("button", name="Re-scan", exact=True).count() == 0
    page.evaluate(SEED_JS, {MODIFY: "def validate(path):\n    return False\n"})

    button(page, "Build").click()
    wait_for_text(page, "Building. This takes a few minutes")

    with open_db(settings.db_path) as conn:
        latest = read_file_versions(conn, request_id, MODIFY)[-1]
    assert latest.kind == "scanned" and "return False" in latest.text  # the edit was seen


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
        assert archive.namelist() == ["READ_ME_FIRST.txt"]  # C5: code files only; no build yet
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


def test_5_31_p30_reconnect_is_hidden_until_the_browser_needs_your_ok_and_survives_redraws(
    make_live_page, live_url, settings, request_id
):
    page = make_live_page(live_url)
    button(page, "Choose workspace folder").wait_for(timeout=WAIT_MS)
    page.evaluate(SEED_JS, FOLDER)
    button(page, "Choose workspace folder").click()
    wait_for_text(page, "passed the check")
    reconnect = button(page, "Reconnect")
    needs = page.get_by_text("Needs your OK")
    page.wait_for_function("() => document.querySelector('#da-ws-chip') !== null")
    assert not reconnect.is_visible() and not needs.is_visible()  # permission is granted
    assert page.locator("#da-ws-chip button").count() == 0  # the chip has no buttons

    # The browser now wants permission again (as on a new visit). A redraw (the Build button's
    # re-scan, F7) re-asks. It asks once (a click may ask); the browser still "forgets"
    # afterwards, until Reconnect.
    page.evaluate(
        """() => {
          window.__asked = 0;
          FileSystemHandle.prototype.queryPermission = async () =>
            window.__asked >= 2 ? 'granted' : 'prompt';
          FileSystemHandle.prototype.requestPermission = async () => {
            window.__asked += 1;
            return 'granted';
          };
        }"""
    )
    button(page, "Build").click()
    needs.wait_for(state="visible", timeout=WAIT_MS)
    assert reconnect.is_visible() and not page.get_by_text("✅").first.is_visible()

    reconnect.click()
    reconnect.wait_for(state="hidden", timeout=WAIT_MS)
    assert page.evaluate("() => window.__asked") == 2
    assert not needs.is_visible()
    assert flow.get_workspace_view(settings, request_id).step == "ws_ready"
