"""Fix G9 finish F8: a senior approves or rejects a rule exception on the Inbox screen, in a real
browser (G9-3), and the F1 gap buttons on the Understand screen.

Skipped, not failed, when Playwright or its browser is missing (like the poll tests).
"""

import json
import threading
import time

import pytest
from werkzeug.serving import make_server

from agents import da_rule_check_agent as rule_agent
from agents import da_understand_flow as flow
from agents.da_llm_client import LLMReply
from agents.da_understand_rules import ASK_EXCEPTION_PREFIX, excepted_pairs
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as cb
from callbacks.screen_callbacks import da_inbox_page_callbacks as inbox_cb
from db_table_functions.db_tbl_da_understand import get_session
from tests import da_play
from web import da_home_web_server as server_module

pytestmark = pytest.mark.usefixtures("published_rulebook")

WAIT_MS = 15000
REASON = "The legacy screen needs this exact wording"
SUGGESTED = "Given no arguments, when the tool runs, then it prints NO INPUT PROVIDED"
GAP = {
    "case": "no arguments",
    "question": "What should it do with no arguments?",
    "suggested_criterion": SUGGESTED,
}


class ConflictClient:
    """Reports one conflict on a fixed criterion, every time (until an exception allows it)."""

    model = "fake"

    def __init__(self, criterion):
        self.criterion = criterion

    def complete(self, prompt, system=None):
        found = [{"criterion": self.criterion, "rule": "CV-PY-001", "why": "Not plain", "fix": "x"}]
        return LLMReply(text=json.dumps({"conflicts": found}), provider="fake", model="fake")


class GapClient:
    """The gap, until a criterion names it (then none)."""

    model = "fake"

    def complete(self, prompt, system=None):
        gaps = [] if "NO INPUT PROVIDED" in prompt else [GAP]
        reply = {"conflicts": [], "uncovered": gaps}
        return LLMReply(text=json.dumps(reply), provider="fake", model="fake")


@pytest.fixture
def settings(make_settings, monkeypatch):
    settings = make_settings(senior_ids=("ann",), developer_id="ann")
    monkeypatch.setattr(cb, "get_settings", lambda: settings)
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    monkeypatch.setattr(inbox_cb, "get_inbox_settings", lambda: settings)
    return settings


@pytest.fixture
def serve():
    servers = []

    def start():
        app = server_module.create_app()
        server = make_server("127.0.0.1", 0, app.server, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return f"http://127.0.0.1:{server.server_port}"

    yield start
    for server, thread in servers:
        server.shutdown()
        thread.join(timeout=5)


def _asked_for_exception(settings):
    """A request that waits at Understand on an open exception ask. Returns (request_id, row)."""
    from db_table_functions.da_db import open_db
    from db_table_functions.db_tbl_da_escalation import ensure_escalation_tables, read_escalations

    view = da_play.to_checkpoint(settings)
    criterion = view.record.acceptance_criteria[1].id
    after = flow.choose_option(
        settings, view.request.request_id, flow.PROCEED_OPTION, view.revision,
        client=ConflictClient(criterion),
    )  # fmt: skip
    flow.ask_for_exception(
        settings, view.request.request_id, f"{ASK_EXCEPTION_PREFIX}1", REASON, after.revision
    )
    with open_db(settings.db_path) as conn:
        ensure_escalation_tables(conn)
        row = read_escalations(conn, view.request.request_id)[0]
    return view.request.request_id, row.escalation_id, criterion


def _senior_decides(make_live_page, url, button, note):
    page = make_live_page(url)
    page.get_by_role("button", name=button, exact=True).click(timeout=WAIT_MS)
    page.get_by_label("Text").fill(note)
    page.get_by_role("button", name="Send", exact=True).click()
    done = "approved" if "Approve" in button else "rejected"
    page.get_by_text(f"Exception {done} on").first.wait_for(timeout=WAIT_MS)


def test_g9_3_the_senior_approves_an_exception_on_the_inbox_screen(
    make_live_page, settings, serve
):
    request_id, escalation_id, criterion = _asked_for_exception(settings)
    url = f"{serve()}/inbox?escalation={escalation_id}&as=ann"

    _senior_decides(make_live_page, url, "Approve exception", "Fine for this screen")

    record = get_session(settings.db_path, request_id).record
    assert (criterion, "CV-PY-001") in excepted_pairs(record)
    assert "approved by ann" in record.exceptions[0]


def test_g9_3_the_senior_rejects_an_exception_on_the_inbox_screen(
    make_live_page, settings, serve
):
    request_id, escalation_id, _ = _asked_for_exception(settings)
    url = f"{serve()}/inbox?escalation={escalation_id}&as=ann"

    _senior_decides(make_live_page, url, "Reject exception", "Please reword it")

    assert get_session(settings.db_path, request_id).record.exceptions == []
    assert flow.get_understand_view(settings, request_id).request.status != "ESCALATION_REQUIRED"


def test_f1_the_gap_buttons_work_on_the_screen(make_live_page, settings, serve, monkeypatch):
    monkeypatch.setattr(rule_agent, "get_understand_client", lambda *args, **kwargs: GapClient())
    view = da_play.to_checkpoint(settings)
    request_id, before = view.request.request_id, view.request.status
    page = make_live_page(f"{serve()}/?request={request_id}")

    page.get_by_role("button", name=flow.PROCEED_OPTION, exact=True).click(timeout=WAIT_MS)
    page.get_by_text("Gap: no arguments").first.wait_for(timeout=WAIT_MS)
    page.get_by_role("button", name="Add this criterion 1", exact=True).click()
    page.get_by_role("button", name=flow.PROCEED_OPTION, exact=True).click(timeout=WAIT_MS)

    deadline = time.time() + 15
    while time.time() < deadline:
        status = flow.get_understand_view(settings, request_id).request.status
        if status != before:  # confirmed, and Discovery may already have started
            break
        time.sleep(0.3)
    assert status != before
    record = get_session(settings.db_path, request_id).record
    assert any("NO INPUT PROVIDED" in c.then for c in record.acceptance_criteria)
