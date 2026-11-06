"""Row 6-34: a whole request from READY_TO_BUILD to b_written in a real browser, against the real
page, the fake AI and the real sandbox. The picker is the browser's private test folder; the app
itself has no test switch.

Skipped, not failed, when Playwright or its browser is missing.
"""

import threading

import pytest
from werkzeug.serving import make_server

from agents import da_build_flow as build_flow
from agents.da_workspace_checks import fingerprint
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_workspace import read_file_versions
from tests.da_browser import HAS_DIR_JS, READ_JS, SEED_JS
from tests.da_build_play import CREATE, MODIFY, ORIGINAL
from tests.da_workspace_play import ready_to_build_id
from web import da_home_web_server as server_module

pytestmark = pytest.mark.usefixtures("published_rulebook")

FOLDER = {
    "src/web/da_page.py": "# web\n",
    "src/callbacks/da_calls.py": "# callbacks\n",
    MODIFY: ORIGINAL,
    "src/agents/secret_notes.py": "never read\n",
}
WAIT_MS = 15000
BUILD_WAIT_MS = 90000


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


def wait_for_text(page, text, timeout=WAIT_MS):
    page.get_by_text(text).first.wait_for(timeout=timeout)


def test_6_34_a_request_runs_from_ready_to_build_to_written_in_a_real_browser(
    make_live_page, live_url, settings, request_id
):
    page = make_live_page(live_url)
    problems = []
    page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
    button(page, "Choose workspace folder").wait_for(timeout=WAIT_MS)
    page.evaluate(SEED_JS, FOLDER)
    button(page, "Choose workspace folder").click()
    wait_for_text(page, "passed the check")

    button(page, "Build").click()  # the page re-scans the folder, then the server builds
    wait_for_text(page, "Running on the server", BUILD_WAIT_MS)  # the live progress page
    wait_for_text(page, "The code files are in your folder", BUILD_WAIT_MS)

    # The code files are in the folder, as the browser read them back.
    created = page.evaluate(READ_JS, CREATE)
    changed = page.evaluate(READ_JS, MODIFY)
    assert created.startswith('"""Read the sheets') and "not sheet.get" in created
    assert ".xlsx" in changed
    # No tests folder was created, and the file nobody planned was never read.
    assert page.evaluate(HAS_DIR_JS, "tests") is False
    assert page.evaluate("() => window.__opened.includes('secret_notes.py')") is False
    # The server saved exactly what the browser read back (the fingerprints agree).
    state = build_flow.get_state(settings, request_id)
    assert (state.step, state.write_state) == ("b_written", "written")
    with open_db(settings.db_path) as conn:
        for path, text in ((CREATE, created), (MODIFY, changed)):
            row = read_file_versions(conn, request_id, path)[-1]
            assert row.kind == "written" and row.fingerprint == fingerprint(text)
    # The screen: green banner, the Written files, "Your turn", and the tests only on the Tests tab.
    assert page.get_by_text("Try it yourself: start CodeVision on your laptop").count() >= 1
    assert page.get_by_text("Ready with warnings").count() >= 1
    page.get_by_role("tab", name="Tests").click()
    wait_for_text(
        page, "These tests run on the CodeVision server. They are not copied to your folder."
    )
    assert page.get_by_text("T-1").count() >= 1
    # Dash raised no "nonexistent object" error for a button missing from the page (the hidden
    # Reconnect button must exist in every build state). Network errors here are not ours.
    assert [p for p in problems if "nonexistent object" in p] == []


def test_6_23_with_no_folder_permission_the_build_is_kept_and_nothing_is_written(
    make_live_page, live_url, settings, request_id
):
    """D-E: the page was reloaded (the stand-in forgets the folder), so the write waits."""
    page = make_live_page(live_url)
    button(page, "Choose workspace folder").wait_for(timeout=WAIT_MS)
    page.evaluate(SEED_JS, FOLDER)
    button(page, "Choose workspace folder").click()
    wait_for_text(page, "passed the check")
    button(page, "Build").click()
    wait_for_text(page, "Running on the server", BUILD_WAIT_MS)
    page.reload()  # leave and come back: this browser no longer holds the folder

    wait_for_text(page, "Built, not written yet", BUILD_WAIT_MS)
    state = build_flow.get_state(settings, request_id)
    assert (state.step, state.write_state) == ("b_done", "not_written")
    assert page.evaluate(READ_JS, CREATE) is None  # nothing was written
