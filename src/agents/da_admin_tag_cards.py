"""The "From the AI scan" queue cards and their approvals (fix 11-2, AG-6 and AG-7). No AI here.

AS400 picture: a suspense file of proposed program-to-area assignments. Admin approves a line (or
all the sure ones at once) and the catalog gets exact-path patterns in ONE new version. The AI never
saves anything; only these functions, called by an Admin click, do.
"""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from agents.da_admin_catalog import ResolveResult, _add_pattern, pattern_offer
from agents.da_admin_forms import RESULT_SAVED
from agents.da_admin_modules import modules_by_capability
from agents.da_admin_tag_store import read_store, save_store
from agents.da_admin_tagger import (
    STATE_APPROVED,
    STATE_PROPOSED,
    STATE_REJECTED,
    STATE_UNREADABLE,
)
from agents.da_code_clusters import remember_reject
from agents.da_tag_versions import list_versions, save_version
from db_table_functions.db_tbl_da_rulebook import get_active_version

NOTHING = "Nothing to approve."


@dataclass(frozen=True)
class AiCard:
    path: str
    capability: str  # "" means "No capability fits"
    confidence: str
    summary: str
    reason: str
    tagged_at: str = ""  # for "Newest first"
    unreadable: bool = False  # Fix G5 R5: "AI could not read this program"; `reason` is the word


def ai_cards(directory: Path | None = None) -> list[AiCard]:
    """Open proposals, by path. Programs in a new-capability suggestion have their own card."""
    modules = read_store(directory)["modules"]
    return [
        AiCard(
            path,
            str(e.get("proposed_capability", "")),
            str(e.get("confidence", "")),
            str(e.get("summary", "")),
            str(e.get("reason", "")),
            str(e.get("tagged_at", "")),
            e.get("state") == STATE_UNREADABLE,
        )
        for path, e in sorted(modules.items())
        if isinstance(e, dict)
        and e.get("state") in (STATE_PROPOSED, STATE_UNREADABLE)
        and not e.get("new_name")
    ]


@dataclass(frozen=True)
class AlsoCard:
    """Fix G6 M4: "Also add <path> to <capability>?" Its own card; Approve all never takes it."""

    path: str
    capability: str
    summary: str


def also_cards(directory: Path | None = None) -> list[AlsoCard]:
    modules = read_store(directory)["modules"]
    return [
        AlsoCard(path, e["also"], str(e.get("summary", "")))
        for path, e in sorted(modules.items())
        if isinstance(e, dict) and e.get("also")
    ]


def _clear_also(path: str, directory: Path | None) -> None:
    store = read_store(directory)
    store["modules"].get(path, {}).pop("also", None)
    save_store(store, directory)


def approve_also(
    settings, path: str, capability: str, admin_id: str, base_version: int | None = None,
    directory: Path | None = None,
) -> ResolveResult:
    """Add: one exact pattern on the other capability; the main one keeps the module."""
    active = get_active_version(settings.db_path)
    held = [c for c in active.rulebook.policy.capabilities if c.name == capability]
    if not held:
        missing = f"Capability '{capability}' is not in the catalog."
        return ResolveResult("refused", problems=[missing])
    if modules_by_capability(held, [path])[capability]:  # already matched there, nothing to add
        _clear_also(path, directory)
        return ResolveResult("resolved")
    note = f"AI scan: also add {path} to {capability}"
    saved = _add_pattern(
        settings, active.rulebook.policy, [(path, capability)],
        base_version or active.version_number, admin_id, note,
    )
    if saved.kind != RESULT_SAVED:
        return ResolveResult(
            "refused", message=saved.message, problems=saved.problems or [saved.message],
            stale=saved.kind == "stale",
        )
    _clear_also(path, directory)
    return ResolveResult("resolved", new_version=saved.version_number)


def reject_also(path: str, directory: Path | None = None) -> None:
    _clear_also(path, directory)


def high_confidence(directory: Path | None = None) -> list[AiCard]:
    return [c for c in ai_cards(directory) if c.confidence == "high" and c.capability]


def high_confidence_counts(directory: Path | None = None) -> dict[str, int]:
    """Capability name to how many sure proposals it would get (for the confirm box)."""
    return dict(Counter(c.capability for c in high_confidence(directory)))


def _mark(
    paths: list[str], state: str, directory: Path | None, who: str, note: str,
    capabilities: dict[str, str] | None = None,
) -> None:
    """Close cards, then save the tag file as a new tag version (Upgrade G5f). `capabilities` is
    what Admin chose (Assign to may differ from the AI's proposal): the tag keeps his choice."""
    if not list_versions(directory):  # so even the first Approve all can be undone
        save_version("Starting tags (before the first Admin decision)", "system", directory)
    store = read_store(directory)
    for path in paths:
        if path in store["modules"]:
            store["modules"][path]["state"] = state
            if capabilities and path in capabilities:
                store["modules"][path]["proposed_capability"] = capabilities[path]
    save_store(store, directory)
    save_version(note, who, directory)


def approve_pairs(
    settings,
    pairs: list[tuple[str, str]],
    admin_id: str,
    note: str,
    base_version: int | None = None,
    directory: Path | None = None,
) -> ResolveResult:
    """Add the exact-path patterns of all pairs in one new rulebook version, then close the cards.

    The version is saved BEFORE the cards close, so a refused save leaves every card open."""
    active = get_active_version(settings.db_path)
    catalog = active.rulebook.policy.capabilities
    names = {c.name.lower() for c in catalog}
    unknown = sorted({cap for _p, cap in pairs if cap.lower() not in names})
    if not pairs or unknown:
        problem = f"Capability '{unknown[0]}' is not in the catalog." if unknown else NOTHING
        return ResolveResult("refused", problems=[problem])
    # a path some capability already matches needs no pattern (first match wins)
    needed = [(p, c) for p, c in pairs if not pattern_offer(p, catalog, c)]
    new_version = None
    if needed:
        saved = _add_pattern(
            settings, active.rulebook.policy, needed, base_version or active.version_number,
            admin_id, note,
        )
        if saved.kind != RESULT_SAVED:
            return ResolveResult(
                "refused", message=saved.message, problems=saved.problems or [saved.message],
                stale=saved.kind == "stale",
            )
        new_version = saved.version_number
    _mark([p for p, _c in pairs], STATE_APPROVED, directory, admin_id, note, dict(pairs))
    # name the capability that already holds a path, so Admin sees where it really is
    needed_paths = {n for n, _c in needed}
    held = [pattern_offer(p, catalog, c) for p, c in pairs if p not in needed_paths]
    if len(held) > 1:  # bulk approve: one summary line, not one sentence per program
        held = [f"{len(held)} programs were already matched by a capability; no pattern needed."]
    return ResolveResult("resolved", message=" ".join(held), new_version=new_version)


def approve_card(
    settings, path: str, capability: str, admin_id: str, base_version: int | None = None,
    directory: Path | None = None,
) -> ResolveResult:
    """Approve (the proposed capability) or Assign to (Admin's pick): one pair, one version."""
    return approve_pairs(
        settings, [(path, capability)], admin_id, f"AI scan: {path} to {capability}",
        base_version, directory,
    )


def approve_all_high(
    settings, admin_id: str, base_version: int | None = None, directory: Path | None = None
) -> ResolveResult:
    """All high-confidence proposals in ONE version; the note holds the count."""
    cards = high_confidence(directory)
    note = f"AI scan: {len(cards)} programs approved (high confidence)"
    return approve_pairs(
        settings, [(c.path, c.capability) for c in cards], admin_id, note, base_version, directory
    )


def reject_cards(paths: list[str], directory: Path | None = None, who: str = "") -> None:
    """The programs belong in no capability. No rulebook change, ONE new tag version. A suggestion
    from code links remembers its cluster, so it stays away until the cluster changes (G2b)."""
    modules = read_store(directory)["modules"]
    for path in paths:
        fingerprint = modules.get(path, {}).get("cluster")
        if fingerprint:
            remember_reject(path, fingerprint, directory)
    many = f"{len(paths)} programs"
    note = f"AI scan: {paths[0] if len(paths) == 1 else many} rejected"
    _mark(paths, STATE_REJECTED, directory, who, note)


def reject_card(path: str, directory: Path | None = None, who: str = "") -> None:
    reject_cards([path], directory, who)
