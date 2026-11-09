"""Row 8-42: build, edit one line in the private test folder, Re-scan, Check my edits, a bug lane
and a rebuild, in a real browser. His edited line must still be in the file at the end.

Skipped, not failed, when Playwright or its browser is missing (plan decision P16). A skip means
the Refine buttons were NOT clicked for real: the engine behind each button and the server side of
every browser hop are tested without a browser (`test_da_refine_*.py`), and Gian's check on
127.0.0.1:8050 is the proof of the real clicks.
"""

import threading

import pytest
from werkzeug.serving import make_server

from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from tests.da_browser import READ_JS, SEED_JS
from tests.da_build_play import MODIFY, ORIGINAL
from tests.da_workspace_play import ready_to_build_id
from web import da_home_web_server as server_module

pytestmark = pytest.mark.usefixtures("published_rulebook")

FOLDER = {
    "src/web/da_page.py": "# web\n",
    "src/callbacks/da_calls.py": "# callbacks\n",
    MODIFY: ORIGINAL,
    "src/agents/secret_notes.py": "never read\n",
}
NOTE = "# my own note, written by the developer\n"
WAIT_MS = 15000
BUILD_WAIT_MS = 120000
REFINE_PLACEHOLDER = "Tell me what to change or fix, then press Send."


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def live_url(settings):
    request_id = ready_to_build_id(settings)
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


def test_8_42_his_edit_survives_a_bug_lane_rebuild_in_a_real_browser(make_live_page, live_url):
    page = make_live_page(live_url)
    problems = []
    page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
    button(page, "Choose workspace folder").wait_for(timeout=WAIT_MS)
    page.evaluate(SEED_JS, FOLDER)
    button(page, "Choose workspace folder").click()
    wait_for_text(page, "passed the check")
    button(page, "Build").click()
    wait_for_text(page, "The code files are in your folder", BUILD_WAIT_MS)
    button(page, "Re-scan").wait_for(timeout=WAIT_MS)

    # 1. He edits one line in his folder and presses Re-scan: the side by side shows it.
    written = page.evaluate(READ_JS, MODIFY)
    page.evaluate(SEED_JS, {MODIFY: NOTE + written})
    button(page, "Re-scan").click()
    wait_for_text(page, "Your edits are not tested yet")
    wait_for_text(page, "Your edits")
    button(page, "Check my edits").wait_for(timeout=WAIT_MS)

    # 2. Check my edits runs on the server and ends green; the Refine buttons come back.
    button(page, "Check my edits").click()
    wait_for_text(page, "Running on the server", BUILD_WAIT_MS)
    button(page, "Re-scan").wait_for(timeout=BUILD_WAIT_MS)
    assert page.evaluate(READ_JS, MODIFY).startswith(NOTE)  # a check run writes nothing

    # 3. A bug: type it, pick the bug lane, confirm the repro test. The fix build starts by itself.
    page.get_by_placeholder(REFINE_PLACEHOLDER).fill("The upload is wrong")
    button(page, "Send").click()
    button(page, "Bug").click()
    button(page, "Yes, this is the bug").click(timeout=BUILD_WAIT_MS)
    wait_for_text(page, "Running on the server", BUILD_WAIT_MS)
    # His note sits next to the line the fix changes, so the app stops and asks (edit protection).
    # He picks Keep mine, then Apply my choices; only then is the code written.
    wait_for_text(page, "The rebuild touches 1 place(s) you edited", BUILD_WAIT_MS)
    button(page, "Keep mine").click()
    button(page, "Apply my choices").click()
    button(page, "Re-scan").wait_for(timeout=BUILD_WAIT_MS)  # b_written again: the code is written

    # 4. His edited line is still in the file, and Dash raised no missing-button error.
    assert NOTE in page.evaluate(READ_JS, MODIFY)
    assert [p for p in problems if "nonexistent object" in p] == []
