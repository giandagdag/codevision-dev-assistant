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
from agents.da_build_agent import AIResult, get_build_client
from agents.da_enhance_agent import TODAY_ROLE, draft_today
from agents.da_enhance_checks import (
    NO_CANDIDATES_TEXT,
    available_symbols,
    find_round_allowed,
    meaning_candidates,
    merge_candidates,
    name_candidates,
    switch_offer_candidate,
    target_problems,
    with_catalog,
)
from agents.da_impact import find_impact
from agents.da_llm_client import LLMClient
from agents.da_main_source import (
    MainSourceError,
    check_freshness,
    get_main_source,
    next_step,
    stale_message,
    stale_options,
)
from agents.da_search_index import (
    IndexFormatError,
    SearchIndex,
    SearchNotConfiguredError,
    get_search_index,
    search_safely,
)
from agents.da_understand_checks import developer_message_problem
from agents.da_workspace_checks import fingerprint, line_ending_of
from configs.da_config import ConfigError, Settings
from da_logging import get_logger
from db_table_functions.da_db import begin_write, open_db
from db_table_functions.db_tbl_da_approach import read_latest_approach
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
    insert_freshness_check,
    read_candidates,
    read_enhance_state,
    read_latest_freshness,
    save_enhance_state,
)
from db_table_functions.db_tbl_da_requests import (
    get_rulebook_for_request,
    insert_request,
    read_request,
    update_request,
)
from db_table_functions.db_tbl_da_rulebook import ensure_rulebook_tables
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    add_message,
    ensure_understand_tables,
    get_session,
    insert_session,
    list_messages,
)
from db_table_functions.db_tbl_da_workspace import (
    ensure_workspace_tables,
    insert_workspace_file,
    read_file_versions,
)
from pydantic_classes.da_discovery_models import SearchFilters
from pydantic_classes.da_enhance_models import (
    Candidate,
    EnhanceState,
    FreshnessResult,
    ImpactResult,
    PathFreshness,
    TargetChoice,
    TodayDraft,
    step_label,
)
from pydantic_classes.da_models import STATUS_CLARIFICATION
from pydantic_classes.da_request_record_models import (
    ChatMessage,
    RecordFreshness,
    RequestRecord,
    Speaker,
    UnderstandSession,
)
from pydantic_classes.da_rulebook_models import Policy
from pydantic_classes.da_workspace_models import FileFact, WorkspaceFile

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
# No record exists before Understand, so the first record version stands in (version numbers
# start at 1).
RECORD_VERSION_BEFORE_UNDERSTAND = 1
FORM_MESSAGE = (
    "Thanks. Check what it does today, say what should change and what must NOT change, "
    "then press Submit. The last box is optional."
)
FORM_MESSAGE_NO_DRAFT = (
    "I could not draft what the program does today. Please write it yourself in the first box, "
    "say what should change and what must NOT change, then press Submit."
)
OVERRIDE_LABELS = {
    "intentional": "My local changes are intentional",
    "unchecked": "Continue without the check",
}
OVERRIDE_REPLIES = {
    "intentional": "Noted: your local changes are intentional. This goes into the PR summary.",
    "unchecked": "Continuing without the freshness check. This goes into the PR summary.",
}


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
    # Part B: the latest freshness check (None before the first) and the buttons the stale
    # banner shows ("check_again", "intentional", "unchecked").
    freshness: FreshnessResult | None = None
    stale_options: list[str] = field(default_factory=list)


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


# --- Understand, enhancement mode: start (spec section 6, steps 1 to 3) ---


def baseline_texts(settings: Settings, request_id: str) -> dict[str, str]:
    """Today's code for each confirmed target: the latest baseline taken at freshness (D-G)."""
    with _read(settings.db_path) as conn:
        state = read_enhance_state(conn, request_id)
        if state is None:
            raise EnhanceError(f"Request {request_id} is not an Enhance request.")
        texts: dict[str, str] = {}
        for target in state.targets:
            versions = [v for v in read_file_versions(conn, request_id, target.path)
                        if v.kind == "baseline"]
            if versions:
                texts[target.path] = versions[-1].text
    return texts


def start_understand(
    settings: Settings,
    request_id: str,
    base_revision: int,
    client: LLMClient | None = None,
    now: datetime | None = None,
) -> EnhanceView:
    """Freshness passed (e_fresh): make the Understand session for this request, with ONE
    today-draft call (no chat is sent, only the target's functions). A draft that cannot be used
    leaves the box empty; he writes it himself. The draft's guess of the functions in scope is
    kept in the record for him to tick or untick at the checkpoint."""
    now = now or datetime.now(UTC)
    state = _load_state(settings, request_id, base_revision, ("e_fresh",))
    if get_session(settings.db_path, request_id) is not None:
        raise EnhanceError("Understand has already started for this request.")
    pinned = get_rulebook_for_request(settings.db_path, request_id)
    files = baseline_texts(settings, request_id)
    try:
        client = client or get_build_client(settings, TODAY_ROLE)
        drafted = draft_today(
            client, pinned.rulebook.charter.purpose, request_id,
            _first_developer_text(settings, request_id), files,
            pinned.rulebook.policy.build_max_prompt_chars,
        )
    except ConfigError as error:  # for example the work server is "not configured yet"
        drafted = AIResult(None, kind="unreachable", message=str(error))
    draft = drafted.value
    with _write_transaction(settings.db_path) as conn:
        tx = _Tx(conn, request_id, now)
        request = read_request(conn, request_id)
        latest = read_latest_freshness(conn, request_id)
        record = _enhance_record(request, state, latest.result if latest else None, draft)
        insert_session(
            conn, UnderstandSession(request_id=request_id, record=record, step="form"), now
        )
        tx.audit(
            "system", "today_drafted",
            {"attempts": drafted.attempts, "ok": draft is not None, "kind": drafted.kind or "ok"},
        )
        update_request(conn, request_id, now=now, status=STATUS_CLARIFICATION)
        tx.audit("system", "status_changed", {"from": request.status, "to": STATUS_CLARIFICATION})
        if drafted.message and draft is not None:
            tx.say("assistant", drafted.message)
        tx.say("assistant", FORM_MESSAGE if draft is not None else FORM_MESSAGE_NO_DRAFT)
        save_enhance_state(conn, state, base_revision, now)
    return _view(settings, request_id)


def _enhance_record(
    request, state: EnhanceState, freshness: FreshnessResult | None, draft: TodayDraft | None
) -> RequestRecord:
    first = state.targets[0]
    summary = "" if freshness is None else (
        "equal" if freshness.all_equal else ",".join(sorted({p.state for p in freshness.paths}))
    )
    return RequestRecord(
        request_id=request.request_id,
        rulebook_version=request.rulebook_version,
        kind=state.kind,
        targets=[target.path for target in state.targets],
        today=draft.today if draft else "",
        functions_in_scope=draft.functions_in_scope_guess if draft else [],
        capability=first.capability,
        capability_confirmed=all(t.capability_confirmed for t in state.targets),
        named_senior=first.named_senior,
        freshness=RecordFreshness(
            result=summary, override=freshness.override if freshness else ""
        ),
    )


# --- impact for a Discover round (spec section 7) ---


def impact_for_record(settings: Settings, record: RequestRecord) -> ImpactResult | None:
    """Who calls the functions in scope. None for a new-program request. Plain code, no AI, no lock:
    it reads the server's reference copy (never his folder, R1) and the saved baselines. A missing
    reference copy gives "could not be checked", and the request goes on."""
    if record.kind == "new":
        return None
    from agents.da_build_loop import resolve_reference_dir  # late: that module is large

    policy = get_rulebook_for_request(settings.db_path, record.request_id)
    rules = policy.rulebook.policy
    texts = baseline_texts(settings, record.request_id)
    scope_by_target: dict[str, list[str]] = {}
    for path, text in texts.items():
        symbols = set(available_symbols(path, text))
        wanted = [name for name in record.functions_in_scope if name in symbols]
        if wanted:
            scope_by_target[path] = wanted
    return find_impact(
        resolve_reference_dir(settings), scope_by_target, rules.capabilities,
        rules.flag_review_zones, rules.impact_max_callers,
    )


# --- freshness (spec section 5) ---


def browser_read_paths(settings: Settings, request_id: str) -> list[str]:
    """The only files the browser may read for this request (9-48, rule R1): the confirmed
    targets until an Approach exists, the planned files after. Reads only; saves nothing."""
    with _read(settings.db_path) as conn:
        state = read_enhance_state(conn, request_id)
        approach = read_latest_approach(conn, request_id)
    if state is None:
        raise EnhanceError(f"Request {request_id} is not an Enhance request.")
    if approach is not None:
        return [normalise_path(item.path) for item in approach.plan.files]
    return [target.path for target in state.targets]


def run_freshness(
    settings: Settings,
    request_id: str,
    facts: list[FileFact],
    base_revision: int,
    now: datetime | None = None,
) -> EnhanceView:
    """Freshness check, also "I've updated, check again" and "Try again": the browser sent each
    target as it is in his folder; the server compares it with main. All equal: the text becomes
    the baseline and the step is e_fresh. Anything else: e_stale, nothing silently passed."""
    now = now or datetime.now(UTC)
    state = _load_state(settings, request_id, base_revision, ("e_pick", "e_stale"))
    _require_targets(state)
    texts = _texts_from_facts(facts, state, _policy(settings, request_id))
    result = check_freshness(texts, get_main_source(settings))  # slow: outside the transaction
    step = next_step(result)
    with _write_transaction(settings.db_path) as conn:
        tx = _Tx(conn, request_id, now)
        insert_freshness_check(conn, request_id, RECORD_VERSION_BEFORE_UNDERSTAND, result, now)
        tx.audit("system", "freshness_checked", _check_details(result))
        tx.say("assistant", stale_message(result))
        if step == "e_fresh":
            _save_baselines(tx, texts)
        save_enhance_state(conn, state.model_copy(update={"step": step}), base_revision, now)
    return _view(settings, request_id)


def override_freshness(
    settings: Settings,
    request_id: str,
    which: str,
    facts: list[FileFact],
    base_revision: int,
    now: datetime | None = None,
) -> EnhanceView:
    """"My local changes are intentional" (`intentional`) or "Continue without the check"
    (`unchecked`). Allowed only when the latest check offered it. The text must still be the one
    that was checked, so the baseline is what he saw. Stored and audited for the PR summary."""
    now = now or datetime.now(UTC)
    state = _load_state(settings, request_id, base_revision, ("e_stale",))
    with _read(settings.db_path) as conn:
        latest = read_latest_freshness(conn, request_id)
    if latest is None or which not in stale_options(latest.result):
        raise EnhanceError("That choice is not available for this freshness result.")
    texts = _texts_from_facts(facts, state, _policy(settings, request_id))
    checked = {item.path: item.his_fingerprint for item in latest.result.paths}
    if any(fingerprint(text) != checked[path] for path, text in texts.items() if text is not None):
        raise EnhanceError("Your folder changed since the check. Please check again.")
    result = latest.result.model_copy(update={"override": which})
    with _write_transaction(settings.db_path) as conn:
        tx = _Tx(conn, request_id, now)
        insert_freshness_check(conn, request_id, RECORD_VERSION_BEFORE_UNDERSTAND, result, now)
        tx.audit("developer", "freshness_override", {"which": which})
        tx.say("developer", OVERRIDE_LABELS[which])
        tx.say("assistant", OVERRIDE_REPLIES[which])
        _save_baselines(tx, texts)
        new = state.model_copy(update={"step": "e_fresh"})
        save_enhance_state(conn, new, base_revision, now)
    return _view(settings, request_id)


def recheck_main(
    settings: Settings, request_id: str, now: datetime | None = None
) -> FreshnessResult | None:
    """Freshness again at the first workspace check (spec section 5, step 8). If the `main` version
    of a target is no longer the one seen at Find, the e_stale banner shows again and the workspace
    check is refused until he checks again. None: not an Enhance request, or nothing changed.

    Only `main` is looked at here: his own edits since the baseline are the Phase 6 pre-build
    re-scan's job. A `main` that cannot be reached now is stale too, unless he already chose
    "Continue without the check"."""
    now = now or datetime.now(UTC)
    with _read(settings.db_path) as conn:
        state = read_enhance_state(conn, request_id)
        latest = read_latest_freshness(conn, request_id)
    if state is None or latest is None or not state.targets:
        return None
    source = get_main_source(settings)  # slow calls below, outside any transaction
    paths = [_recheck_path(item, source, latest.result.override) for item in latest.result.paths]
    if paths == latest.result.paths:
        return None
    result = FreshnessResult(paths=paths, main_source=source.name)
    with _write_transaction(settings.db_path) as conn:
        tx = _Tx(conn, request_id, now)
        insert_freshness_check(conn, request_id, RECORD_VERSION_BEFORE_UNDERSTAND, result, now)
        tx.audit("system", "freshness_checked", {**_check_details(result), "recheck": True})
        tx.say("assistant", stale_message(result))
        save_enhance_state(
            conn, state.model_copy(update={"step": "e_stale"}), state.revision, now
        )
    return result


def _recheck_path(item: PathFreshness, source, override: str) -> PathFreshness:
    """The saved row, unless the file on main is no longer the version seen at Find."""
    if not item.main_fingerprint:
        return item  # was not on main, or main was out of reach: his choice at Find stands
    try:
        main_text = source.get_text(item.path)
    except MainSourceError:
        if override == "unchecked":
            return item
        return item.model_copy(update={"state": "unreachable"})
    now_fingerprint = fingerprint(main_text) if main_text is not None else ""
    if now_fingerprint == item.main_fingerprint:
        return item
    state = "differs" if main_text is not None else "not_on_main"
    return item.model_copy(update={"state": state, "main_fingerprint": now_fingerprint})


def _require_targets(state: EnhanceState) -> None:
    if not state.targets:
        raise EnhanceError("Confirm the program first; then I can check it is up to date.")


def _texts_from_facts(
    facts: list[FileFact], state: EnhanceState, policy: Policy
) -> dict[str, str | None]:
    """His folder's text for each target, in target order. The browser may send exactly the
    confirmed targets and nothing else (9-48); a file too big or not UTF-8 is refused."""
    wanted = [target.path for target in state.targets]
    sent = {normalise_path(item.path): item for item in facts}
    if len(sent) != len(facts) or set(sent) != set(wanted):
        raise EnhanceError("The files sent are not the confirmed program(s). Please try again.")
    limit = policy.workspace_max_file_kb * 1024
    texts: dict[str, str | None] = {}
    for path in wanted:
        fact = sent[path]
        if fact.too_big or fact.not_utf8:
            reason = "too big to read" if fact.too_big else "not UTF-8 text"
            raise EnhanceError(f"`{path}` is {reason}, so I cannot check it.")
        if not fact.exists:
            texts[path] = None
            continue
        if fact.text is None or len(fact.text.encode("utf-8")) > limit:
            raise EnhanceError(f"`{path}` could not be read. Please choose the folder again.")
        if fact.fingerprint is not None and fact.fingerprint != fingerprint(fact.text):
            raise EnhanceError(f"`{path}` did not arrive intact. Please try again.")
        texts[path] = fact.text
    return texts


def _save_baselines(tx: _Tx, texts: dict[str, str | None]) -> None:
    """His text becomes the baseline: today's code for the rest of Phase 9 (D-G)."""
    saved: dict[str, str] = {}
    for path, text in texts.items():
        if text is None:
            continue
        insert_workspace_file(
            tx.conn,
            WorkspaceFile(
                request_id=tx.request_id, path=path, file_version=1, kind="baseline", text=text,
                fingerprint=fingerprint(text), line_ending=line_ending_of(text),
            ),
            tx.now,
        )
        saved[path] = fingerprint(text)
    tx.audit("system", "enhance_baseline_taken", {"files": saved})


def _check_details(result: FreshnessResult) -> dict:
    return {
        "paths": [{"path": item.path, "state": item.state} for item in result.paths],
        "main_source": result.main_source,
    }


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
        latest = read_latest_freshness(conn, request_id)
    if state is None:
        raise EnhanceError(f"Request {request_id} is not an Enhance request.")
    policy = _policy(settings, request_id)
    stale = state.step == "e_stale" and latest is not None
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
        freshness=latest.result if latest else None,
        stale_options=stale_options(latest.result) if stale else [],
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
    ensure_workspace_tables(conn)
    ensure_enhance_tables(conn)
