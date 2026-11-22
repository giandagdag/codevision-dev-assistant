"""Fix G6 S2/S3: suggest a first catalog from code links. The AI only names groups of programs.

AS400 picture: the links decide which programs sit together (like a "where used" cross reference);
the AI only reads paths and one-line summaries to find a business name. Never code text, and
nothing here creates a capability: the results are cards for Admin to decide on.
Never logs a prompt or a reply.
"""

from dataclasses import dataclass, replace

from agents.da_admin_tagger import (
    CONFIDENCE,
    NEW_DESCRIPTION_MAX,
    NEW_NAME_MIN,
    RETRY_LINE,
    _cut,
    clean_name,
    is_sendable,
    name_key,
)
from agents.da_admin_tagger import (
    NEW_NAME_MAX as NAME_MAX,
)
from agents.da_code_clusters import Group, groups, path_weights
from agents.da_reply_reader import read_json_object
from agents.da_search_index import DATA_FOLDER
from da_logging import get_logger

logger = get_logger(__name__)

PROMPT_FILE = DATA_FOLDER / "da_group_prompt.md"
MERGE_PROMPT_FILE = DATA_FOLDER / "da_merge_prompt.md"
MAX_PROGRAMS_IN_PROMPT = 40
MAX_CAPABILITIES = 12
# The job's step names (G5 progress bar).
STEP_GROUPING, STEP_NAMING, STEP_MERGING = "Grouping programs", "Naming groups", "Merging"


@dataclass(frozen=True)
class NamedGroup:
    name: str
    description: str
    programs: tuple[str, ...]  # the group without the paths the AI said do not fit
    confidence: str
    folders: tuple[str, ...]
    inside: int
    outside: int
    existing: str = ""  # the name of a capability already in the catalog (a normal proposal for it)


def build_group_prompt(programs: list[str], summaries: dict[str, str]) -> str:
    """Paths and saved one-line summaries only, at most 40 programs."""
    shown = programs[:MAX_PROGRAMS_IN_PROMPT]
    cut = f" (first {len(shown)} of {len(programs)})" if len(programs) > len(shown) else ""
    lines = "\n".join(f"- {p}: {summaries.get(p, '')}".rstrip(": ") for p in shown)
    return PROMPT_FILE.read_text(encoding="utf-8").format(programs=lines, cut_note=cut)


def read_group_reply(text: str, programs: tuple[str, ...]) -> dict | None:
    """The checked reply (name, description, not_in_group, confidence) or None."""
    data = read_json_object(text)
    if data is None:
        return None
    name, description = data.get("name"), data.get("description", "")
    if not isinstance(name, str) or not isinstance(description, str):
        return None
    name = clean_name(name)
    confidence = str(data.get("confidence", "")).strip().lower()
    if not (NEW_NAME_MIN <= len(name) <= NAME_MAX) or confidence not in CONFIDENCE:
        return None
    left_out = data.get("not_in_group", [])
    left_out = [p for p in left_out if p in programs] if isinstance(left_out, list) else []
    return {"name": name, "description": _cut(description, NEW_DESCRIPTION_MAX),
            "not_in_group": left_out, "confidence": confidence}  # fmt: skip


def name_group(group: Group, summaries: dict[str, str], client) -> NamedGroup | None:
    """One AI call for one group, one retry when the reply cannot be read. None = could not name."""
    sendable = [p for p in group.programs if is_sendable(p, [])]
    if not sendable:
        return None
    prompt = build_group_prompt(sendable, summaries)
    for attempt in (prompt, f"{prompt}\n{RETRY_LINE}"):
        try:
            reply = client.complete(attempt)
        except Exception as error:  # noqa: BLE001 - one bad group must not stop the job
            logger.warning("Group naming call failed: %s", type(error).__name__)
            return None
        checked = read_group_reply(reply.text, tuple(sendable))
        if checked:
            kept = tuple(p for p in group.programs if p not in checked["not_in_group"])
            return NamedGroup(
                checked["name"], checked["description"], kept, checked["confidence"],
                group.folders, group.inside, group.outside,
            )
    return None


# --- S3: merge step (AI names plus plain code) ---------------------------------------------------


def _between(a: NamedGroup, b: NamedGroup, weights: dict[str, dict[str, int]]) -> int:
    return sum(weights.get(p, {}).get(q, 0) for p in a.programs for q in b.programs)


def _combine(a: NamedGroup, b: NamedGroup, weights) -> NamedGroup:
    """One group from two; it keeps the bigger one's name and fields."""
    big, small = (a, b) if len(a.programs) >= len(b.programs) else (b, a)
    between = _between(a, b, weights)
    order = {c: i for i, c in enumerate(reversed(CONFIDENCE))}  # low is the lowest
    return replace(
        big,
        programs=tuple(sorted(a.programs + b.programs)),
        folders=tuple(dict.fromkeys(big.folders + small.folders)),
        inside=a.inside + b.inside + between,
        outside=max(0, a.outside + b.outside - 2 * between),
        confidence=min(a.confidence, b.confidence, key=order.get),
        existing=big.existing or small.existing,
    )


def merge_same_names(named: list[NamedGroup], weights) -> list[NamedGroup]:
    """Names equal ignoring case, spaces and a plural "s" become one group (plain code)."""
    first: dict[str, NamedGroup] = {}
    for group in named:
        key = name_key(group.name)
        first[key] = _combine(first[key], group, weights) if key in first else group
    return list(first.values())


def _merge_prompt(named: list[NamedGroup]) -> str:
    areas = "\n".join(f"- {g.name}: {g.description}" for g in named)
    return MERGE_PROMPT_FILE.read_text(encoding="utf-8").format(areas=areas)


def read_merges(text: str) -> list[dict]:
    """The merges the AI asked for: each has 2 or more names plus a checked new name."""
    data = read_json_object(text)
    items = data.get("merges") if data else None
    if not isinstance(items, list):
        return []
    found = []
    for item in (i for i in items if isinstance(i, dict)):
        names = item.get("names")
        name = clean_name(str(item.get("name", "")))
        description = _cut(str(item.get("description", "")), NEW_DESCRIPTION_MAX)
        if isinstance(names, list) and len(names) >= 2 and NEW_NAME_MIN <= len(name) <= NAME_MAX:
            found.append({"names": [str(n) for n in names], "name": name,
                          "description": description})  # fmt: skip
    return found


def ai_merge(named: list[NamedGroup], weights, client) -> list[NamedGroup]:
    """One call with all names; applies the merges it returns. A failed call merges nothing."""
    if len(named) < 2:
        return named
    prompt = _merge_prompt(named)
    merges: list[dict] = []
    for attempt in (prompt, f"{prompt}\n{RETRY_LINE}"):
        try:
            reply = client.complete(attempt)
        except Exception as error:  # noqa: BLE001 - suggestions still work without the merge call
            logger.warning("Group merge call failed: %s", type(error).__name__)
            return named
        data = read_json_object(reply.text)
        if data is not None and isinstance(data.get("merges"), list):
            merges = read_merges(reply.text)
            break
    for merge in merges:
        keys = {name_key(n) for n in merge["names"]}
        hit = [g for g in named if name_key(g.name) in keys]
        if len(hit) < 2:
            continue
        joined = hit[0]
        for other in hit[1:]:
            joined = _combine(joined, other, weights)
        description = merge["description"] or joined.description
        joined = replace(joined, name=merge["name"], description=description)
        named = [g for g in named if g not in hit] + [joined]
    return named


def cap_count(named: list[NamedGroup], weights, limit: int = MAX_CAPABILITIES) -> list[NamedGroup]:
    """Above the limit, the smallest group joins its most-linked neighbour (the largest if none)."""
    named = list(named)
    while len(named) > limit:
        small = min(named, key=lambda g: (len(g.programs), g.name))
        others = [g for g in named if g is not small]
        best = max(others, key=lambda g: (_between(small, g, weights), len(g.programs), g.name))
        named.remove(small)
        named[named.index(best)] = _combine(best, small, weights)
    return named


def mark_existing(named: list[NamedGroup], known: list[str]) -> list[NamedGroup]:
    """A name equal to a catalog capability becomes a normal proposal for that capability."""
    by_key = {name_key(n): n for n in known}
    return [replace(g, existing=by_key.get(name_key(g.name), g.existing)) for g in named]


def suggest(graph: dict, summaries: dict[str, str], client, known: list[str], progress=None):
    """The whole job: groups, names, merges. `progress(step_name)` is called as each step starts."""
    say = progress or (lambda _step: None)
    weights = path_weights(graph)
    say(STEP_GROUPING)
    found = groups(graph)
    say(STEP_NAMING)
    named = [n for n in (name_group(g, summaries, client) for g in found) if n]
    say(STEP_MERGING)
    named = merge_same_names(named, weights)
    named = ai_merge(named, weights, client)
    named = merge_same_names(named, weights)  # the AI may have renamed two groups alike
    named = cap_count(named, weights)
    return sorted(mark_existing(named, known), key=lambda g: (-len(g.programs), g.name))
