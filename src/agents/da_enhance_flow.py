"""The Enhance conversation, part A: start, switch offer, find the program, pick, fix and confirm
(Phase 9 spec sections 3 and 4). The freshness check comes in part B.

Same pattern as the Understand and Refine flows (rules F1 to F3): every action reads with no lock,
does slow work (the search) outside any transaction, then saves state, rows, chat lines and audit
events in ONE transaction, with the Enhance state's own revision as the stale check. No AI is
called here; plain code finds and the developer confirms (decision 4).

AS400 picture: WRKOBJ to find the member, then a sign-off screen before anything is changed.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from agents.da_approach_checks import normalise_path
from agents.da_enhance_checks import (
    NO_CANDIDATES_TEXT,
    find_round_allowed,
    meaning_candidates,
    merge_candidates,
    name_candidates,
    switch_offer_candidate,
    target_problems,
    with_catalog,
)
from agents.da_search_index import (
    IndexFormatError,
    SearchIndex,
    SearchNotConfiguredError,
    get_search_index,
    search_safely,
)
from agents.da_understand_checks import developer_message_problem
from configs.da_config import Settings
from da_logging import get_logger
from db_table_functions.da_db import begin_write, open_db
from db_table_functions.db_tbl_da_audit import (
    ensure_audit_table,
    insert_audit_event,
    list_audit_events,
)
from db_table_functions.db_tbl_da_enhance import (
    EnhanceError,
    add_unassigned,
    ensure_enhance_tables,
    insert_candidates,
    read_candidates,
    read_enhance_state,
    save_enhance_state,
)
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request, insert_request
from db_table_functions.db_tbl_da_rulebook import ensure_rulebook_tables
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    add_message,
    ensure_understand_tables,
    get_session,
    list_messages,
)
from pydantic_classes.da_discovery_models import SearchFilters
from pydantic_classes.da_enhance_models import (
    Candidate,
    EnhanceState,
    TargetChoice,
    step_label,
)
from pydantic_classes.da_request_record_models import ChatMessage, Speaker
from pydantic_classes.da_rulebook_models import Policy

logger = get_logger(__name__)

NEW_REQUEST_TITLE = "Change to an existing program"
WELCOME = (
    "Name the CodeVision program, or describe it. I'll find it, protect what works today, "
    "and change only what you agree."
)
OFFER_EVENT = "switch_offered"
SWITCHED_EVENT = "switched_to_enhance"
DECLINED_EVENT = "switch_declined"
FIX_PREFIX = "Make it work as intended: "
SEARCH_POOL = 50  # how many raw hits to ask the index for, before the top-k cut
FIND_STEPS = ("e_find", "e_pick")


@dataclass
class EnhanceView:
    """Everything the screen needs for the Find steps. Built by get_enhance_view."""

    request_id: str
    kind: str
    step: str
    label: str
    revision: int
    candidates: list[Candidate] = field(default_factory=list)
    targets: list[TargetChoice] = field(default_factory=list)
    capability_names: list[str] = field(default_factory=list)
    searches_left: int = 0
    change_prefill: str = ""
    messages: list[ChatMessage] = field(default_factory=list)


@dataclass
class _Tx:
    """One action's work inside its write transaction."""

    conn: sqlite3.Connection
    request_id: str
    now: datetime

    def say(self, speaker: Speaker, text: str) -> None:
        add_message(self.conn, self.request_id, speaker, text, self.now)

    def audit(self, actor, event_type: str, details: dict | None = None) -> None:
        insert_audit_event(self.conn, self.request_id, actor, event_type, details, self.now)


# --- start (card 2) ---


def start_enhance_request(
    settings: Settings, developer_id: str | None = None, now: datetime | None = None
) -> EnhanceView:
    """Home card 2: a new request of kind `enhance` at step e_find. The request keeps the status
    a new request has before Understand (DRAFT); the header pill shows the step label."""
    now = now or datetime.now(UTC)
    with _write_transaction(settings.db_path) as conn:
        request = insert_request(
            conn, NEW_REQUEST_TITLE, developer_id or settings.developer_id, now
        )
        tx = _Tx(conn, request.request_id, now)
        tx.audit("developer", "request_created", {"rulebook_version": request.rulebook_version})
        tx.audit("developer", "enhance_started", {"kind": "enhance"})
        tx.say("assistant", WELCOME)
        save_enhance_state(conn, EnhanceState(request_id=request.request_id), 0, now)
    logger.info("Created Enhance request %s", request.request_id)
    return _view(settings, request.request_id)


# --- find (card 2, spec section 4) ---


def find_program(
    settings: Settings,
    request_id: str,
    message: str,
    base_revision: int,
    index: SearchIndex | None = None,
    now: datetime | None = None,
) -> EnhanceView:
    """One search round: by name and by meaning, merged, with the catalog filled in."""
    now = now or datetime.now(UTC)
    text = _accept_text(message)
    state = _load_state(settings, request_id, base_revision, FIND_STEPS)
    policy = _policy(settings, request_id)
    if not find_round_allowed(state.find_rounds_used, policy):
        raise EnhanceError(
            f"I searched {state.find_rounds_used} times and found nothing you confirmed. "
            "Please use Get help."
        )
    candidates, by_name, by_meaning = _search(index or get_search_index(settings), text, policy)
    with _write_transaction(settings.db_path) as conn:
        tx = _Tx(conn, request_id, now)
        round_number = state.find_rounds_used + 1
        tx.say("developer", text)
        insert_candidates(conn, request_id, round_number, candidates, now)
        tx.audit(
            "system",
            "enhance_search",
            {"round": round_number, "by_name": by_name, "by_meaning": by_meaning},
        )
        tx.say("assistant", _found_message(candidates))
        new = state.model_copy(
            update={
                "step": "e_pick" if candidates else "e_find",
                "find_rounds_used": round_number,
                "targets": [],
            }
        )
        save_enhance_state(conn, new, base_revision, now)
    return _view(settings, request_id)


def mark_as_fix(
    settings: Settings, request_id: str, base_revision: int, now: datetime | None = None
) -> EnhanceView:
    """"This is a fix" at e_pick (D-M): kind becomes `fix` and "What should change?" is pre-filled
    with "Make it work as intended: <his opening statement>"."""
    now = now or datetime.now(UTC)
    state = _load_state(settings, request_id, base_revision, ("e_pick",))
    opening = _first_developer_text(settings, request_id)
    with _write_transaction(settings.db_path) as conn:
        tx = _Tx(conn, request_id, now)
        tx.audit("developer", "marked_as_fix", {})
        tx.say("assistant", "Noted: this is a fix. I will pre-fill what should change for you.")
        new = state.model_copy(update={"kind": "fix", "change_prefill": FIX_PREFIX + opening})
        save_enhance_state(conn, new, base_revision, now)
    return _view(settings, request_id)


def confirm_targets(
    settings: Settings,
    request_id: str,
    paths: list[str],
    capability_picks: dict[str, str],
    base_revision: int,
    now: datetime | None = None,
) -> EnhanceView:
    """"Yes, that's it" (one or more ticked programs). A program in no capability needs a pick
    from the catalog; it goes into the Unassigned queue with his pick (spec section 4, step 8)."""
    now = now or datetime.now(UTC)
    state = _load_state(settings, request_id, base_revision, ("e_pick",))
    policy = _policy(settings, request_id)
    chosen = _chosen_candidates(settings, request_id, paths)
    problems = target_problems(paths, policy) + _capability_problems(
        chosen, capability_picks, policy
    )
    if problems:
        raise EnhanceError("\n".join(problems))
    targets = [_target_choice(item, capability_picks, policy) for item in chosen]
    with _write_transaction(settings.db_path) as conn:
        tx = _Tx(conn, request_id, now)
        for target in targets:
            if not target.capability_confirmed:
                add_unassigned(conn, target.path, target.capability, request_id, now)
                tx.audit(
                    "developer",
                    "capability_picked",
                    {"path": target.path, "capability": target.capability},
                )
        tx.audit(
            "developer",
            "targets_confirmed",
            {
                "paths": [t.path for t in targets],
                "capability": [t.capability for t in targets],
                "how_found": [t.how_found for t in targets],
            },
        )
        tx.say("developer", "Yes, that's it: " + ", ".join(t.path for t in targets))
        tx.say("assistant", _confirmed_message(targets))
        save_enhance_state(conn, state.model_copy(update={"targets": targets}), base_revision, now)
    return _view(settings, request_id)


# --- the switch offer on card 1 (D-N) ---


def maybe_offer_switch(
    settings: Settings,
    request_id: str,
    index: SearchIndex | None = None,
    now: datetime | None = None,
) -> Candidate | None:
    """Called after the card 1 form is submitted. Plain code only, no AI call. Offers once, and
    only for a Best match; never again after an offer or a decline. Never raises for a missing or
    unreadable index: the offer is a convenience."""
    now = now or datetime.now(UTC)
    if _offer_history(settings, request_id):
        return None
    text = "\n".join(m.text for m in list_messages(settings.db_path, request_id)
                     if m.speaker == "developer")
    try:
        policy = _policy(settings, request_id)
        hits, _dropped = search_safely(
            index or get_search_index(settings), text, "exact", SearchFilters(), SEARCH_POOL
        )
    except (SearchNotConfiguredError, IndexFormatError):
        return None
    offer = switch_offer_candidate(text, hits)
    if offer is None:
        return None
    offer = with_catalog(offer, policy.capabilities)
    with _write_transaction(settings.db_path) as conn:
        tx = _Tx(conn, request_id, now)
        tx.audit("system", OFFER_EVENT, {"path": offer.path})
        tx.say(
            "assistant",
            f"This sounds like a change to `{offer.path}`, which already exists. "
            "Switch to Enhance or fix?",
        )
    return offer


def switch_to_enhance(
    settings: Settings,
    request_id: str,
    base_revision: int,
    now: datetime | None = None,
) -> EnhanceView:
    """"Switch to Enhance or fix": the same CVDA number, kind `enhance`, the opening statement
    kept, step e_pick with the offered program first. `base_revision` is the Understand session
    revision the screen showed (the request is still on card 1's flow until now)."""
    now = now or datetime.now(UTC)
    path = _open_offer(settings, request_id, base_revision)
    policy = _policy(settings, request_id)
    offered = with_catalog(
        Candidate(path=path, how_found="name", score=1.0, best_match=True), policy.capabilities
    )
    with _write_transaction(settings.db_path) as conn:
        tx = _Tx(conn, request_id, now)
        tx.audit("developer", SWITCHED_EVENT, {"path": path})
        insert_candidates(conn, request_id, 1, [offered], now)
        tx.say("assistant", _found_message([offered]))
        state = EnhanceState(request_id=request_id, step="e_pick", find_rounds_used=1)
        save_enhance_state(conn, state, 0, now)
    return _view(settings, request_id)


def decline_switch(
    settings: Settings, request_id: str, base_revision: int, now: datetime | None = None
) -> None:
    """"No, this is new": never asked again on this request (audit `switch_declined`)."""
    now = now or datetime.now(UTC)
    _open_offer(settings, request_id, base_revision)
    with _write_transaction(settings.db_path) as conn:
        tx = _Tx(conn, request_id, now)
        tx.audit("developer", DECLINED_EVENT, {})
        tx.say("assistant", "Understood: this stays a new program.")


# --- reading ---


def get_enhance_view(settings: Settings, request_id: str) -> EnhanceView | None:
    """None when the request is not an Enhance request (no Enhance state)."""
    with _read(settings.db_path) as conn:
        if read_enhance_state(conn, request_id) is None:
            return None
    return _view(settings, request_id)


def _view(settings: Settings, request_id: str) -> EnhanceView:
    with _read(settings.db_path) as conn:
        state = read_enhance_state(conn, request_id)
        rounds = read_candidates(conn, request_id)
    if state is None:
        raise EnhanceError(f"Request {request_id} is not an Enhance request.")
    policy = _policy(settings, request_id)
    return EnhanceView(
        request_id=request_id,
        kind=state.kind,
        step=state.step,
        label=step_label(state.step),
        revision=state.revision,
        candidates=rounds[-1] if rounds else [],
        targets=state.targets,
        capability_names=[item.name for item in policy.capabilities],
        searches_left=max(policy.enhance_find_max_rounds - state.find_rounds_used, 0),
        change_prefill=state.change_prefill,
        messages=list_messages(settings.db_path, request_id),
    )


# --- helpers ---


def _search(
    index: SearchIndex, text: str, policy: Policy
) -> tuple[list[Candidate], int, int]:
    """(candidates with the catalog filled in, files found by name, files found by meaning)."""
    filters = SearchFilters()
    try:
        name_hits, _ = search_safely(index, text, "exact", filters, SEARCH_POOL)
        meaning_hits, _ = search_safely(index, text, "meaning", filters, SEARCH_POOL)
    except (SearchNotConfiguredError, IndexFormatError) as error:
        raise EnhanceError(str(error)) from error
    by_name = name_candidates(text, name_hits, policy.enhance_name_top_k)
    by_meaning = meaning_candidates(meaning_hits, policy.enhance_meaning_top_k)
    merged = merge_candidates(by_name, by_meaning)
    return [with_catalog(c, policy.capabilities) for c in merged], len(by_name), len(by_meaning)


def _found_message(candidates: list[Candidate]) -> str:
    if not candidates:
        return NO_CANDIDATES_TEXT
    best = next((c for c in candidates if c.best_match), None)
    if best is None:
        return (
            f"I found {len(candidates)} possible program(s). Pick the right one, "
            "or search again."
        )
    if best.capability:
        return (
            f"Best match: `{best.path}` in the `{best.capability}` capability. "
            "Is this the right program?"
        )
    return f"Best match: `{best.path}`, which is not in the catalog yet. Is this the right program?"


def _chosen_candidates(settings: Settings, request_id: str, paths: list[str]) -> list[Candidate]:
    """The candidates he ticked. A path that no search showed him cannot be confirmed."""
    with _read(settings.db_path) as conn:
        shown = {c.path: c for round_ in read_candidates(conn, request_id) for c in round_}
    chosen: list[Candidate] = []
    for raw in paths:
        path = normalise_path(raw)
        if path not in shown:
            raise EnhanceError(f"{path} was not one of the programs I found. Search for it first.")
        chosen.append(shown[path])
    return chosen


def _capability_problems(
    chosen: list[Candidate], picks: dict[str, str], policy: Policy
) -> list[str]:
    names = {item.name for item in policy.capabilities}
    problems = []
    for item in chosen:
        if item.capability:
            continue
        pick = picks.get(item.path, "")
        if pick not in names:
            problems.append(
                f"{item.path} is not in the catalog. Pick the capability it belongs to."
            )
    return problems


def _target_choice(item: Candidate, picks: dict[str, str], policy: Policy) -> TargetChoice:
    if item.capability:
        return TargetChoice(
            path=item.path,
            how_found=item.how_found,
            capability=item.capability,
            named_senior=item.named_senior,
        )
    picked = next(c for c in policy.capabilities if c.name == picks[item.path])
    return TargetChoice(
        path=item.path,
        how_found=item.how_found,
        capability=picked.name,
        named_senior=picked.named_senior,
        capability_confirmed=False,
    )


def _confirmed_message(targets: list[TargetChoice]) -> str:
    lines = ["Program confirmed."]
    for target in targets:
        senior = f" Named senior: {target.named_senior}." if target.named_senior else ""
        note = " Capability not yet confirmed by Admin." if not target.capability_confirmed else ""
        lines.append(f"`{target.path}` is in the `{target.capability}` capability.{senior}{note}")
    return "\n".join(lines)


def _offer_history(settings: Settings, request_id: str) -> list[str]:
    """The switch events of this request, oldest first: offered, switched, declined."""
    wanted = {OFFER_EVENT, SWITCHED_EVENT, DECLINED_EVENT}
    return [e.event_type for e in list_audit_events(settings.db_path, request_id)
            if e.event_type in wanted]


def _open_offer(settings: Settings, request_id: str, base_revision: int) -> str:
    """The path that was offered and not yet answered; refuses a stale window or a closed offer."""
    session = get_session(settings.db_path, request_id)
    if session is None:
        raise EnhanceError(f"Request {request_id} does not exist.")
    if session.revision != base_revision:
        raise StaleRevisionError(STALE_MESSAGE)
    history = _offer_history(settings, request_id)
    if history != [OFFER_EVENT]:
        raise EnhanceError("There is no switch offer to answer on this request.")
    events = [e for e in list_audit_events(settings.db_path, request_id)
              if e.event_type == OFFER_EVENT]
    return events[-1].details["path"]


def _first_developer_text(settings: Settings, request_id: str) -> str:
    for message in list_messages(settings.db_path, request_id):
        if message.speaker == "developer":
            return message.text
    return ""


def _accept_text(text: str) -> str:
    """Refuse an empty, too long or secret-looking message before it is saved (R8, R9)."""
    problem = developer_message_problem(text)
    if problem:
        raise EnhanceError(problem)
    return text.strip()


def _policy(settings: Settings, request_id: str) -> Policy:
    return get_rulebook_for_request(settings.db_path, request_id).rulebook.policy


def _load_state(
    settings: Settings, request_id: str, base_revision: int, steps: tuple[str, ...]
) -> EnhanceState:
    """Read with no lock; refuse a stale window or the wrong step before any slow work."""
    with _read(settings.db_path) as conn:
        state = read_enhance_state(conn, request_id)
    if state is None:
        raise EnhanceError(f"Request {request_id} is not an Enhance request.")
    if state.revision != base_revision:
        raise StaleRevisionError(STALE_MESSAGE)
    if state.step not in steps:
        raise EnhanceError("That action is not available at this step.")
    return state


@contextmanager
def _read(db_path: Path) -> Iterator[sqlite3.Connection]:
    with open_db(db_path) as conn:
        _ensure(conn)
        yield conn


@contextmanager
def _write_transaction(db_path: Path) -> Iterator[sqlite3.Connection]:
    with open_db(db_path) as conn:
        # Set up tables before taking the lock: setting up a table ends any open transaction.
        _ensure(conn)
        begin_write(conn)
        yield conn


def _ensure(conn: sqlite3.Connection) -> None:
    ensure_rulebook_tables(conn)
    ensure_audit_table(conn)
    ensure_understand_tables(conn)
    ensure_enhance_tables(conn)
