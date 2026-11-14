"""The Discover actions the screen calls (spec 3.7). Thin, like da_understand_flow.

Each action reads with no lock held, runs the search and the one AI call, and only then opens ONE
write transaction that saves the round, the status moves, the audit events and the chat lines
together (rules R4, R6). So no round is ever half-saved. Like a job that builds its whole
result first and then does a single commit.

Request record v1 and the Understand session are never written here (rule R4). Discover keeps its
own revision number for the stale-window check (planning decision 2).
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from agents.da_discover_agent import (
    DiscoverSummary,
    fallback_summary,
    get_discover_client,
    summarise_hits,
)
from agents.da_discover_checks import hint_problem
from agents.da_discover_queries import SearchRound, run_searches
from agents.da_enhance_flow import impact_for_record
from agents.da_escalation_flow import escalate as open_escalation
from agents.da_escalation_flow import request_triggers
from agents.da_escalation_triggers import get_help
from agents.da_impact import summary_line
from agents.da_llm_client import LLMClient, LLMClientError
from agents.da_search_index import (
    IndexFormatError,
    IndexNotBuiltError,
    SearchIndex,
    SearchNotConfiguredError,
    get_search_index,
)
from configs.da_config import ConfigError, Settings
from da_logging import get_logger
from db_table_functions.da_db import begin_write, open_db
from db_table_functions.db_tbl_da_audit import ensure_audit_table, insert_audit_event
from db_table_functions.db_tbl_da_discovery import (
    DiscoveryError,
    bump_discovery_revision,
    count_rounds,
    ensure_discovery_tables,
    insert_result,
    read_discovery_revision,
    read_escalation_open_item,
    read_latest_result,
)
from db_table_functions.db_tbl_da_enhance import (
    ensure_enhance_tables,
    read_enhance_state,
    save_enhance_state,
)
from db_table_functions.db_tbl_da_handoff import refuse_if_locked
from db_table_functions.db_tbl_da_requests import read_request, update_request
from db_table_functions.db_tbl_da_rulebook import ensure_rulebook_tables
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    add_message,
    read_confirmed_record,
    read_messages,
)
from pydantic_classes.da_discovery_models import (
    MATCH_KINDS,
    DiscoveryResult,
    DiscoveryView,
    Finding,
)
from pydantic_classes.da_enhance_models import ImpactResult
from pydantic_classes.da_models import (
    STATUS_CONFIRMED,
    STATUS_DISCOVERY_CONFIRMED,
    STATUS_ESCALATION,
    STATUS_NO_MATCH,
    STATUS_SEARCHING,
    STATUS_SIMILAR_FOUND,
    Actor,
    Request,
    display_status,
)
from pydantic_classes.da_request_record_models import RequestRecord, Speaker

logger = get_logger(__name__)

NOT_PROOF_LIMITATION = (
    "No reliable match was found in approved sources. That is not proof it does not exist."
)
DISCOVER_DIVIDER = "🔍 Discover"
SEARCHING_MESSAGE = "Searching approved sources for code that already does something similar…"
CONFIRM_OPTION = "✅ Findings look right"
HINT_OPTION = "✏️ Something's missing"
ESCALATE_OPTION = "🙋 Escalate to a senior developer"
HINT_QUESTION = "What's missing? Name a feature, file or term."
DEVELOPER_REQUEST = "developer request"
# Said whenever a round used the made-up index (DA_SEARCH_PROVIDER=fake), also with a real AI.
FAKE_INDEX_NOTICE = "Practice index (made-up code), not CodeVision."
# B1 F7: at work (onprem) with the practice index, Discovery does not search at all.
NO_INDEX_MESSAGE = (
    "No CodeVision index is connected yet, so Discovery found nothing to reuse. "
    "Ask your admin to set it up."
)
NO_INDEX_PROVIDER = "none"  # saved as the round's search provider: nothing was searched

_OUTCOME_STATUSES = (STATUS_SIMILAR_FOUND, STATUS_NO_MATCH)
_STARTABLE = (STATUS_CONFIRMED, STATUS_SEARCHING)


# --- the outcome rule (the app decides, never the AI: rules R1, R2) ---


def outcome_status(findings: list[Finding]) -> str:
    """SIMILAR_IMPLEMENTATION_FOUND if any finding is an existing or similar implementation,
    otherwise NO_RELIABLE_MATCH (spec section 2)."""
    if any(finding.kind in MATCH_KINDS for finding in findings):
        return STATUS_SIMILAR_FOUND
    return STATUS_NO_MATCH


def final_limitations(limitations: list[str], outcome: str) -> list[str]:
    """The AI's limitations, plus the 'not proof' line the app always adds when nothing matched."""
    result = list(limitations)
    if outcome == STATUS_NO_MATCH and NOT_PROOF_LIMITATION not in result:
        result.append(NOT_PROOF_LIMITATION)
    return result


# --- the actions the screen calls ---


def start_discovery(
    settings: Settings,
    request_id: str,
    base_revision: int,
    client: LLMClient | None = None,
    index: SearchIndex | None = None,
    now: datetime | None = None,
) -> DiscoveryView:
    """Run a search round from CONFIRMED_FOR_DISCOVERY, or start the round over from SEARCHING."""
    return _run_round(settings, request_id, base_revision, "", client, index, now)


def add_hint_and_search(
    settings: Settings,
    request_id: str,
    hint: str,
    base_revision: int,
    client: LLMClient | None = None,
    index: SearchIndex | None = None,
    now: datetime | None = None,
) -> DiscoveryView:
    """Search again with the developer's hint (decision D-C)."""
    problem = hint_problem(hint)
    if problem:
        raise DiscoveryError(problem)
    return _run_round(settings, request_id, base_revision, hint.strip(), client, index, now)


def confirm_discovery(
    settings: Settings, request_id: str, base_revision: int, now: datetime | None = None
) -> DiscoveryView:
    now = now or datetime.now(UTC)
    with _write_transaction(settings.db_path) as conn:
        request = _require_open_request(conn, request_id)
        _require_status(request, _OUTCOME_STATUSES, "confirmed")
        bump_discovery_revision(conn, request_id, base_revision, now)
        rounds = count_rounds(conn, request_id)
        _say(conn, request_id, "developer", CONFIRM_OPTION, now)
        _audit(conn, request_id, "developer", "discovery_confirmed", {"round": rounds}, now)
        _move(conn, request, STATUS_DISCOVERY_CONFIRMED, now)
        _say(
            conn,
            request_id,
            "assistant",
            f"Discovery confirmed after round {rounds}. Now planning how it will be built.",
            now,
        )
        _start_safety_net_step(conn, request_id, now)
    logger.info("Discovery confirmed for %s", request_id)
    return get_discovery_view(settings, request_id)


def escalate_discovery(
    settings: Settings, request_id: str, base_revision: int, now: datetime | None = None
) -> DiscoveryView:
    """Ask for a senior developer. Record v1 is not changed (R4): the open item lives in the
    audit event, the chat and the view (spec 3.5)."""
    now = now or datetime.now(UTC)
    with _write_transaction(settings.db_path) as conn:
        request = _require_open_request(conn, request_id)
        _require_status(request, _OUTCOME_STATUSES, "escalated")
        bump_discovery_revision(conn, request_id, base_revision, now)
        latest = read_latest_result(conn, request_id)
        reason = latest.limitations[-1] if latest and latest.limitations else DEVELOPER_REQUEST
        open_item = f"Escalated in Discover: {reason}"[:300]
        _say(conn, request_id, "developer", ESCALATE_OPTION, now)
        decision = get_help(request_triggers(conn, request_id), "Discover", reason)
        # D-I: with the switch off the button stays and nothing moves.
        if not open_escalation(conn, request_id, decision, now, open_item).switched_off:
            _audit(
                conn,
                request_id,
                "developer",
                "discovery_escalated",
                {"round": latest.round if latest else 0, "open_item": open_item},
                now,
            )
            _move(conn, request, STATUS_ESCALATION, now)
            _say(
                conn,
                request_id,
                "assistant",
                "A senior developer will pick this up. (The escalations inbox comes in Phase 8.)",
                now,
            )
    logger.info("Discovery escalated for %s", request_id)
    return get_discovery_view(settings, request_id)


def get_discovery_view(settings: Settings, request_id: str) -> DiscoveryView:
    """Everything the screen needs to show Discover, read on one connection so the status, the
    round and the chat always match each other."""
    with open_db(settings.db_path) as conn:
        ensure_discovery_tables(conn)
        conn.execute("BEGIN")
        request = _require_request(conn, request_id)
        record = read_confirmed_record(conn, request_id, request.version)
        if record is None:
            raise DiscoveryError("This request is not confirmed yet, so Discover cannot show it.")
        messages = read_messages(conn, request_id)
        latest = read_latest_result(conn, request_id)
        rounds = count_rounds(conn, request_id)
        revision = read_discovery_revision(conn, request_id)
        open_item = read_escalation_open_item(conn, request_id)
    can_hint = request.status in _OUTCOME_STATUSES and rounds < settings.discovery_max_rounds
    return DiscoveryView(
        request=request,
        record=record,
        messages=messages,
        status_label=display_status(request.status),
        result=latest,
        outcome=request.status,
        rounds_used=rounds,
        max_rounds=settings.discovery_max_rounds,
        choices=_choices(request.status, can_hint),
        can_hint=can_hint,
        cap_message=_cap_message(request.status, rounds, settings.discovery_max_rounds),
        open_item=open_item,
        revision=revision,
        demo_mode=settings.llm_provider == "fake",
    )


# --- one round ---


def _run_round(
    settings: Settings,
    request_id: str,
    base_revision: int,
    hint: str,
    client: LLMClient | None,
    index: SearchIndex | None,
    now: datetime | None,
) -> DiscoveryView:
    now = now or datetime.now(UTC)
    request, record, rounds = _read_for_round(settings, request_id, base_revision, hint)
    # Search and the AI call run with no database lock held.
    round_number = rounds + 1
    searched, no_index_text, notes = SearchRound(queries=[], hits=[], dropped=0), "", []
    if index is None and _no_index_at_work(settings):
        no_index_text = NO_INDEX_MESSAGE
    else:
        try:
            searched, notes = _search(settings, record, hint, index)
        except IndexNotBuiltError as error:  # B1 I5: say so and carry on
            no_index_text = str(error)
    no_index = bool(no_index_text)
    summary = _summarise(settings, record, searched.hits, hint, client)
    outcome = outcome_status(summary.findings)
    # Phase 9: who calls the functions being changed (None for a new-program request).
    impact = impact_for_record(settings, record)
    result = DiscoveryResult(
        request_id=request_id,
        round=round_number,
        record_version=record.version,
        rulebook_version=request.rulebook_version or record.rulebook_version,
        search_provider=NO_INDEX_PROVIDER if no_index else settings.search_provider,
        queries=[query.label() for query in searched.queries],
        hits=searched.hits,
        findings=summary.findings,
        limitations=[
            *([no_index_text] if no_index else []),
            *notes,
            *final_limitations(summary.limitations, outcome),
        ],
        summary_source=summary.summary_source,
        model=summary.model,
        hint=hint,
        impact=impact,
    )
    with _write_transaction(settings.db_path) as conn:
        current = _require_open_request(conn, request_id)
        _require_status(current, _round_statuses(hint), "searched")
        bump_discovery_revision(conn, request_id, base_revision, now)
        first_round = current.status == STATUS_CONFIRMED
        if first_round:
            _say(conn, request_id, "system", DISCOVER_DIVIDER, now)
        if hint:
            _say(conn, request_id, "developer", f"{HINT_OPTION}: {hint}", now)
            _audit(conn, request_id, "developer", "discovery_hint_added",
                   {"round": round_number, "hint": hint}, now)
        _audit(conn, request_id, "developer", "discovery_started",
               {"round": round_number, "provider": settings.search_provider}, now)
        # From SEARCHING ("Search again") the status is already right: no second move.
        if current.status != STATUS_SEARCHING:
            current = _move(conn, current, STATUS_SEARCHING, now)
        _say(conn, request_id, "assistant", SEARCHING_MESSAGE, now)
        if no_index:
            _say(conn, request_id, "assistant", no_index_text, now)
        for note in notes:
            _say(conn, request_id, "assistant", note, now)
        insert_result(conn, result, now)
        _move(conn, current, outcome, now)
        _audit(
            conn,
            request_id,
            "system",
            "discovery_completed",
            {
                "round": round_number,
                "hit_count": len(result.hits),
                "outcome": outcome,
                "summary_source": result.summary_source,
            },
            now,
        )
        _say(conn, request_id, "assistant", _result_line(result, outcome), now)
        if impact is not None:
            _audit(conn, request_id, "system", "impact_found", _impact_details(impact), now)
            _say(conn, request_id, "assistant", "Impact: " + summary_line(impact), now)
    logger.info("Discovery round %d for %s: %s", round_number, request_id, outcome)
    return get_discovery_view(settings, request_id)


def _impact_details(impact: ImpactResult) -> dict:
    """Counts only for the audit trail (spec section 14); the rows live in the round."""
    kinds = [row.kind for row in impact.rows]
    return {
        "available": impact.available,
        "rows": len(impact.rows),
        "direct": kinds.count("direct"),
        "possible": kinds.count("possible"),
        "imports_only": kinds.count("imports_only"),
        "more": impact.more,
        "copy": "reference copy",
    }


def _round_statuses(hint: str) -> tuple[str, ...]:
    return _OUTCOME_STATUSES if hint else _STARTABLE


def _read_for_round(
    settings: Settings, request_id: str, base_revision: int, hint: str
) -> tuple[Request, RequestRecord, int]:
    """Checks before any search: status, stale window, round cap. Nothing is written."""
    with open_db(settings.db_path) as conn:
        ensure_discovery_tables(conn)
        conn.execute("BEGIN")
        request = _require_open_request(conn, request_id)
        _require_status(request, _round_statuses(hint), "searched")
        if read_discovery_revision(conn, request_id) != base_revision:
            raise StaleRevisionError(STALE_MESSAGE)
        rounds = count_rounds(conn, request_id)
        record = read_confirmed_record(conn, request_id, request.version)
    if record is None:
        raise DiscoveryError("This request is not confirmed yet, so Discover cannot start.")
    if rounds >= settings.discovery_max_rounds:
        raise DiscoveryError(
            f"The limit of {settings.discovery_max_rounds} search rounds is reached. "
            "You can confirm the findings or escalate."
        )
    return request, record, rounds


def _no_index_at_work(settings: Settings) -> bool:
    """At work (the onprem AI) the made-up practice index must never answer silently (B1 F7)."""
    return settings.llm_provider == "onprem" and settings.search_provider == "fake"


def _search(settings: Settings, record: RequestRecord, hint: str, index: SearchIndex | None):
    try:
        index = index or get_search_index(settings)
        found = run_searches(index, record, hint, settings.search_top_k)
        return found, list(getattr(index, "notes", []))
    except IndexNotBuiltError:
        raise
    except (SearchNotConfiguredError, IndexFormatError) as error:
        raise DiscoveryError(str(error)) from error


def _summarise(
    settings: Settings,
    record: RequestRecord,
    hits: list,
    hint: str,
    client: LLMClient | None,
) -> DiscoverSummary:
    """The AI step. If the AI cannot even be set up, the plain results are used instead."""
    try:
        client = client or get_discover_client(settings)
    except (ConfigError, LLMClientError) as error:
        logger.warning("Discover could not set up the AI (%s). Using plain results.", error)
        return fallback_summary(hits, settings.llm_provider, "", 0, [str(error)])
    return summarise_hits(client, record, hits, hint)


# --- helpers ---


@contextmanager
def _write_transaction(db_path: Path) -> Iterator[sqlite3.Connection]:
    with open_db(db_path) as conn:
        # Set up tables before taking the lock: setting up a table ends any open transaction.
        ensure_rulebook_tables(conn)
        ensure_audit_table(conn)
        ensure_discovery_tables(conn)
        ensure_enhance_tables(conn)
        begin_write(conn)
        yield conn


def _start_safety_net_step(conn: sqlite3.Connection, request_id: str, now: datetime) -> None:
    """An enhance request goes on to the safety net (spec section 8): its Enhance step becomes
    `s_writing`. Read inside this transaction, so its own revision cannot be stale. A new-program
    request has no Enhance state and is left alone."""
    state = read_enhance_state(conn, request_id)
    if state is not None and state.step == "e_fresh":
        moved = state.model_copy(update={"step": "s_writing"})
        save_enhance_state(conn, moved, state.revision, now)


def _require_open_request(conn: sqlite3.Connection, request_id: str) -> Request:
    """For developer actions: refused when the request is handed off (Phase 10)."""
    request = _require_request(conn, request_id)
    refuse_if_locked(conn, request_id)
    return request


def _require_request(conn: sqlite3.Connection, request_id: str) -> Request:
    request = read_request(conn, request_id)
    if request is None:
        raise DiscoveryError(f"Request {request_id} does not exist.")
    return request


def _require_status(request: Request, allowed: tuple[str, ...], verb: str) -> None:
    if request.status not in allowed:
        raise DiscoveryError(
            f"This request cannot be {verb} now: its status is "
            f"{display_status(request.status)}."
        )


def _move(conn: sqlite3.Connection, request: Request, status: str, now: datetime) -> Request:
    """One status move through the spec table, audited in the same transaction (rule R6)."""
    moved = update_request(conn, request.request_id, now=now, status=status)
    _audit(
        conn, request.request_id, "system", "status_changed",
        {"from": request.status, "to": status}, now,
    )
    return moved


def _audit(
    conn: sqlite3.Connection,
    request_id: str,
    actor: Actor,
    event_type: str,
    details: dict,
    now: datetime,
) -> None:
    insert_audit_event(conn, request_id, actor, event_type, details, now)


def _say(
    conn: sqlite3.Connection, request_id: str, speaker: Speaker, text: str, now: datetime
) -> None:
    add_message(conn, request_id, speaker, text, now)


def _choices(status: str, can_hint: bool) -> list[str]:
    if status not in _OUTCOME_STATUSES:
        return []
    return [CONFIRM_OPTION, *([HINT_OPTION] if can_hint else []), ESCALATE_OPTION]


def _cap_message(status: str, rounds: int, max_rounds: int) -> str:
    if status in _OUTCOME_STATUSES and rounds >= max_rounds:
        return (
            f"You have used all {max_rounds} search rounds, so you can only confirm the "
            "findings or escalate to a senior developer."
        )
    return ""


def _result_line(result: DiscoveryResult, outcome: str) -> str:
    line = _outcome_line(result, outcome)
    if result.search_provider == "fake":
        line += f"\n{FAKE_INDEX_NOTICE}"
    return line


def _outcome_line(result: DiscoveryResult, outcome: str) -> str:
    matches = sum(1 for finding in result.findings if finding.kind in MATCH_KINDS)
    if outcome == STATUS_SIMILAR_FOUND:
        return (
            f"Round {result.round}: found {matches} existing or similar "
            f"implementation{'s' if matches != 1 else ''} to consider reusing, out of "
            f"{len(result.findings)} finding{'s' if len(result.findings) != 1 else ''}. "
            "Please check them."
        )
    return (
        f"Round {result.round}: no reliable existing implementation was found in approved "
        "sources. That is not proof it does not exist."
    )
