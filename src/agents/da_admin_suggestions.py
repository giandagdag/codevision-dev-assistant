"""New-capability suggestion cards (Fix G4, S4). The AI proposes; only an Admin click saves.

AS400 picture: a request to add a new area to the catalog, with its programs attached. Create and
assign saves ONE rulebook version (the new capability and an exact-path pattern per kept program).
"""

from dataclasses import dataclass
from pathlib import Path

from agents.da_admin_catalog import ResolveResult
from agents.da_admin_forms import RESULT_SAVED, TAB_CAPABILITY, capability_rows, save_from_form
from agents.da_admin_tag_cards import _mark, approve_pairs
from agents.da_admin_tag_store import read_store, save_store
from agents.da_admin_tagger import STATE_APPROVED, STATE_PROPOSED, STATE_REJECTED, name_key
from db_table_functions.db_tbl_da_rulebook import get_active_version

CONFIDENCE_ORDER = ("low", "medium", "high")


@dataclass(frozen=True)
class Suggestion:
    name: str
    description: str
    confidence: str  # the lowest of its modules
    modules: dict[str, str]  # path to its own AI summary


def suggestions(directory: Path | None = None) -> list[Suggestion]:
    """Open `new` proposals grouped by name (the tagger already merged the spellings)."""
    groups: dict[str, list[tuple[str, dict]]] = {}
    for path, entry in sorted(read_store(directory)["modules"].items()):
        if _is_open_new(entry):
            groups.setdefault(name_key(entry["new_name"]), []).append((path, entry))
    result = []
    for members in groups.values():
        first = members[0][1]
        lowest = min((str(e.get("confidence")) for _p, e in members), key=_rank)
        result.append(Suggestion(
            first["new_name"], str(first.get("new_description", "")), lowest,
            {p: str(e.get("summary", "")) for p, e in members},
        ))
    return result


def _is_open_new(entry) -> bool:
    return isinstance(entry, dict) and entry.get("state") == STATE_PROPOSED and bool(
        entry.get("new_name"))


def _rank(confidence: str) -> int:
    return CONFIDENCE_ORDER.index(confidence) if confidence in CONFIDENCE_ORDER else 0


def remove_from_suggestion(path: str, directory: Path | None = None) -> None:
    """Take one program out of its suggestion: it stays in the queue as "No capability fits"."""
    store = read_store(directory)
    entry = store["modules"].get(path)
    if entry:
        entry.pop("new_name", None)
        entry.pop("new_description", None)
        save_store(store, directory)


def create_and_assign(
    settings, name: str, description: str, named_senior: str, backup_senior: str,
    paths: list[str], admin_id: str, base_version: int | None = None,
    directory: Path | None = None, note: str = "",
) -> ResolveResult:
    """The new capability and its exact-path patterns in ONE version, then close the cards."""
    name, description = " ".join(name.split()), description.strip()
    active = get_active_version(settings.db_path)
    if not (name and description and paths):
        problem = "A name, a description and a program are needed."
        return ResolveResult("refused", problems=[problem])
    if not named_senior.strip():  # the rulebook requires one (spec said empty allowed: asked Gian)
        return ResolveResult("refused", problems=["A named senior is needed for a new capability."])
    rows = capability_rows(active.rulebook.policy)
    rows.append({"name": name, "description": description, "named_senior": named_senior.strip(),
                 "backup_senior": backup_senior.strip(), "path_patterns": "\n".join(paths)})
    note = note or f"AI suggestion: new capability {name} with {len(paths)} programs"
    saved = save_from_form(
        settings.db_path, TAB_CAPABILITY, {"capabilities": rows},
        base_version or active.version_number, admin_id, note,
    )
    if saved.kind != RESULT_SAVED:
        problems = saved.problems or [saved.message]
        return ResolveResult("refused", message=saved.message, problems=problems,
                             stale=saved.kind == "stale")
    _mark(paths, STATE_APPROVED, directory, admin_id, note, {p: name for p in paths})
    return ResolveResult("resolved", new_version=saved.version_number)


def assign_suggestion(
    settings, capability: str, paths: list[str], admin_id: str,
    base_version: int | None = None, directory: Path | None = None, note: str = "",
) -> ResolveResult:
    """Assign to: all kept programs go to an existing capability (one version)."""
    note = note or f"AI scan: {len(paths)} programs to {capability} (new capability suggestion)"
    return approve_pairs(settings, [(p, capability) for p in paths], admin_id, note,
                         base_version, directory)


def reject_suggestion(paths: list[str], admin_id: str, directory: Path | None = None) -> None:
    """Reject: every program becomes `rejected`. No rulebook change."""
    _mark(paths, STATE_REJECTED, directory, admin_id, f"AI scan: {len(paths)} programs rejected")
