"""Let the AI describe it (B2 S4, fix batch B2).

AS400 picture: a help key on the bug screen that fills the input field with a draft. It is not
sent: he reads it, changes it, and presses Send himself. Nothing is saved, so a failed call
leaves the box and the request exactly as they were.
"""

from agents.da_llm_client import LLMClient
from agents.da_refine_agent import REPRO_ROLE, describe_bug
from agents.da_refine_lanes import (
    STEP_BUG,
    _call,
    _context,
    _load_state,
    _require_request,
    _require_step,
)
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables, read_build_state, read_rounds
from db_table_functions.db_tbl_da_refine import RefineError
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request
from db_table_functions.db_tbl_da_understand import read_messages

DESCRIBE_KEY = "describe_bug"
DESCRIBE_LABEL = "Let the AI describe it"
DESCRIBE_FAILED = "The AI could not write a description right now. Your text was not changed."
CHAT_LINES = 6  # the last lines of the chat the AI may read
FAILING_LIMIT = 10  # failing tests listed
LINE_LIMIT = 300


def describe_for_box(
    settings, request_id: str, base_revision: int, client: LLMClient | None = None
) -> str:
    """One AI call; returns the draft text for the box. Raises RefineError (with the box left as
    it was) when the call fails."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        conn.execute("BEGIN")
        state = _load_state(conn, request_id, base_revision)
        _require_step(state, STEP_BUG)
        request = _require_request(conn, request_id)
        rulebook = get_rulebook_for_request(settings.db_path, request_id).rulebook
        context = _context(conn, request, rulebook)
        build = read_build_state(conn, request_id)
        rounds = read_rounds(conn, request_id, build.build_number) if build else []
        chat = [f"{m.speaker}: {m.text}"[:LINE_LIMIT] for m in read_messages(conn, request_id)]
    failing = _failing_lines(rounds[-1].layer_b if rounds else None)
    recent = chat[-CHAT_LINES:]
    result, _ = _call(
        settings, REPRO_ROLE, client, lambda c: describe_bug(c, context, failing, recent)
    )
    if result is None or result.value is None:
        raise RefineError(DESCRIBE_FAILED)
    return result.value


def _failing_lines(layer_b) -> list[str]:
    if layer_b is None:
        return []
    bad = [t for t in layer_b.tests if t.result in ("fail", "error")]
    return [f"{t.name}: {t.message}"[:LINE_LIMIT] for t in bad[:FAILING_LIMIT]]
