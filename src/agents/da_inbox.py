"""What the senior inbox shows (Phase 10 spec section 9): the list, the Mine / All filter, the
unread count for the menu and the home banner, and the pill words for My recent requests.

Plain code, no AI. AS400 picture: the help-desk operator's message queue; "Mine" is the filter on
the queue the operator owns (named or backup), "All" is the whole queue.
"""

from dataclasses import dataclass
from datetime import datetime

from agents import da_tester_review as tester
from agents.da_senior_access import is_senior
from configs.da_config import Settings
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables, read_build_state
from db_table_functions.db_tbl_da_escalation import (
    list_escalations,
    read_escalation,
    read_escalations,
)
from db_table_functions.db_tbl_da_requests import read_request
from db_table_functions.db_tbl_da_rulebook import ensure_rulebook_tables
from db_table_functions.db_tbl_da_tester import read_actions, read_reviews
from db_table_functions.db_tbl_da_understand import ensure_understand_tables
from pydantic_classes.da_escalation_models import UNASSIGNED, EscalationRow

CLOSED_LIMIT = 50  # "Show closed" adds the last 50 closed rows
MENU_NAME = "Inbox"
CLOSED_BY_SENIOR = "Closed by senior"
UNASSIGNED_HEADING = "Nobody is named for this capability"

TRIGGER_WORDS = {
    "cap_hit_twice": "Build stopped twice",
    "out_of_scope": "Out of scope",
    "dispute": "Dispute",
    "tester_unable_twice": "Tester unable twice",
    "get_help": "Get help",
    "rule_exception": "Rule exception",
}


@dataclass
class InboxRow:
    """One line of the list. `revision` is the row's own number, for the stale check."""

    escalation_id: int
    revision: int
    request_id: str
    title: str
    developer_id: str
    capability: str
    triggers: str
    opened_at: datetime | None
    from_status: str
    open_item: str
    taken_over_by: str
    senior_label: str
    backup_label: str
    outcome: str
    has_exception_ask: bool = False  # Fix G9 U6: Approve / Reject exception buttons show


def matches_me(row: EscalationRow, user_id: str) -> bool:
    """Mine = I am the named or the backup senior; Unassigned rows are everybody's (D-L)."""
    who = (user_id or "").strip()
    return row.senior_label == UNASSIGNED or who in (row.senior_label, row.backup_label)


def trigger_words(triggers: list[str]) -> str:
    return ", ".join(TRIGGER_WORDS.get(name, name) for name in triggers)


def open_count(rows: list[EscalationRow], user_id: str) -> int:
    """The unread count: open rows addressed to me plus Unassigned ones. Closed rows never count."""
    return sum(1 for row in rows if row.outcome == "open" and matches_me(row, user_id))


def menu_label(count: int) -> str:
    return f"{MENU_NAME} ({count})" if count > 0 else MENU_NAME


def banner_text(count: int) -> str | None:
    """The home banner for seniors. None at 0 (the banner is not drawn)."""
    if count <= 0:
        return None
    noun = "escalation" if count == 1 else "escalations"
    return f"You have {count} {noun} waiting"


def _read_rows(settings: Settings) -> list[EscalationRow]:
    with open_db(settings.db_path) as conn:
        # Tables first: setting up a table ends any open transaction.
        ensure_rulebook_tables(conn)
        ensure_understand_tables(conn)
        ensure_build_tables(conn)
        conn.execute("BEGIN")
        return list_escalations(conn)


def senior_open_count(settings: Settings, user_id: str) -> int:
    """0 for a non-senior, so the menu and the banner stay hidden for developers."""
    if not is_senior(settings, user_id):
        return 0
    return open_count(_read_rows(settings), user_id)


def inbox_rows(
    settings: Settings, user_id: str, mine: bool = True, show_closed: bool = False
) -> list[InboxRow]:
    """Newest first. Open rows always; the last 50 closed ones only with `show_closed`."""
    with open_db(settings.db_path) as conn:
        ensure_rulebook_tables(conn)
        ensure_understand_tables(conn)
        ensure_build_tables(conn)
        conn.execute("BEGIN")
        rows = [
            row for row in list_escalations(conn) if not mine or matches_me(row, user_id)
        ]
        closed_kept = 0
        shown: list[InboxRow] = []
        for row in rows:
            if row.outcome != "open":
                if not show_closed or closed_kept >= CLOSED_LIMIT:
                    continue
                closed_kept += 1
            shown.append(_to_inbox_row(conn, row))
        return shown


def get_inbox_row(settings: Settings, escalation_id: int) -> InboxRow | None:
    """One row for the detail header, or None when there is no such escalation."""
    with open_db(settings.db_path) as conn:
        ensure_rulebook_tables(conn)
        ensure_understand_tables(conn)
        ensure_build_tables(conn)
        conn.execute("BEGIN")
        row = read_escalation(conn, escalation_id)
        return _to_inbox_row(conn, row) if row else None


def _to_inbox_row(conn, row: EscalationRow) -> InboxRow:
    request = read_request(conn, row.request_id)
    return InboxRow(
        escalation_id=row.escalation_id, revision=row.revision,
        request_id=row.request_id, title=request.title if request else "",
        developer_id=request.developer_id if request else "",
        capability=row.capability, triggers=trigger_words(row.triggers),
        opened_at=row.opened_at, from_status=row.from_status,
        open_item=row.open_item, taken_over_by=row.taken_over_by,
        senior_label=row.senior_label, backup_label=row.backup_label,
        outcome=row.outcome, has_exception_ask=bool(row.exception_asks),
    )  # fmt: skip


def open_finding_options(settings: Settings, request_id: str) -> list[dict[str, str]]:
    """The Must fix and Should fix of the newest review that are still open, for the Overrule
    dialog: [{"value": "F-1", "label": "F-1 (Must fix): the message"}]."""
    with open_db(settings.db_path) as conn:
        ensure_rulebook_tables(conn)
        ensure_understand_tables(conn)
        ensure_build_tables(conn)
        conn.execute("BEGIN")
        state = read_build_state(conn, request_id)
        number = state.build_number if state else 0
        reviews = read_reviews(conn, request_id, number) if number else []
        if not reviews:
            return []
        review, actions = reviews[-1], read_actions(conn, request_id, number)
    options = []
    for item in review.findings:
        if not item.kept or item.severity == "fyi":
            continue
        held = tester.finding_state(item.finding_id, review.review_number, actions)[0]
        if held in ("accepted", "overruled"):
            continue
        word = "Must fix" if item.severity == "must_fix" else "Should fix"
        options.append(
            {"value": item.finding_id, "label": f"{item.finding_id} ({word}): {item.message[:80]}"}
        )
    return options


def pill_notes(settings: Settings, request_ids: list[str]) -> dict[str, str]:
    """Extra words for the status pill in My recent requests: "with <label>" while a row is
    open, "Closed by senior" after an abandon. Requests without a note are left out."""
    notes: dict[str, str] = {}
    with open_db(settings.db_path) as conn:
        ensure_rulebook_tables(conn)
        ensure_understand_tables(conn)
        ensure_build_tables(conn)
        conn.execute("BEGIN")
        for request_id in request_ids:
            note = _note_for(read_escalations(conn, request_id))
            if note:
                notes[request_id] = note
    return notes


def _note_for(rows: list[EscalationRow]) -> str:
    if not rows:
        return ""
    newest = rows[-1]
    if newest.outcome == "abandoned":
        return CLOSED_BY_SENIOR
    if newest.outcome == "open":
        who = "your senior" if newest.senior_label == UNASSIGNED else newest.senior_label
        return f"with {who}"
    return ""
