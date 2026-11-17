"""The Capability catalog and its Unassigned queue, as plain functions (Phase 11b, spec 6 and 19).

Which capability a path belongs to is decided here with the same function the developer flow uses
(lookup_capability: first match wins), so Admin sees exactly what a request would get. No AI.

A resolved row is closed as `confirmed` (the developer's pick stands), `changed` (Admin moved the
file) or `rejected` (the file belongs in no capability; a later change reopens it).
The request's own record is never touched (spec 11-31): only da_unassigned_files changes.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from agents.da_admin_forms import (
    RESULT_SAVED,
    TAB_CAPABILITY,
    capability_rows,
    save_from_form,
)
from agents.da_admin_suggest import suggest_capability
from agents.da_enhance_checks import lookup_capability
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_enhance import (
    EnhanceError,
    list_resolved,
    list_unassigned,
    resolve_unassigned,
)
from db_table_functions.db_tbl_da_rulebook import get_active_version
from pydantic_classes.da_enhance_models import UnassignedFile
from pydantic_classes.da_rulebook_models import Capability

RESOLVED_SHOWN = 50


@dataclass(frozen=True)
class QueueRow:
    """One open Unassigned file as the screen shows it."""

    unassigned_id: int
    path: str
    picked_capability: str
    request_id: str
    waiting_since: datetime | None
    would_match: str  # capability a request would get today, or "" for none
    suggested: str = ""  # capability it imports from most (AF-12), or "" for none
    reason: str = ""


@dataclass(frozen=True)
class ResolveResult:
    """resolved = the row is closed. refused = nothing was closed; problems say why."""

    kind: str
    message: str = ""
    problems: list[str] = field(default_factory=list)
    new_version: int | None = None
    stale: bool = False


def would_match(path: str, capabilities: list[Capability]) -> str:
    """Name of the first capability that matches the path, or "" when none does."""
    found = lookup_capability(path, capabilities)
    return found.name if found else ""


def queue_rows(settings) -> list[QueueRow]:
    """Open Unassigned rows, oldest first, each with what it would match in the active catalog."""
    active = get_active_version(settings.db_path)
    catalog = active.rulebook.policy.capabilities if active else []
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        rows = list_unassigned(conn)
    scope = active.rulebook.policy.index_folder_scope if active else ""
    result = []
    for row in rows:
        suggested, reason = suggest_capability(row.path, catalog, scope)
        result.append(
            QueueRow(
                unassigned_id=row.unassigned_id,
                path=row.path,
                picked_capability=row.picked_capability,
                request_id=row.request_id,
                waiting_since=row.created_at,
                would_match=would_match(row.path, catalog),
                suggested=suggested,
                reason=reason,
            )
        )
    return result


def resolved_rows(settings, limit: int = RESOLVED_SHOWN) -> list[UnassignedFile]:
    """The last resolved rows (who, when, and where a moved file went), newest first."""
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        return list_resolved(conn, limit)


def pattern_offer(path: str, capabilities: list[Capability], target: str) -> str:
    """"" when adding the path to `target` would help, else a plain sentence saying why not.

    Lookup is first match wins: if some capability already matches the path (an earlier one, or
    the target itself), a new pattern on the target changes nothing."""
    names = {c.name.lower() for c in capabilities}
    if target.lower() not in names:
        return f"Capability '{target}' is not in the catalog."
    matching = would_match(path, capabilities)
    if matching:
        return f"The capability '{matching}' already matches this path, so no pattern is needed."
    return ""


def resolve_row(
    settings,
    unassigned_id: int,
    state: str,
    capability: str,
    admin_id: str,
    add_pattern: bool = False,
    note: str = "",
    base_version: int | None = None,
) -> ResolveResult:
    """Close one open row. `capability` is the pick that stands (confirmed) or where the file
    moves (changed).

    With add_pattern the file's path is first added to that capability as a new catalog version
    (needs a change note). The pattern is saved BEFORE the row is closed, so a refused save leaves
    the row open and nothing half done. base_version is the version the screen was drawn from, so
    a stale view is caught by the normal save."""
    row = _open_row_by_id(settings, unassigned_id)
    if row is None:
        return ResolveResult("refused", problems=["That Unassigned row is not open any more."])
    active = get_active_version(settings.db_path)
    catalog = active.rulebook.policy.capabilities
    if state == "rejected":
        add_pattern = False  # a rejected file joins no capability
    if state == "changed" and capability.lower() not in {c.name.lower() for c in catalog}:
        problem = f"Capability '{capability}' is not in the catalog."
        return ResolveResult("refused", problems=[problem])

    new_version = None
    if add_pattern and not pattern_offer(row.path, catalog, capability):
        version = base_version or active.version_number
        saved = _add_pattern(
            settings, active.rulebook.policy, [(row.path, capability)], version, admin_id, note
        )
        if saved.kind != RESULT_SAVED:
            return ResolveResult(
                "refused",
                message=saved.message,
                problems=saved.problems or [saved.message],
                stale=saved.kind == "stale",
            )
        new_version = saved.version_number

    try:
        with open_db(settings.db_path) as conn:
            resolve_unassigned(
                conn,
                unassigned_id,
                state,
                admin_id,
                datetime.now(UTC),
                resolved_capability=capability if state == "changed" else "",
            )
    except EnhanceError as error:
        return ResolveResult("refused", problems=[str(error)], new_version=new_version)
    return ResolveResult("resolved", new_version=new_version)


def _open_row_by_id(settings, unassigned_id: int) -> UnassignedFile | None:
    with open_db(settings.db_path) as conn:
        ensure_build_tables(conn)
        return next((r for r in list_unassigned(conn) if r.unassigned_id == unassigned_id), None)


def _add_pattern(settings, policy, pairs, base_version, admin_id, note):
    """Add each (path, capability) pair as an exact-path pattern and save ONE new version."""
    rows = capability_rows(policy)
    for path, capability in pairs:
        for row in rows:
            if row["name"].lower() == capability.lower():
                row["path_patterns"] = row["path_patterns"] + "\n" + path
    return save_from_form(
        settings.db_path, TAB_CAPABILITY, {"capabilities": rows}, base_version, admin_id, note
    )
