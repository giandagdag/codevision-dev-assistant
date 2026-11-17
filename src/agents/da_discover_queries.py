"""Builds the searches for one Discover round and merges their hits (spec 3.3). No AI here.

The app decides what to search for (rule R1). Like building the query list for a where-used run
from the fields of the request record.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from agents.da_admin_modules import modules_by_capability
from agents.da_search_index import SearchIndex, search_safely
from pydantic_classes.da_discovery_models import SearchFilters, SearchHit, SearchMode
from pydantic_classes.da_request_record_models import RequestRecord
from pydantic_classes.da_rulebook_models import Capability

MAX_QUERIES = 6
MAX_HITS = 12
QUERY_TEXT_LIMIT = 300


@dataclass(frozen=True)
class Query:
    text: str
    mode: SearchMode

    def label(self) -> str:
        return f"{self.mode}: {self.text}"


@dataclass(frozen=True)
class SearchRound:
    queries: list[Query]
    hits: list[SearchHit]
    dropped: int
    capability: str = ""  # the capability the searches were narrowed to, or ""


def build_queries(record: RequestRecord, hint: str = "") -> list[Query]:
    """Exact queries from the title and each reference, meaning queries from the objective and
    expected behaviour, and an exact and a meaning query from the hint. The hint goes first so
    the cap of 6 can never drop it."""
    wanted: list[Query] = []
    hint = hint.strip()
    if hint:
        wanted += [Query(hint, "exact"), Query(hint, "meaning")]
    # Phase 9: an enhance or fix request also searches for its own programs and the functions in
    # scope. They come before the title, so the cap of 6 keeps them (spec section 7, step 1).
    if record.kind != "new":
        wanted += [Query(path, "exact") for path in record.targets]
        if record.functions_in_scope:
            wanted.append(Query(" ".join(record.functions_in_scope), "exact"))
    wanted.append(Query(record.title, "exact"))
    wanted.append(Query(record.objective, "meaning"))
    wanted.append(Query(record.expected_behaviour, "meaning"))
    wanted += [Query(reference, "exact") for reference in record.references]

    queries: list[Query] = []
    for query in wanted:
        text = " ".join(query.text.split())[:QUERY_TEXT_LIMIT]
        cleaned = Query(text, query.mode)
        if text and cleaned not in queries:
            queries.append(cleaned)
    return queries[:MAX_QUERIES]


def run_searches(
    index: SearchIndex,
    record: RequestRecord,
    hint: str,
    top_k: int,
    capabilities: list[Capability] | None = None,
    paths: list[str] | None = None,
) -> SearchRound:
    """Run every query, drop unsafe hits, merge, keep the best 12 and number them 1 to 12.

    With a catalog and the indexed paths, plain code may find the capability the request is about
    (fix 11-1). Then each query runs twice: on that capability's modules first, then on the whole
    index. Hits inside the capability are labelled and listed first."""
    queries = build_queries(record, hint)
    capability, modules = match_capability(record, hint, capabilities or [], paths or [])
    filters = [SearchFilters()]
    if capability and modules:
        filters.insert(0, SearchFilters(modules=modules))
    found: list[SearchHit] = []
    dropped = 0
    for query in queries:
        for one in filters:
            hits, count = search_safely(index, query.text, query.mode, one, top_k)
            found += hits
            dropped += count
    if capability:
        found = [
            hit.model_copy(update={"capability": capability}) if hit.source_path in modules else hit
            for hit in found
        ]
    return SearchRound(
        queries=queries, hits=merge_hits(found), dropped=dropped, capability=capability
    )


def _stem(word: str) -> str:
    # "limits" and "limit" are the same word for matching.
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _words(text: str) -> set[str]:
    return {_stem(word) for word in re.findall(r"[a-z0-9]+", text.lower())}


def match_capability(
    record: RequestRecord, hint: str, capabilities: list[Capability], paths: list[str]
) -> tuple[str, list[str]]:
    """The capability the request is about (name, its module paths), or ("", []). No AI.

    Points: a word of the capability name 3, a word of its description 1, a module file name that
    appears in the request 2. The most points wins; a tie goes to the first in the catalog."""
    text = " ".join([record.title, record.objective, record.expected_behaviour, hint])
    text = " ".join([text, *record.references, *record.targets])
    request_words = _words(text)
    spaced = " ".join(re.findall(r"[a-z0-9]+", text.lower()))
    best_name, best_modules, best_points = "", [], 0
    by_capability = modules_by_capability(capabilities, paths)
    for c in capabilities:
        points = 3 * len(_words(c.name) & request_words)
        points += len({w for w in _words(c.description) if len(w) >= 5} & request_words)
        for path in by_capability[c.name]:
            stem = " ".join(re.findall(r"[a-z0-9]+", Path(path).stem.lower()))
            points += 2 if stem and stem in spaced else 0
        if points > best_points:
            best_name, best_modules, best_points = c.name, by_capability[c.name], points
    return best_name, best_modules


def merge_hits(hits: list[SearchHit]) -> list[SearchHit]:
    """One hit per (source_path, symbol), keeping the best score, so two functions in one file
    stay two hits (decision D-F). Best 12, numbered from 1."""
    best: dict[tuple[str, str], SearchHit] = {}
    for hit in hits:
        key = (hit.source_path, hit.symbol)
        if key not in best or hit.score > best[key].score:
            best[key] = hit
    # Hits inside the matched capability come first (fix 11-1); with none labelled this is a no-op.
    ranked = sorted(
        best.values(), key=lambda h: (not h.capability, -h.score, h.source_path, h.symbol)
    )
    kept = ranked[:MAX_HITS]
    return [hit.model_copy(update={"hit_id": number}) for number, hit in enumerate(kept, start=1)]
