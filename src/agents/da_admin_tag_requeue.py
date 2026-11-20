"""When a capability is removed, its approved AI tags go back to the queue (Fix G4, C4).

Nothing is lost: each such program becomes an AI card again (state `proposed`), and the change is
saved as a new tag version, so the Tags history can still restore the earlier tags."""

from pathlib import Path

from agents.da_admin_tag_store import read_store, save_store
from agents.da_admin_tagger import STATE_APPROVED, STATE_PROPOSED
from agents.da_tag_versions import list_versions, save_version


def requeue_for_removed(names: set[str], who: str, directory: Path | None = None) -> int:
    """Re-open the approved tags that point at one of the removed capabilities. Returns how many."""
    gone = {n.lower() for n in names}
    if not gone:
        return 0
    store = read_store(directory)
    hit = [
        entry
        for entry in store["modules"].values()
        if isinstance(entry, dict)
        and entry.get("state") == STATE_APPROVED
        and str(entry.get("proposed_capability", "")).lower() in gone
    ]
    if not hit:
        return 0
    if not list_versions(directory):  # so the very first change can be undone too
        save_version("Starting tags (before the first Admin decision)", "system", directory)
    for entry in hit:
        entry["state"] = STATE_PROPOSED
    save_store(store, directory)
    save_version(f"{len(hit)} programs back in the queue (capability removed)", who, directory)
    return len(hit)
