"""Row 9-50: an Enhance request (card 2) whose safety net is accepted and whose plan is accepted
goes through the folder check and a green build in a real browser. Only the function in scope may
change; every other function of the target stays byte for byte the same.

The steps before the Build tab (Find, freshness, Understand, Discover, the net, Approach) run
through the engine, the same way the other browser tests start (`ready_to_build_id`). Their screens
are tested without a browser (`test_da_enhance_screen*.py`). Skipped, not failed, when Playwright or
its browser is missing (plan decision P16): then the real clicks are NOT proven, and Gian's check on
127.0.0.1:8050 is the proof.
"""

import ast
import threading

import pytest
from werkzeug.serving import make_server

from agents import da_approach_flow as approach_flow
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from tests.da_browser import READ_JS, SEED_JS
from tests.test_da_enhance_approach import accepted_net_request, at_tests_step
from web import da_home_web_server as server_module

pytestmark = pytest.mark.usefixtures("published_rulebook")

TARGET = "src/agents/limits_expiry_report.py"
IN_SCOPE_CLASS = "ExpiryReport"  # the scripted edit changes ExpiryReport.build_line
WAIT_MS = 15000
BUILD_WAIT_MS = 120000


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def target_text(settings):
    return (settings.fake_main_dir / TARGET).read_text(encoding="utf-8")


@pytest.fixture
def live_url(settings, tmp_path):
    request_id = accepted_net_request(settings, tmp_path)
    view = at_tests_step(settings, request_id)
    approach_flow.accept_test_plan(settings, request_id, view.revision)
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


def function_texts(source: str) -> dict[str, str]:
    """Each top-level function and each method, by dotted name, as its exact source text."""
    tree = ast.parse(source)
    found = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            found[node.name] = ast.get_source_segment(source, node)
        elif isinstance(node, ast.ClassDef):
            for inner in node.body:
                if isinstance(inner, ast.FunctionDef):
                    found[f"{node.name}.{inner.name}"] = ast.get_source_segment(source, inner)
    return found


def test_9_50_only_the_function_in_scope_changes_in_a_real_browser(
    make_live_page, live_url, target_text
):
    page = make_live_page(live_url)
    problems = []
    page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
    button(page, "Choose workspace folder").wait_for(timeout=WAIT_MS)
    page.evaluate(
        SEED_JS,
        {
            "src/web/da_page.py": "# web\n",
            "src/callbacks/da_calls.py": "# callbacks\n",
            TARGET: target_text,
        },
    )
    button(page, "Choose workspace folder").click()
    wait_for_text(page, "passed the check")
    button(page, "Build").click()
    wait_for_text(page, "The code files are in your folder", BUILD_WAIT_MS)

    before = function_texts(target_text)
    after = function_texts(page.evaluate(READ_JS, TARGET))
    changed = [name for name in before if before[name] != after.get(name)]
    assert changed == [f"{IN_SCOPE_CLASS}.build_line"]
    assert set(after) == set(before)  # nothing added or dropped
    assert problems == []
