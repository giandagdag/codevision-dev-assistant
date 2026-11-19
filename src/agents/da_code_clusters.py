"""Clusters of linked modules and capability suggestions (Upgrade G, G2). Plain code, no AI.

AS400 picture: programs that call each other a lot belong to the same application area. If most
tagged programs in such a group sit in one capability, an untagged neighbour probably does too.
The suggestion is only a card in the Admin queue: nothing is tagged until Admin approves.
Standard library only; label propagation is fixed (sorted order, 20 rounds) so a rerun on the same
graph gives the same answer.
"""

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from agents.da_admin_index import index_dir
from agents.da_admin_tag_store import read_store, save_store
from agents.da_code_impact_graph import with_catalog_tags

ROUNDS = 20
MIN_TAGGED = 3
SOURCE = "links"  # marks a tag-store entry that is a suggestion from code links
REJECTS_NAME = "da_cluster_rejects.json"
_TAGGED_STATES = ("approved", "matched")


@dataclass(frozen=True)
class Suggestion:
    path: str
    capability: str
    count: int  # linked tagged modules in this capability
    total: int  # linked tagged modules
    fingerprint: str  # the cluster as it is now; a rejected card stays hidden while it is the same

    @property
    def reason(self) -> str:
        return (
            f"Suggested from code links: {self.count} of {self.total} "
            f"linked modules are {self.capability}"
        )


def module_weights(graph: dict) -> dict[str, dict[str, int]]:
    """module -> {other module -> links either way}. Links inside one module are left out."""
    modules = {entry["module"] for entry in graph["files"].values()}
    weights: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for entry in graph["files"].values():
        for _kind, _source, target in entry.get("edges", []):
            other = _owner(target, modules)
            if other and other != entry["module"]:
                weights[entry["module"]][other] += 1
                weights[other][entry["module"]] += 1
    return weights


def _owner(target: str, modules: set[str]) -> str:
    parts = target.split(".")
    for end in range(len(parts), 0, -1):
        if ".".join(parts[:end]) in modules:
            return ".".join(parts[:end])
    return ""


def clusters(graph: dict) -> list[list[str]]:
    """Groups of 2 or more modules, each sorted; the list itself is sorted."""
    weights = module_weights(graph)
    names = sorted(weights)
    label = {name: name for name in names}
    for _ in range(ROUNDS):
        changed = False
        for name in names:
            score: Counter[str] = Counter()
            for other, weight in weights[name].items():
                score[label[other]] += weight
            best = min(score, key=lambda lab: (-score[lab], lab))  # most weight, then smallest name
            if best != label[name]:
                label[name], changed = best, True
        if not changed:
            break
    groups: dict[str, list[str]] = defaultdict(list)
    for name in names:
        groups[label[name]].append(name)
    return sorted(g for g in groups.values() if len(g) > 1)


def suggestions(graph: dict, store: dict, rejects: dict[str, str]) -> list[Suggestion]:
    """A card for each untagged module whose cluster has 3+ tagged modules and a clear majority."""
    path_of = {entry["module"]: path for path, entry in graph["files"].items()}
    tags = store["modules"]
    found: list[Suggestion] = []
    for group in clusters(graph):
        fingerprint = hashlib.sha256("\n".join(group).encode()).hexdigest()[:16]
        capabilities = [_capability(tags.get(path_of[m])) for m in group]
        tagged = Counter(c for c in capabilities if c)
        total = sum(tagged.values())
        if total < MIN_TAGGED:
            continue
        top, count = min(tagged.items(), key=lambda item: (-item[1], item[0]))
        if count * 2 <= total:
            continue
        for module in group:
            path = path_of[module]
            if _is_untagged(tags.get(path)) and rejects.get(path) != fingerprint:
                found.append(Suggestion(path, top, count, total, fingerprint))
    return sorted(found, key=lambda s: s.path)


def _capability(entry: dict | None) -> str:
    if isinstance(entry, dict) and entry.get("state") in _TAGGED_STATES:
        return str(entry.get("proposed_capability", ""))
    return ""


def _is_untagged(entry: dict | None) -> bool:
    """No entry at all, or an entry that is only an earlier suggestion of ours (not approved)."""
    if entry is None:
        return True
    if _ours(entry):
        return entry.get("state") != "approved"
    # An AI tag nobody has decided yet is still a guess: the links may suggest better.
    return entry.get("state") == "proposed"


# --- saving: suggestions are cards in the same tag file Admin already reviews ---------------------


def read_rejects(directory: Path | None = None) -> dict[str, str]:
    try:
        raw = json.loads(((directory or index_dir()) / REJECTS_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def remember_reject(path: str, fingerprint: str, directory: Path | None = None) -> None:
    folder = directory or index_dir()
    folder.mkdir(parents=True, exist_ok=True)
    rejects = {**read_rejects(folder), path: fingerprint}
    side = folder / (REJECTS_NAME + ".new")
    side.write_text(json.dumps(rejects, indent=1), encoding="utf-8")
    side.replace(folder / REJECTS_NAME)


def write_suggestions(graph: dict, directory: Path | None = None, capabilities=()) -> int:
    """Refresh the suggestion cards in the tag file. Returns how many cards are open.

    Old cards of ours are dropped first (an approved one is kept: Admin decided), so a card whose
    cluster changed disappears or moves. Admin-decided and AI entries are never touched."""
    store = read_store(directory)
    tags = store["modules"]
    old = [p for p, e in tags.items() if _ours(e) and e.get("state") != "approved"]
    for path in old:
        before = tags[path].get("ai")  # the AI tag this card replaced, put back untouched
        if isinstance(before, dict):
            tags[path] = before
        else:
            del tags[path]
    # A module the catalog's path patterns already place is not "untagged" and counts for its group.
    seen = {**store, "modules": with_catalog_tags(graph, tags, capabilities)}
    cards = suggestions(graph, seen, read_rejects(directory))
    if not cards and not old:
        return 0  # nothing to write: do not create a tag file for nothing
    for card in cards:
        ai = tags.get(card.path)  # an undecided AI tag: keep its summary and hash, show our reason
        tags[card.path] = {
            **(ai or {"summary": ""}), "proposed_capability": card.capability,
            "confidence": "medium", "reason": card.reason, "state": "proposed", "source": SOURCE,
            "cluster": card.fingerprint, **({"ai": ai} if ai else {}),
        }
    save_store(store, directory)
    return len(cards)


def _ours(entry) -> bool:
    return isinstance(entry, dict) and entry.get("source") == SOURCE
