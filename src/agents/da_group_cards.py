"""Fix G6 S4/S5: the "Suggested from code links" cards and their decisions. The AI proposes; only an
Admin click saves.

AS400 picture: a small suspense file of proposed new areas, kept beside the index (not in the
per-program tag file, so a program's own tag card is never touched). Create and assign saves ONE
rulebook version with exact-path patterns. Never logs a path list, a prompt or a reply.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from agents.da_admin_index import index_dir
from agents.da_admin_suggestions import assign_suggestion, create_and_assign
from agents.da_admin_tagger import name_key
from agents.da_capability_suggest import NamedGroup

CARDS_NAME = "da_group_cards.json"
TITLE = "Suggested from code links"


@dataclass(frozen=True)
class GroupCard:
    name: str
    description: str
    programs: tuple[str, ...]
    confidence: str
    inside: int
    outside: int
    existing: str = ""  # a capability already in the catalog: "Assign to" instead of "Create"
    fingerprint: str = ""

    @property
    def counts(self) -> str:
        return f"{len(self.programs)} programs, {self.inside} links inside"


def fingerprint(name: str, programs) -> str:
    text = name_key(name) + "\n" + "\n".join(sorted(programs))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _file(directory: Path | None) -> Path:
    return (directory or index_dir()) / CARDS_NAME


def _read(directory: Path | None) -> dict:
    try:
        raw = json.loads(_file(directory).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = None
    raw = raw if isinstance(raw, dict) else {}
    return {"cards": list(raw.get("cards") or []), "rejected": list(raw.get("rejected") or [])}


def _write(data: dict, directory: Path | None) -> None:
    path = _file(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    side = path.with_name(CARDS_NAME + ".new")
    side.write_text(json.dumps(data, indent=1), encoding="utf-8")
    side.replace(path)


def read_cards(directory: Path | None = None) -> list[GroupCard]:
    found = []
    for raw in _read(directory)["cards"]:
        try:
            found.append(GroupCard(**{**raw, "programs": tuple(raw["programs"])}))
        except (TypeError, KeyError):
            continue  # a damaged card is dropped, never a crash
    return found


def save_suggestions(named: list[NamedGroup], directory: Path | None = None) -> int:
    """Replace the open cards with a new run's result. A card Admin rejected before stays away
    while its name and programs are the same. Returns how many cards are open."""
    data = _read(directory)
    cards = []
    for group in named:
        print_ = fingerprint(group.name, group.programs)
        if print_ in data["rejected"] or not group.programs:
            continue
        cards.append(asdict(GroupCard(
            group.name, group.description, group.programs, group.confidence, group.inside,
            group.outside, group.existing, print_,
        )))
    _write({"cards": cards, "rejected": data["rejected"]}, directory)
    return len(cards)


def _find(name: str, directory: Path | None) -> GroupCard | None:
    return next((c for c in read_cards(directory) if c.name == name), None)


def _close(card: GroupCard, directory: Path | None, rejected: bool = False) -> None:
    data = _read(directory)
    data["cards"] = [c for c in data["cards"] if c.get("fingerprint") != card.fingerprint]
    if rejected:
        data["rejected"].append(card.fingerprint)
    _write(data, directory)


def remove_program(name: str, path: str, directory: Path | None = None) -> None:
    """Remove from this suggestion: the program stays unassigned (nothing else changes)."""
    card = _find(name, directory)
    if card is None or path not in card.programs:
        return
    kept = tuple(p for p in card.programs if p != path)
    data = _read(directory)
    data["cards"] = [
        asdict(GroupCard(**{**asdict(card), "programs": kept,
                            "fingerprint": fingerprint(card.name, kept)}))
        if c.get("fingerprint") == card.fingerprint else c
        for c in data["cards"]
    ]
    _write(data, directory)


def reject_card(name: str, directory: Path | None = None) -> None:
    if card := _find(name, directory):
        _close(card, directory, rejected=True)


def create_card(
    settings, name: str, description: str, named_senior: str, backup_senior: str, admin_id: str,
    card_name: str, base_version: int | None = None, directory: Path | None = None,
):
    """Create and assign: the (possibly edited) capability with the card's kept programs, one
    rulebook version. The card closes only when the save worked."""
    card = _find(card_name, directory)
    if card is None:
        from agents.da_admin_catalog import ResolveResult  # a card closed by another click

        return ResolveResult("refused", problems=["That suggestion is not open any more."])
    note = f"{TITLE}: new capability {' '.join(name.split())} with {len(card.programs)} programs"
    result = create_and_assign(
        settings, name, description, named_senior, backup_senior, list(card.programs), admin_id,
        base_version, directory, note,
    )
    if result.kind == "resolved":
        _close(card, directory)
    return result


def assign_card(
    settings, card_name: str, admin_id: str, base_version: int | None = None,
    directory: Path | None = None,
):
    """A card named like a catalog capability: add its programs to that capability (one version)."""
    card = _find(card_name, directory)
    if card is None or not card.existing:
        from agents.da_admin_catalog import ResolveResult

        return ResolveResult("refused", problems=["That suggestion is not open any more."])
    result = assign_suggestion(
        settings, card.existing, list(card.programs), admin_id, base_version, directory,
        f"{TITLE}: {len(card.programs)} programs to {card.existing}",
    )
    if result.kind == "resolved":
        _close(card, directory)
    return result
