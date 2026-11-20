"""Search, filter and sort of the Review queue cards (Fix G4 L9), and the bulk approve plan (L10).

Pure functions on made-up data: no AI, no file, no database. The screen calls these with the cards
it already has. AS400 picture: a subfile with filter keys over the same rows.
"""

from dataclasses import dataclass

SOURCE_AI, SOURCE_REQUEST = "ai", "request"
PROPOSAL_HAS, PROPOSAL_NONE, PROPOSAL_NEW = "has", "none", "new"
SORT_CONFIDENCE, SORT_PATH, SORT_NEWEST = "confidence", "path", "newest"
SOURCES = {SOURCE_AI: "AI scan", SOURCE_REQUEST: "From a request"}
PROPOSALS = {
    PROPOSAL_HAS: "Has a capability",
    PROPOSAL_NONE: "No capability fits",
    PROPOSAL_NEW: "New capability suggested",
}
CONFIDENCES = ("high", "medium", "low")
SORTS = {
    SORT_CONFIDENCE: "Confidence (high first)",
    SORT_PATH: "Path A to Z",
    SORT_NEWEST: "Newest first",
}
NO_MATCH = "No programs match. Clear the filters."


@dataclass(frozen=True)
class ReviewFilter:
    search: str = ""
    source: tuple[str, ...] = ()
    proposal: tuple[str, ...] = ()
    confidence: tuple[str, ...] = ()
    folder: tuple[str, ...] = ()
    sort: str = SORT_CONFIDENCE

    @property
    def active(self) -> bool:
        return bool(self.search or self.source or self.proposal or self.confidence or self.folder)


def filter_from_values(
    search=None, source=None, proposal=None, confidence=None, folder=None, sort=None
) -> ReviewFilter:
    """Build the filter from what the controls hold (None or empty means "not set")."""
    return ReviewFilter(
        (search or "").strip(),
        tuple(source or ()),
        tuple(proposal or ()),
        tuple(confidence or ()),
        tuple(folder or ()),
        sort if sort in SORTS else SORT_CONFIDENCE,
    )


def folder_of(path: str) -> str:
    """The top folder of a path ("agent_flows/a.py" gives "agent_flows"); "" for a bare file."""
    parts = path.replace("\\", "/").strip("/").split("/")
    return parts[0] if len(parts) > 1 else ""


def top_folders(paths: list[str]) -> list[str]:
    return sorted({folder for p in paths if (folder := folder_of(p))})


def _proposal_of(capability: str, is_new: bool) -> str:
    return PROPOSAL_NEW if is_new else (PROPOSAL_HAS if capability else PROPOSAL_NONE)


def _keeps(f: ReviewFilter, source, paths, capability, is_new, confidence, text) -> bool:
    if f.source and source not in f.source:
        return False
    if f.proposal and _proposal_of(capability, is_new) not in f.proposal:
        return False
    if f.confidence and confidence not in f.confidence:
        return False
    if f.folder and not any(folder_of(p) in f.folder for p in paths):
        return False
    return not f.search or f.search.lower() in text.lower()


def _rank(confidence: str) -> int:
    return CONFIDENCES.index(confidence) if confidence in CONFIDENCES else len(CONFIDENCES)


def filter_ai_cards(cards, f: ReviewFilter) -> list:
    """AI scan cards (AiCard): search matches the path and the summary."""
    kept = [
        c
        for c in cards
        if _keeps(
            f, SOURCE_AI, [c.path], c.capability, False, c.confidence, f"{c.path}\n{c.summary}"
        )
    ]
    if f.sort == SORT_PATH:
        return sorted(kept, key=lambda c: c.path.lower())
    if f.sort == SORT_NEWEST:  # tagged_at is an ISO text, so text order is time order
        return sorted(kept, key=lambda c: (c.tagged_at, c.path), reverse=True)
    return sorted(kept, key=lambda c: (_rank(c.confidence), c.path.lower()))


def filter_suggestions(suggested, f: ReviewFilter) -> list:
    """New-capability suggestions: search matches the name, description and program paths."""
    kept = [
        s
        for s in suggested
        if _keeps(
            f, SOURCE_AI, list(s.modules), "", True, s.confidence,
            f"{s.name}\n{s.description}\n" + "\n".join(s.modules),
        )
    ]
    if f.sort == SORT_PATH:
        return sorted(kept, key=lambda s: s.name.lower())
    return sorted(kept, key=lambda s: (_rank(s.confidence), s.name.lower()))


def filter_requests(rows, f: ReviewFilter) -> list:
    """Rows from a request (QueueRow) have no confidence or proposal: those filters hide them."""
    if f.confidence or f.proposal:
        return []
    kept = [
        r for r in rows if _keeps(f, SOURCE_REQUEST, [r.path], "", False, "", r.path)
    ]
    return sorted(kept, key=lambda r: r.path.lower())


def count_line(shown: int, total: int) -> str:
    return f"Showing {shown} of {total}"


@dataclass(frozen=True)
class BulkPlan:
    """What "Approve proposals" does with the selected cards."""

    pairs: list[tuple[str, str]]  # (path, capability) of cards that have a proposal
    skipped: int  # selected cards without a proposal
    counts: dict[str, int]  # per capability, for the confirm box


def bulk_plan(selected: list[str], cards) -> BulkPlan:
    by_path = {c.path: c for c in cards}
    chosen = [by_path[p] for p in selected if p in by_path]
    pairs = [(c.path, c.capability) for c in chosen if c.capability]
    counts: dict[str, int] = {}
    for _path, capability in pairs:
        counts[capability] = counts.get(capability, 0) + 1
    return BulkPlan(pairs, len(chosen) - len(pairs), counts)
