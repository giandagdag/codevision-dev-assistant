"""Phase 10 step 10b: the senior Inbox page (spec sections 9 and 14; tests 10-33 to 10-35,
10-50, 10-55, 10-56) plus the developer-side pieces that go with it (waiting line, senior
bubble, pills)."""

import ast
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from dash import dcc

from agents import da_senior_actions as senior
from agents.da_inbox import (
    CLOSED_BY_SENIOR,
    banner_text,
    inbox_rows,
    menu_label,
    open_count,
    pill_notes,
    pill_text,
    senior_open_count,
)
from callbacks.screen_callbacks import da_developer_assistant_page_callbacks as dev_cb
from callbacks.screen_callbacks.da_inbox_page_callbacks import (
    inbox_user,
    inbox_view,
    menu_and_banner,
    run_senior_action,
)
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import read_build_state, save_build_state
from db_table_functions.db_tbl_da_escalation import read_open_escalation, update_escalation
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from layouts.da_inbox_page import (
    INBOX_PATH,
    MODE_CLOSE,
    MODE_GUIDANCE,
    MODE_OVERRULE,
    MODE_TAKE_OVER,
    all_controls,
    inbox_list,
    read_only,
)
from pydantic_classes.da_escalation_models import UNASSIGNED, EscalationRow
from tests.test_da_senior_actions import seed
from web import da_web_components as parts

pytestmark = pytest.mark.usefixtures("published_rulebook")
SRC = Path(__file__).resolve().parents[1] / "src"
NOW = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
REASON = "The rule does not apply to this batch job."


def texts(node) -> str:
    """All the words in a Dash tree, including labels and values."""
    found: list[str] = []

    def visit(item):
        if isinstance(item, list | tuple):
            for sub in item:
                visit(sub)
        elif isinstance(item, str):
            found.append(item)
        elif hasattr(item, "to_plotly_json"):
            for name in getattr(item, "_prop_names", []):
                value = getattr(item, name, None)
                if name in ("id", "style"):
                    continue
                if isinstance(value, str | list | tuple) or hasattr(value, "to_plotly_json"):
                    visit(value)

    visit(node)
    return "\n".join(found)


def row(label="ann", backup="", outcome="open", request="CVDA-2026-0001") -> EscalationRow:
    return EscalationRow(
        request_id=request, from_status="NOT_PASSING", senior_label=label, backup_label=backup,
        outcome=outcome,
    )  # fmt: skip


def set_labels(settings, request_id, senior_label, backup_label=""):
    """Address the open row to someone (the seed leaves it Unassigned)."""
    with open_db(settings.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = read_open_escalation(conn, request_id)
        changed = current.model_copy(
            update={"senior_label": senior_label, "backup_label": backup_label}
        )
        update_escalation(conn, changed, current.revision, NOW)


def drawable(settings, **kwargs):
    """The senior-actions seed, with the approach version a real build always has, so the whole
    request page can be drawn from it."""
    request_id = seed(settings, **kwargs)
    with open_db(settings.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        state = read_build_state(conn, request_id)
        state.approach_version = 1
        save_build_state(conn, state, state.revision, NOW)
    return request_id


@pytest.fixture
def settings(make_settings):
    return make_settings(senior_ids=("ann", "bob"), developer_id="ann")


# --- 10-55 / 10-56: the count, the menu, the banner (plain functions) ---


def test_10_55_the_menu_shows_the_open_count_and_plain_inbox_at_zero():
    rows = [row("ann"), row("ann", outcome="returned"), row("bob"), row(UNASSIGNED)]
    assert open_count(rows, "ann") == 2  # his own open row plus the Unassigned one
    assert open_count(rows, "bob") == 2
    assert open_count([row("ann", outcome="abandoned")], "ann") == 0  # closed rows never count
    assert menu_label(2) == "Inbox (2)"
    assert menu_label(0) == "Inbox"


def test_the_backup_senior_counts_too():
    assert open_count([row("ann", backup="bob")], "bob") == 1
    assert open_count([row("ann", backup="bob")], "cy") == 0


def test_10_56_the_banner_is_for_seniors_with_open_rows_only(settings):
    assert banner_text(2) == "You have 2 escalations waiting"
    assert banner_text(1) == "You have 1 escalation waiting"
    assert banner_text(0) is None
    request_id = seed(settings)
    set_labels(settings, request_id, "ann")

    assert senior_open_count(settings, "ann") == 1
    assert menu_and_banner(settings, "ann", "/") == ("Inbox (1)", "You have 1 escalation waiting")
    assert menu_and_banner(settings, "ann", "/inbox") == ("Inbox (1)", None)  # banner: Home only
    # A developer who is no senior sees neither the number nor the banner.
    assert menu_and_banner(settings, "dev-0099", "/") == ("Inbox", None)


def test_a_senior_with_nothing_waiting_sees_no_banner(settings):
    assert menu_and_banner(settings, "ann", "/") == ("Inbox", None)


# --- 10-33: who may open it ---


def test_10_33_a_senior_sees_the_list_and_anyone_else_the_refusal(settings):
    request_id = seed(settings)
    set_labels(settings, request_id, "ann")

    mine = inbox_view(settings, INBOX_PATH, "", "ann")
    other = inbox_view(settings, INBOX_PATH, "", "dev-0099")

    assert request_id in texts(mine.listing)
    assert "This page is for capability seniors." in texts(other.listing)
    assert request_id not in texts(other.listing)
    assert other.detail == [] and other.target is None


def test_a_senior_in_the_catalog_gets_in_without_the_env_list(make_settings, published_rulebook):
    named = published_rulebook.rulebook.policy.capabilities[0].named_senior
    if not named:
        pytest.skip("the seed names no senior")
    settings = make_settings()
    assert "capability seniors" not in texts(inbox_view(settings, INBOX_PATH, "", named).listing)


def test_10_33_codevision_source_lets_nobody_in_and_logs_the_line(make_settings, caplog):
    settings = make_settings(senior_source="codevision", senior_ids=("ann",))
    with caplog.at_level(logging.WARNING):
        view = inbox_view(settings, INBOX_PATH, "", "ann")
    assert "capability seniors" in texts(view.listing)
    assert "Senior access is not configured yet" in caplog.text


def test_other_paths_draw_nothing_and_stay_hidden(settings):
    view = inbox_view(settings, "/", "", "ann")
    assert view.shell_style == {"display": "none"} and view.listing == []


# --- 10-34: Mine / All / Show closed ---


def test_10_34_mine_all_and_show_closed(settings):
    first, second = seed(settings), seed(settings)
    set_labels(settings, first, "ann")
    set_labels(settings, second, "bob")

    mine = [r.request_id for r in inbox_rows(settings, "ann", mine=True)]
    everything = [r.request_id for r in inbox_rows(settings, "ann", mine=False)]

    assert mine == [first]
    assert sorted(everything) == sorted([first, second])
    open_row = read_open(settings, first)
    senior.close_escalation(settings, open_row.escalation_id, open_row.revision, "ann",
                            "abandoned", "Not doing this one.", NOW)  # fmt: skip
    assert [r.request_id for r in inbox_rows(settings, "ann", mine=True)] == []
    shown = inbox_rows(settings, "ann", mine=True, show_closed=True)
    assert [(r.request_id, r.outcome) for r in shown] == [(first, "abandoned")]


def test_unassigned_rows_show_to_everybody_under_their_own_heading(settings):
    request_id = seed(settings)
    set_labels(settings, request_id, UNASSIGNED)

    rows = inbox_rows(settings, "bob", mine=True)

    assert [r.request_id for r in rows] == [request_id]
    assert "Nobody is named for this capability" in texts(inbox_list(rows, "bob"))


def test_an_empty_list_says_so(settings):
    assert "Nothing is waiting." in texts(inbox_list([], "ann"))


def test_the_list_links_keep_the_as_switch_and_show_why_it_was_escalated(settings):
    request_id = seed(settings)
    set_labels(settings, request_id, "ann")
    shown = texts(inbox_list(inbox_rows(settings, "ann"), "ann"))
    assert "Dispute" in shown and "Disputed Must fix: F-1" in shown
    assert "NOT PASSING" in shown


# --- 10-35: the detail is read-only ---


def test_10_35_the_detail_shows_the_request_and_no_developer_control(settings):
    request_id = drawable(settings)
    set_labels(settings, request_id, "ann")
    target = read_open(settings, request_id)

    view = inbox_view(settings, INBOX_PATH, f"?escalation={target.escalation_id}", "ann")

    assert view.target == {
        "escalation_id": target.escalation_id, "revision": target.revision,
        "request_id": request_id,
    }  # fmt: skip
    action_bar, *page = view.detail
    assert all_controls(page) == []  # no button, no text box, nothing with an id
    assert "Read-only view" in texts(page)
    assert "Developer Assistant chat" in texts(page)
    assert "Overrule a finding" in texts(action_bar)
    assert [f["value"] for f in view.findings] == ["F-1"]


def test_a_closed_row_is_shown_without_action_buttons(settings):
    request_id = drawable(settings)
    set_labels(settings, request_id, "ann")
    target = read_open(settings, request_id)
    senior.close_escalation(settings, target.escalation_id, target.revision, "ann",
                            "abandoned", "Not doing this one.", NOW)  # fmt: skip

    view = inbox_view(settings, INBOX_PATH, f"?escalation={target.escalation_id}", "ann")

    assert "Overrule a finding" not in texts(view.detail[0])
    assert view.findings == []


def test_read_only_removes_controls_and_ids_from_a_developer_page():
    from layouts.da_developer_assistant_page import render_new_workspace

    page = render_new_workspace(demo_mode=False)
    assert all_controls(page)  # the developer page has a text box, buttons and stores

    cleaned = read_only(page)

    assert all_controls(cleaned) == []
    assert not [c for c in cleaned if isinstance(c, dcc.Store)]


def test_a_picked_row_that_does_not_exist_shows_the_list_only(settings):
    view = inbox_view(settings, INBOX_PATH, "?escalation=999", "ann")
    assert view.detail == [] and view.target is None


# --- the four actions through the screen's function ---


def test_guidance_goes_through_with_the_revision_the_senior_saw(settings):
    request_id = seed(settings)
    set_labels(settings, request_id, "ann")
    target_row = read_open(settings, request_id)
    target = {"escalation_id": target_row.escalation_id, "revision": target_row.revision,
              "request_id": request_id}  # fmt: skip

    line = run_senior_action(settings, MODE_GUIDANCE, target, "ann", "Use the batch limit table.")

    assert line == f"Guidance sent to {request_id}"
    assert read_open(settings, request_id).guidance[0].text == "Use the batch limit table."
    with pytest.raises(StaleRevisionError):  # the same old window, a second time
        run_senior_action(settings, MODE_GUIDANCE, target, "ann", "Again.")


def test_overrule_take_over_and_close_lines(settings):
    request_id = seed(settings)
    set_labels(settings, request_id, "ann")

    def target():
        r = read_open(settings, request_id)
        return {"escalation_id": r.escalation_id, "revision": r.revision, "request_id": request_id}

    assert run_senior_action(settings, MODE_OVERRULE, target(), "ann", REASON, finding="F-1") == (
        f"Overruled F-1 on {request_id}"
    )
    assert run_senior_action(settings, MODE_TAKE_OVER, target(), "ann") == (
        f"You have taken over {request_id}"
    )
    line = run_senior_action(settings, MODE_CLOSE, target(), "ann", "Looks fine now.",
                             outcome="returned")  # fmt: skip
    assert line == f"Returned to the developer: {request_id}"


def test_a_non_senior_cannot_act(settings):
    with pytest.raises(senior.SeniorActionError, match="capability seniors"):
        run_senior_action(settings, MODE_TAKE_OVER, {"escalation_id": 1, "revision": 1,
                          "request_id": "CVDA-2026-0001"}, "dev-0099")  # fmt: skip


def test_overrule_needs_a_picked_finding(settings):
    with pytest.raises(senior.SeniorActionError, match="Pick"):
        run_senior_action(settings, MODE_OVERRULE, {"escalation_id": 1, "revision": 1,
                          "request_id": "CVDA-2026-0001"}, "ann", REASON)  # fmt: skip


# --- ?as= works in the home shell only ---


def test_the_as_switch_works_only_when_the_shell_allows_it(settings):
    assert inbox_user(settings, "?as=bob", allow_switch=True) == "bob"
    assert inbox_user(settings, "?as=bob", allow_switch=False) == "ann"
    assert inbox_user(settings, "", allow_switch=True) == "ann"


# --- the developer side: waiting line, senior bubble, pills ---


def test_the_developer_page_shows_the_waiting_line_while_a_row_is_open(settings, monkeypatch):
    request_id = drawable(settings)
    set_labels(settings, request_id, "ann")
    monkeypatch.setattr(dev_cb, "get_settings", lambda: settings)

    page = dev_cb.show_page(f"?request={request_id}", 0)

    text = texts(page)
    assert "Waiting for your senior. Your chat is locked until ann replies." in text
    assert "Send" not in text.split("Waiting for your senior")[-1]


def test_after_guidance_the_composer_is_not_replaced(settings, monkeypatch):
    request_id = drawable(settings)
    set_labels(settings, request_id, "ann")
    target = read_open(settings, request_id)
    senior.send_guidance(settings, target.escalation_id, target.revision, "ann", "Try X.")
    monkeypatch.setattr(dev_cb, "get_settings", lambda: settings)

    assert "Your chat is locked" not in texts(dev_cb.show_page(f"?request={request_id}", 0))


def test_the_waiting_line_keeps_the_open_item_visible(settings, monkeypatch):
    request_id = drawable(settings)
    monkeypatch.setattr(dev_cb, "get_settings", lambda: settings)

    assert "Disputed Must fix: F-1" in texts(dev_cb.show_page(f"?request={request_id}", 0))


def test_a_senior_line_gets_its_own_bubble_style():
    from pydantic_classes.da_request_record_models import ChatMessage
    from styles import da_styles

    def message(text):
        return ChatMessage(
            request_id="CVDA-2026-0001", speaker="assistant", text=text, sent_at=NOW
        )

    assert parts.chat_bubble(message("Senior ann: Use X.")).style == da_styles.BUBBLE_SENIOR
    assert parts.chat_bubble(message("Hello.")).style == da_styles.BUBBLE["assistant"]


def test_pills_say_with_whom_and_closed_by_senior(settings):
    first, second = seed(settings), seed(settings)
    set_labels(settings, first, "ann")
    set_labels(settings, second, UNASSIGNED)
    gone = read_open(settings, second)
    senior.close_escalation(settings, gone.escalation_id, gone.revision, "ann",
                            "abandoned", "Not doing this one.", NOW)  # fmt: skip

    notes = pill_notes(settings, [first, second])

    assert notes == {first: "with ann", second: CLOSED_BY_SENIOR}
    assert pill_text("ESCALATION_REQUIRED", notes[first]) == "ESCALATION REQUIRED, with ann"
    assert pill_text("ESCALATION_REQUIRED", CLOSED_BY_SENIOR) == "Closed by senior"
    assert pill_text("NOT_PASSING", "") == "NOT PASSING"
    assert "ESCALATION REQUIRED, with ann" in texts(
        parts.status_pill("ESCALATION_REQUIRED", notes[first])
    )


# --- 10-50: the inbox imports nothing from the developer page callbacks ---


def test_10_50_inbox_modules_import_nothing_from_the_developer_callbacks():
    for path in (
        SRC / "callbacks" / "screen_callbacks" / "da_inbox_page_callbacks.py",
        SRC / "layouts" / "da_inbox_page.py",
        SRC / "agents" / "da_inbox.py",
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not [m for m in modules if "developer_assistant_page_callbacks" in m], path


def test_the_inbox_makes_no_ai_call():
    banned = ("get_llm_client", "get_build_client", "get_tester_client", ".complete(")
    for path in (
        SRC / "callbacks" / "screen_callbacks" / "da_inbox_page_callbacks.py",
        SRC / "layouts" / "da_inbox_page.py",
        SRC / "agents" / "da_inbox.py",
    ):
        text = path.read_text(encoding="utf-8")
        assert not [word for word in banned if word in text], path


def read_open(settings, request_id):
    with open_db(settings.db_path) as conn:
        return read_open_escalation(conn, request_id)
