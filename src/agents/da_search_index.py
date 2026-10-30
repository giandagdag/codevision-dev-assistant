"""Discover's search interface, the pretend index, and our own safety filter (spec 3.1, 3.2).

Like a cross-reference query: ask "where is this used or done?" and get back a numbered list of
source places. At home the answers come from a small made-up file in the same shape the real
index will have. At work the same interface will sit on CodeVision's embeddings and FAISS (P15).
Standard library only (rule R8).
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from configs.da_config import Settings
from da_logging import get_logger
from pydantic_classes.da_discovery_models import (
    SNIPPET_LIMIT,
    HitKind,
    SearchFilters,
    SearchHit,
    SearchMode,
)

logger = get_logger(__name__)

DATA_FOLDER = Path(__file__).resolve().parents[1] / "data"
FAKE_INDEX_FILE = DATA_FOLDER / "da_fake_index.json"

NOT_CONFIGURED_MESSAGE = "CodeVision search is not configured yet."

# Standards, documents and settings are not tied to one programming language (planning decision 6).
_LANGUAGE_NEUTRAL_KINDS = ("doc", "standard", "config")

_WORD = re.compile(r"[a-z0-9]+")
_CAMEL_JOIN = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
# Small words that would match almost everything.
_STOP_WORDS = frozenset(
    "a an and are as at be by for from in into is it of on or so that the their then these "
    "this to up use used using what when which who will with".split()
)
# Words that mean nearly the same thing. Good enough to prove the pipeline, not real semantic
# search (spec 3.2). The first word of each group stands for the whole group.
_SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("extract", "parse", "read", "pull"),
    ("validate", "check", "verify"),
    ("ingest", "load", "import", "intake"),
    ("process", "processor", "handle"),
    ("excel", "spreadsheet", "workbook", "xlsx"),
    ("upload", "submit"),
    ("batch", "group"),
    ("error", "failure", "reject"),
    ("chunk", "split"),
)


class SearchNotConfiguredError(Exception):
    """The chosen search provider is only a placeholder so far."""


class IndexFormatError(Exception):
    """The index file cannot be used. The message says why in plain words."""


class SearchIndex(Protocol):
    def search(
        self, query: str, mode: SearchMode, filters: SearchFilters, top_k: int
    ) -> list[SearchHit]: ...


class IndexPiece(BaseModel):
    """One piece of the index: a function, a class, or a whole non-code file."""

    model_config = ConfigDict(extra="forbid")

    piece_no: int = Field(ge=0)
    path: str = Field(min_length=1)
    symbol: str = ""
    line_start: int = Field(default=0, ge=0)
    kind: HitKind
    language: str = ""
    deprecated: bool = False
    restricted: bool = False
    tags: list[str] = Field(default_factory=list)
    # Same limit as SearchHit.snippet: a longer one is refused when the file is loaded, never cut.
    snippet: str = Field(default="", max_length=SNIPPET_LIMIT)


@dataclass(frozen=True)
class IndexData:
    build_id: str
    built_at: str
    pieces: tuple[IndexPiece, ...]


def load_index_file(path: Path = FAKE_INDEX_FILE) -> IndexData:
    """Read an index file. Refused if a piece number does not match its position in the list.

    CodeVision's design links a vector to its file by row number. Rows out of order would point
    to the wrong file without any error, so we check the numbers instead of trusting them.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        pieces = tuple(IndexPiece.model_validate(item) for item in raw["pieces"])
        build_id, built_at = str(raw["build_id"]), str(raw.get("built_at", ""))
    except (OSError, ValueError, KeyError, TypeError, ValidationError) as error:
        raise IndexFormatError(
            f"The search index file could not be read ({type(error).__name__}). "
            f"Check that it has build_id and a list of pieces, and that no snippet is longer "
            f"than {SNIPPET_LIMIT} characters."
        ) from error
    for position, piece in enumerate(pieces):
        if piece.piece_no != position:
            raise IndexFormatError(
                f"The search index is out of order: the piece at position {position} says it "
                f"is number {piece.piece_no}. Piece numbers must run 0, 1, 2 with no gaps."
            )
    return IndexData(build_id=build_id, built_at=built_at, pieces=pieces)


class FakeSearchIndex:
    """The pretend index: word matching with a small synonym list, no embeddings."""

    def __init__(self, data: IndexData) -> None:
        self._data = data

    @classmethod
    def from_file(cls, path: Path = FAKE_INDEX_FILE) -> FakeSearchIndex:
        return cls(load_index_file(path))

    def search(
        self, query: str, mode: SearchMode, filters: SearchFilters, top_k: int
    ) -> list[SearchHit]:
        words = _query_words(query)
        if not words:
            return []
        permitted = [piece for piece in self._data.pieces if _allowed_by_flags(piece, filters)]
        candidates = [piece for piece in permitted if _allowed_by_language(piece, filters)]
        if mode == "meaning" and not candidates:
            # CodeVision's own fallback is switched off, so an empty filter returns nothing there.
            # We search all permitted pieces instead (spec 3.2).
            candidates = permitted
        scored = [(_score(piece, words, mode), piece) for piece in candidates]
        best = sorted(
            ((score, piece) for score, piece in scored if score > 0),
            key=lambda item: (-item[0], item[1].piece_no),
        )
        return [self._to_hit(piece, score, mode) for score, piece in best[:top_k]]

    def _to_hit(self, piece: IndexPiece, score: float, mode: SearchMode) -> SearchHit:
        return SearchHit(
            source_path=piece.path,
            symbol=piece.symbol,
            line_start=piece.line_start,
            # No commit IDs in the pretend index, so the build ID stands in (decision 13).
            version=self._data.build_id,
            kind=piece.kind,
            language=piece.language,
            snippet=piece.snippet,
            score=round(min(score, 1.0), 3),
            mode=mode,
            deprecated=piece.deprecated,
            restricted=piece.restricted,
        )


class CodeVisionSearchIndex:
    """Placeholder until the work adapter (P15) exists."""

    def search(
        self, query: str, mode: SearchMode, filters: SearchFilters, top_k: int
    ) -> list[SearchHit]:
        raise SearchNotConfiguredError(NOT_CONFIGURED_MESSAGE)


def get_search_index(settings: Settings, index_file: Path = FAKE_INDEX_FILE) -> SearchIndex:
    if settings.search_provider == "codevision":
        return CodeVisionSearchIndex()
    return FakeSearchIndex.from_file(index_file)


def looks_secret(path: str) -> bool:
    """True for paths that look like secret or environment files (spec 3.1)."""
    lowered = path.lower().replace("\\", "/")
    name = lowered.rsplit("/", 1)[-1]
    return (
        name.startswith(".env")
        or name.endswith((".env", ".pem", ".key"))
        or "secret" in lowered
        or "credential" in lowered
    )


def drop_unsafe_hits(hits: list[SearchHit]) -> tuple[list[SearchHit], int]:
    """Our own safety filter, run after any index (rule R3). Returns the kept hits and how many
    were dropped."""
    kept = [
        hit
        for hit in hits
        if not (hit.deprecated or hit.restricted or looks_secret(hit.source_path))
    ]
    return kept, len(hits) - len(kept)


def search_safely(
    index: SearchIndex, query: str, mode: SearchMode, filters: SearchFilters, top_k: int
) -> tuple[list[SearchHit], int]:
    """Search, then drop anything unsafe. The log gets the count, never a path."""
    hits, dropped = drop_unsafe_hits(index.search(query, mode, filters, top_k))
    if dropped:
        logger.info("Search safety filter dropped %d hit(s).", dropped)
    return hits, dropped


def _allowed_by_flags(piece: IndexPiece, filters: SearchFilters) -> bool:
    if piece.deprecated and not filters.include_deprecated:
        return False
    return not (piece.restricted and not filters.include_restricted)


def _allowed_by_language(piece: IndexPiece, filters: SearchFilters) -> bool:
    if piece.kind in _LANGUAGE_NEUTRAL_KINDS:
        return True
    return piece.language.lower() in {name.lower() for name in filters.languages}


def _words(text: str) -> list[str]:
    return _WORD.findall(_CAMEL_JOIN.sub(" ", text).lower())


def _query_words(query: str) -> list[str]:
    seen: dict[str, None] = {}
    for word in _words(query):
        if word not in _STOP_WORDS:
            seen[word] = None
    return list(seen)


def _piece_words(piece: IndexPiece) -> list[str]:
    return _words(" ".join([piece.path, *piece.tags, piece.snippet]))


def _stem(word: str) -> str:
    for ending in ("ing", "ed", "es", "s"):
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[: -len(ending)]
    return word


def _build_synonym_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for group in _SYNONYM_GROUPS:
        stood_for = _stem(group[0])
        for word in group:
            mapping[_stem(word)] = stood_for
    return mapping


_SYNONYMS = _build_synonym_map()


def _meaning_id(word: str) -> str:
    stem = _stem(word)
    return _SYNONYMS.get(stem, stem)


def _score(piece: IndexPiece, query_words: list[str], mode: SearchMode) -> float:
    words = _piece_words(piece)
    if mode == "exact":
        present = set(words)
        return sum(1 for word in query_words if word in present) / len(query_words)
    wanted = {_meaning_id(word) for word in query_words}
    present_ids = {_meaning_id(word) for word in words}
    return len(wanted & present_ids) / len(wanted)
