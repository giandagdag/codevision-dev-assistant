"""Catalog search "What the code does" (fix 11-2, section 2). Plain code plus the embedder, no LLM.

AS400 picture: a "where used" lookup, but by what a program does instead of by its name. It runs the
same safe search Discover uses, then groups the pieces by program.
"""

from dataclasses import dataclass

from agents.da_admin_modules import modules_by_capability
from agents.da_search_index import (
    IndexFormatError,
    SearchIndex,
    SearchNotConfiguredError,
    _meaning_id,
    _query_words,
    _words,
    get_search_index,
    no_index_at_work,
    search_safely,
)
from configs.da_config import Settings
from pydantic_classes.da_discovery_models import SearchFilters
from pydantic_classes.da_rulebook_models import Capability

UNASSIGNED = "Unassigned"
NEEDS_BUILDING = "The code index needs building. Open Repository and index."
MAX_MODULES = 15
MAX_SYMBOLS = 3
FROM_CODE = "from code"
FROM_SUMMARY = "from summary"


@dataclass(frozen=True)
class ModuleHit:
    path: str
    symbols: tuple[str, ...]
    capability: str
    summary: str
    source: str  # FROM_CODE or FROM_SUMMARY
    score: float
    also: tuple[str, ...] = ()  # fix G6 M2: the other capabilities that claim it, after the main


def capabilities_of(path: str, capabilities: list[Capability]) -> tuple[str, list[str]]:
    """Fix G6 M1: (main, also). The main capability is the first match in catalog order (it owns the
    senior, escalations and Discover's narrowing); every other match is an "also in". A path no
    capability matches is (Unassigned, [])."""
    found = [n for n, paths in modules_by_capability(capabilities, [path]).items() if paths]
    return (found[0], found[1:]) if found else (UNASSIGNED, [])


def capability_of(path: str, capabilities: list[Capability]) -> str:
    """The main capability: the first whose patterns match the path, else Unassigned."""
    return capabilities_of(path, capabilities)[0]


def summary_score(summary: str, query: str) -> float:
    """Share of the query's words (by stem and synonym) found in a summary; 0 if under half."""
    wanted = {_meaning_id(word) for word in _query_words(query)}
    if not wanted:
        return 0.0
    present = {_meaning_id(word) for word in _words(summary)}
    share = len(wanted & present) / len(wanted)
    return share if share >= 0.5 else 0.0


def modules_by_meaning(
    query: str,
    index: SearchIndex,
    capabilities: list[Capability],
    tags: dict[str, dict] | None = None,
    top_k: int = 30,
) -> list[ModuleHit]:
    """Group the search hits by module, best score per module, then add summary matches."""
    tags = tags or {}
    best: dict[str, float] = {}
    symbols: dict[str, list[str]] = {}
    hits, _dropped = search_safely(index, query, "meaning", SearchFilters(), top_k)
    for hit in hits:
        best[hit.source_path] = max(best.get(hit.source_path, 0.0), hit.score)
        found = symbols.setdefault(hit.source_path, [])
        if hit.symbol and hit.symbol not in found:
            found.append(hit.symbol)
    from_summary: set[str] = set()
    for path, entry in tags.items():
        score = summary_score(str(entry.get("summary", "")), query)
        if score and path not in best:
            best[path] = score
            from_summary.add(path)
    ranked = sorted(best, key=lambda p: (-best[p], p))[:MAX_MODULES]
    hits = []
    for path in ranked:
        main, also = capabilities_of(path, capabilities)
        hits.append(
            ModuleHit(
                path,
                tuple(symbols.get(path, ())[:MAX_SYMBOLS]),
                main,
                str(tags.get(path, {}).get("summary", "")),
                FROM_SUMMARY if path in from_summary else FROM_CODE,
                best[path],
                tuple(also),
            )
        )
    return hits


def meaning_search(
    query: str, settings: Settings, capabilities: list[Capability], tags: dict[str, dict]
) -> tuple[list[ModuleHit], str]:
    """(modules, message). No index is one plain line, never an error (AG-2)."""
    if not query.strip():
        return [], ""
    if no_index_at_work(settings):
        return [], NEEDS_BUILDING
    try:
        index = get_search_index(settings)
        return modules_by_meaning(query, index, capabilities, tags), ""
    except (IndexFormatError, SearchNotConfiguredError, ImportError, OSError):
        return [], NEEDS_BUILDING
