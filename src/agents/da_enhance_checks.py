"""Plain-code rules for Enhance, part A: finding the program (Phase 9, spec sections 3, 4, 6).
No AI, no database, no screen: every rule can be tested with made-up values.

AS400 picture: WRKOBJ plus the application owner list. You look the member up by name, then see
which application area owns it and who signs off changes there.
"""

import re
from collections.abc import Iterable
from fnmatch import fnmatchcase

from agents.da_approach_checks import matches_any, normalise_path
from agents.da_code_splitter import MODULE_SYMBOL, split_python_file
from agents.da_search_index import drop_unsafe_hits
from pydantic_classes.da_discovery_models import SearchHit
from pydantic_classes.da_enhance_models import Candidate
from pydantic_classes.da_request_record_models import MustNotChange, RequestRecord
from pydantic_classes.da_rulebook_models import Capability, Policy

NO_CANDIDATES_TEXT = (
    "I could not find that program. Try its file name, or describe what it does in other words."
)
NOTHING_SPECIAL = "nothing special"
_WORD = re.compile(r"[a-z0-9_]+")
_CAMEL_JOIN = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_DRIVE_LETTER = re.compile(r"^[A-Za-z]:")
_MIN_WORD = 3
# A stem this short ("app", "db") would match too many messages to be called a Best match.
_MIN_BEST_WORD = 4
_STOP_WORDS = frozenset(
    "the and for with this that from into when what which where does not new add fix change "
    "make report shows show".split()
)


# --- Find by name (spec section 4, steps 2 to 4) ---


def keep_code_hits(hits: Iterable[SearchHit]) -> list[SearchHit]:
    """Only `code` pieces, and never a deprecated, restricted or secret-looking file (9-7)."""
    safe, _dropped = drop_unsafe_hits(list(hits))
    return [hit for hit in safe if hit.kind == "code"]


def name_candidates(message: str, hits: Iterable[SearchHit], top_k: int) -> list[Candidate]:
    """Case-insensitive whole-word match of his words against file stems and symbols.

    One candidate per file. A word that equals a file stem or a symbol makes it a Best match
    (score 1.0). Other files that share name words get a lower score. At most `top_k` files."""
    words = _query_words(message)
    if not words:
        return []
    by_path: dict[str, Candidate] = {}
    for hit in keep_code_hits(hits):
        score, best = _name_score(words, hit)
        if score <= 0:
            continue
        old = by_path.get(hit.source_path)
        if old is None or (best, score) > (old.best_match, old.score):
            by_path[hit.source_path] = Candidate(
                path=hit.source_path, how_found="name", score=round(score, 3), best_match=best
            )
    ranked = sorted(by_path.values(), key=lambda c: (not c.best_match, -c.score, c.path))
    return ranked[:top_k]


def meaning_candidates(hits: Iterable[SearchHit], top_k: int) -> list[Candidate]:
    """The meaning search, one candidate per file, best score first, at most `top_k` files."""
    best_score: dict[str, float] = {}
    for hit in keep_code_hits(hits):
        best_score[hit.source_path] = max(best_score.get(hit.source_path, 0.0), hit.score)
    ranked = sorted(best_score.items(), key=lambda item: (-item[1], item[0]))
    return [
        Candidate(path=path, how_found="meaning", score=round(score, 3))
        for path, score in ranked[:top_k]
    ]


def merge_candidates(by_name: list[Candidate], by_meaning: list[Candidate]) -> list[Candidate]:
    """Merge by path. A file found both ways says "name+meaning". Best matches come first."""
    merged: dict[str, Candidate] = {}
    for candidate in by_name:
        merged[candidate.path] = candidate
    for candidate in by_meaning:
        old = merged.get(candidate.path)
        if old is None:
            merged[candidate.path] = candidate
        else:
            merged[candidate.path] = old.model_copy(
                update={"how_found": "name+meaning", "score": max(old.score, candidate.score)}
            )
    return sorted(merged.values(), key=lambda c: (not c.best_match, -c.score, c.path))


def switch_offer_candidate(message: str, hits: Iterable[SearchHit]) -> Candidate | None:
    """The file to offer in the card 1 switch offer, or None. Only a Best match counts (D-N);
    a loose word overlap never triggers the offer."""
    for candidate in name_candidates(message, hits, top_k=5):
        if candidate.best_match:
            return candidate
    return None


def find_round_allowed(rounds_used: int, policy: Policy) -> bool:
    """False once `enhance_find_max_rounds` searches found nothing: only Get help is left (9-10)."""
    return rounds_used < policy.enhance_find_max_rounds


def _query_words(message: str) -> list[str]:
    seen: dict[str, None] = {}
    for word in _WORD.findall(message.lower()):
        if len(word) >= _MIN_WORD and word not in _STOP_WORDS:
            seen[word] = None
    return list(seen)


def _stem_of(path: str) -> str:
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0].lower()


def _symbol_names(symbol: str) -> list[str]:
    if not symbol or symbol == MODULE_SYMBOL:
        return []
    return [symbol.lower(), symbol.rsplit(".", 1)[-1].lower()]


def _name_parts(text: str) -> set[str]:
    spaced = _CAMEL_JOIN.sub(" ", text).lower().replace("_", " ").replace(".", " ")
    return {part for part in spaced.split() if len(part) >= _MIN_WORD}


def _name_score(words: list[str], hit: SearchHit) -> tuple[float, bool]:
    """(score, is Best match) for one piece against his words."""
    stem = _stem_of(hit.source_path)
    exact_names = {stem, *_symbol_names(hit.symbol)}
    if any(word in exact_names and len(word) >= _MIN_BEST_WORD for word in words):
        return 1.0, True
    parts = _name_parts(stem) | _name_parts(hit.symbol)
    hits = sum(1 for word in words if word in parts)
    return (hits / len(words) if hits else 0.0), False


# --- catalog lookup (spec section 4 step 5; D-B) ---


def lookup_capability(path: str, capabilities: list[Capability]) -> Capability | None:
    """First capability whose pattern matches the lower-case path wins. None = not in the
    catalog (9-8)."""
    lower = normalise_path(path).lower()
    for capability in capabilities:
        if any(fnmatchcase(lower, pattern.lower()) for pattern in capability.path_patterns):
            return capability
    return None


def with_catalog(candidate: Candidate, capabilities: list[Capability]) -> Candidate:
    """The candidate with its capability and named senior filled in, or unchanged if none."""
    found = lookup_capability(candidate.path, capabilities)
    if found is None:
        return candidate
    return candidate.model_copy(
        update={"capability": found.name, "named_senior": found.named_senior}
    )


# --- target validation (spec section 4, last paragraph; 9-11) ---


def target_problems(paths: list[str], policy: Policy) -> list[str]:
    """Every reason these targets cannot be confirmed. Empty list = fine."""
    problems: list[str] = []
    if not paths:
        return ["Pick at least one program."]
    if len(paths) > policy.max_files:
        problems.append(f"At most {policy.max_files} programs can be changed in one request.")
    folders = [normalise_path(f).rstrip("/").lower() for f in policy.allowed_folders]
    seen: set[str] = set()
    for raw in paths:
        path = normalise_path(raw)
        lower = path.lower()
        reason = _one_target_problem(path, lower, folders, policy)
        if reason:
            problems.append(f"{path}: {reason}")
        if lower in seen:
            problems.append(f"{path} is listed more than once.")
        seen.add(lower)
    return problems


def _one_target_problem(path: str, lower: str, folders: list[str], policy: Policy) -> str:
    if path.startswith("/") or _DRIVE_LETTER.match(path) or ".." in path.split("/"):
        return "the path must be relative, with no drive letter and no '..'."
    if not lower.endswith(".py"):
        return "only Python (.py) files can be changed here."
    if not any(lower.startswith(folder + "/") for folder in folders):
        return f"it is not in an allowed folder. Allowed: {', '.join(policy.allowed_folders)}."
    if matches_any(lower, policy.protected_files):
        return "it is a protected file. Ask a senior to change it."
    return ""


# --- functions in scope (spec section 6, step 4; 9-21) ---


def available_symbols(path: str, text: str) -> list[str]:
    """The real functions, classes and methods of a file, from the Phase 3 splitter."""
    return [
        piece.symbol
        for piece in split_python_file(path, text)
        if piece.symbol and piece.symbol != MODULE_SYMBOL
    ]


def keep_known_symbols(
    guess: Iterable[str], available: Iterable[str]
) -> tuple[list[str], list[str]]:
    """(kept, dropped) of the AI's guess. A symbol not in the split is dropped (9-21)."""
    known = set(available)
    kept: list[str] = []
    dropped: list[str] = []
    for symbol in guess:
        if symbol in known and symbol not in kept:
            kept.append(symbol)
        elif symbol not in known and symbol not in dropped:
            dropped.append(symbol)
    return kept, dropped


def scope_problems(chosen: list[str], available: Iterable[str]) -> list[str]:
    """Why his ticked list cannot be saved: unknown symbols, or nothing ticked."""
    known = set(available)
    problems = [
        f"{symbol} is not a function in the chosen programs."
        for symbol in chosen
        if symbol not in known
    ]
    if not chosen:
        problems.append("Tick at least one function that the change touches.")
    return problems


# --- must-not-change items (spec section 6; NC numbering) ---


def nc_number(item_id: str) -> int:
    """NC-6 gives 6."""
    return int(item_id.split("-")[1])


def next_nc_number(records: Iterable[RequestRecord]) -> int:
    """One more than the highest NC ID in ANY version, so an ID is never reused."""
    highest = 0
    for record in records:
        for item in record.must_not_change:
            highest = max(highest, nc_number(item.id))
    return highest + 1


def parse_keep_lines(text: str, policy: Policy) -> tuple[list[str], list[str]]:
    """(lines, problems) from the box "What must NOT change?": one item per line, blank lines
    skipped. "Nothing special" alone gives no items."""
    lines = [line.strip(" -*\t") for line in text.splitlines() if line.strip(" -*\t")]
    if len(lines) == 1 and lines[0].lower().rstrip(".") == NOTHING_SPECIAL:
        return [], []
    problems: list[str] = []
    if len(lines) > policy.enhance_max_keep_items:
        problems.append(
            f"At most {policy.enhance_max_keep_items} items, one per line. You wrote {len(lines)}."
        )
    return lines, problems


def number_keep_items(
    lines: list[str], previous: list[MustNotChange], all_versions: Iterable[RequestRecord]
) -> list[MustNotChange]:
    """Items with the same text as before keep their ID; new text gets the next free number."""
    by_text = {" ".join(item.text.lower().split()): item for item in previous}
    number = next_nc_number(all_versions)
    result: list[MustNotChange] = []
    for line in lines:
        old = by_text.get(" ".join(line.lower().split()))
        if old is not None and all(old.id != done.id for done in result):
            result.append(old)
            continue
        result.append(MustNotChange(id=f"NC-{number}", text=line))
        number += 1
    return result
