"""His picks on a rebuild's conflicts, and Apply my choices (Phase 8, R5.3 steps 4 to 7).

AS400 picture: two programmers changed the same source member. The app shows both versions of each
clashing place; he picks one per place; only then is the member saved.

Nothing here writes to his folder. "Apply my choices" either lets the normal write run on the tested
result (all picks are the AI's) or starts a check run on the merged files (any Keep mine, D-K). The
write itself is the Phase 6 write, with the Phase 5 edit guard (R5.1).
"""

import sqlite3
from datetime import UTC, datetime

from agents.da_build_flow import (
    STARTED_MESSAGE,
    BuildTx,
    _approach_of,
    _check_revision,
    _require_request,
    _require_step,
    _save,
    _write,
    get_state,
    planned_paths_of,
)
from agents.da_refine_merge import merge_picks as merge_file
from agents.da_refine_merge import plan_merge
from agents.da_workspace_checks import fingerprint
from db_table_functions.db_tbl_da_build import (
    BuildError,
    insert_build_file,
    insert_build_run,
    next_build_number,
    read_build_state,
    read_latest_code,
)
from db_table_functions.db_tbl_da_refine import insert_conflict_row, read_conflicts
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request
from db_table_functions.db_tbl_da_workspace import read_file_versions
from pydantic_classes.da_build_models import BuildFile, BuildRun, BuildState
from pydantic_classes.da_models import STATUS_BUILDING

STEP = "b_conflicts"
KEEP_MINE, TAKE_AI = "mine", "ai"
CHOICES = (KEEP_MINE, TAKE_AI)
APPLY_LABEL = "Apply my choices"


def pick(
    settings,
    request_id: str,
    path: str,
    conflict_id: str,
    choice: str,
    base_revision: int,
    now: datetime | None = None,
) -> BuildState:
    """Save one pick (Keep mine or Take the AI's). A new row is added; the newest row per conflict
    is its state, so he can change his mind until he applies. Audited as `conflict_resolved`."""
    now = now or datetime.now(UTC)
    if choice not in CHOICES:
        raise BuildError("Pick Keep mine or Take the AI's.")
    with _write(settings.db_path) as conn:
        request = _require_request(conn, request_id)
        _check_revision(conn, request_id, base_revision)
        state = read_build_state(conn, request_id)
        _require_step(state or BuildState(request_id=request_id), STEP)
        stored = read_conflicts(conn, request_id, state.build_number)
        found = {(c.path, c.conflict_id): c for c in stored}
        item = found.get((path, conflict_id))
        if item is None:
            raise BuildError(f"There is no conflict {conflict_id} in {path}.")
        tx = BuildTx(conn, request, state, now)
        insert_conflict_row(
            conn, request_id, state.build_number, item.model_copy(update={"choice": choice}), now
        )
        tx.audit(
            "developer",
            "conflict_resolved",
            {"conflict_id": conflict_id, "path": path, "choice": choice},
        )
        tx.set()  # the revision goes up, so an old window is refused
        _save(tx, base_revision)
    return get_state(settings, request_id)


def apply_choices(
    settings, request_id: str, base_revision: int, now: datetime | None = None
) -> BuildState:
    """Apply my choices. Every conflict needs a pick.

    All picks Take the AI's: the tested result stays as it is, the step moves to b_done and the
    normal write follows (no check run). Any Keep mine: the merged files were never tested, so a
    check run is started on them (D-K); it ends at b_done and the write follows, either way. The
    check run's loop is started by the caller (the runner), as for Check my edits."""
    now = now or datetime.now(UTC)
    # The rulebook is read before the write transaction (a second connection inside one can lock).
    policy = get_rulebook_for_request(settings.db_path, request_id).rulebook.policy
    with _write(settings.db_path) as conn:
        request = _require_request(conn, request_id)
        _check_revision(conn, request_id, base_revision)
        state = read_build_state(conn, request_id)
        _require_step(state or BuildState(request_id=request_id), STEP)
        stored = read_conflicts(conn, request_id, state.build_number)
        open_ones = [c.conflict_id for c in stored if c.choice not in CHOICES]
        if open_ones or not stored:
            raise BuildError("Pick Keep mine or Take the AI's for every conflict first.")
        picks = {(c.path, c.conflict_id): c.choice for c in stored}
        tx = BuildTx(conn, request, state, now)
        tx.say("developer", APPLY_LABEL)
        mine = sum(1 for choice in picks.values() if choice == KEEP_MINE)
        tx.audit("developer", "conflicts_applied", {"mine": mine, "ai": len(picks) - mine})
        if not mine:
            tx.say("assistant", "All your picks take the AI's version. Writing the tested result.")
            tx.set(step="b_done")
        else:
            merged = merged_texts(
                conn, request_id, state, picks, policy.refine_conflict_context_lines
            )
            _start_merge_check(tx, merged, request.status)
        _save(tx, base_revision)
    return get_state(settings, request_id)


def merged_texts(
    conn: sqlite3.Connection,
    request_id: str,
    state: BuildState,
    picks: dict[tuple[str, str], str],
    distance: int,
) -> dict[str, str]:
    """The text each planned file gets. A file with no Keep mine keeps the tested result, byte for
    byte. A file with a Keep mine is his version with the free changes and his picks applied."""
    code = read_latest_code(conn, request_id, state.build_number)
    texts = {}
    for path in planned_paths_of(_approach_of(conn, request_id, state)):
        built = code.get(path)
        if built is None:
            continue
        texts[path] = built.text
        mine_here = any(p == path and choice == KEEP_MINE for (p, _), choice in picks.items())
        if not mine_here:
            continue
        versions = read_file_versions(conn, request_id, path)
        written = [v for v in versions if v.kind == "written"]
        plan = plan_merge(
            path, written[-1].text, versions[-1].text, built.text, distance, distance
        )
        by_id = {c_id: choice for (p, c_id), choice in picks.items() if p == path}
        texts[path] = merge_file(plan, by_id)
    return texts


def _start_merge_check(tx: BuildTx, merged: dict[str, str], came_from: str) -> None:
    """A check run (no Generator, no budget) on the merged files. Its files are saved first, made
    by `merge`, so the loop tests exactly these texts and the write afterwards writes them."""
    conn = tx.conn
    number = next_build_number(conn, tx.request.request_id)
    insert_build_run(
        conn,
        BuildRun(
            request_id=tx.request.request_id,
            build_number=number,
            approach_version=tx.state.approach_version,
            started_at=tx.now,
            kind="check",
        ),
    )
    for path, text in merged.items():
        insert_build_file(
            conn,
            BuildFile(
                request_id=tx.request.request_id,
                build_number=number,
                round=1,
                path=path,
                kind="code",
                text=text,
                fingerprint=fingerprint(text),
                made_by="merge",
            ),
            tx.now,
        )
    tx.audit("system", "merge_check_started", {"build": number})
    tx.say("assistant", "Your picks are not tested yet. I am checking the merged files first.")
    tx.move_to(STATUS_BUILDING)
    tx.say("assistant", STARTED_MESSAGE)
    tx.set(
        build_number=number,
        step="b_running",
        current_round=0,
        write_state="not_written",
        message="",
        return_status=came_from,
    )
