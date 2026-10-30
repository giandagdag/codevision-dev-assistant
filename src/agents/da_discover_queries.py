"""Builds the searches for one Discover round and merges their hits (spec 3.3). No AI here.

The app decides what to search for (rule R1). Like building the query list for a where-used run
from the fields of the request record.
"""

from dataclasses import dataclass

from agents.da_search_index import SearchIndex, search_safely
from pydantic_classes.da_discovery_models import SearchFilters, SearchHit, SearchMode
from pydantic_classes.da_request_record_models import RequestRecord

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


def build_queries(record: RequestRecord, hint: str = "") -> list[Query]:
    """Exact queries from the title and each reference, meaning queries from the objective and
    expected behaviour, and an exact and a meaning query from the hint. The hint goes first so
    the cap of 6 can never drop it."""
    wanted: list[Query] = []
    hint = hint.strip()
    if hint:
        wanted += [Query(hint, "exact"), Query(hint, "meaning")]
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
    index: SearchIndex, record: RequestRecord, hint: str, top_k: int
) -> SearchRound:
    """Run every query, drop unsafe hits, merge, keep the best 12 and number them 1 to 12."""
    queries = build_queries(record, hint)
    filters = SearchFilters()
    found: list[SearchHit] = []
    dropped = 0
    for query in queries:
        hits, count = search_safely(index, query.text, query.mode, filters, top_k)
        found += hits
        dropped += count
    return SearchRound(queries=queries, hits=merge_hits(found), dropped=dropped)


def merge_hits(hits: list[SearchHit]) -> list[SearchHit]:
    """One hit per (source_path, symbol), keeping the best score, so two functions in one file
    stay two hits (decision D-F). Best 12, numbered from 1."""
    best: dict[tuple[str, str], SearchHit] = {}
    for hit in hits:
        key = (hit.source_path, hit.symbol)
        if key not in best or hit.score > best[key].score:
            best[key] = hit
    ranked = sorted(best.values(), key=lambda h: (-h.score, h.source_path, h.symbol))
    kept = ranked[:MAX_HITS]
    return [hit.model_copy(update={"hit_id": number}) for number, hit in enumerate(kept, start=1)]
