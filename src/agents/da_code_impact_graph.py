"""Who uses a module, read from the code link graph (Upgrade G, G3). Plain code, no AI.

AS400 picture: DSPPGMREF turned around, "where used" for a program, two levels deep.
"""

from dataclasses import dataclass

from agents.da_code_graph import IMPORTS, file_module

MAX_LEVELS = 2
STATE_APPROVED = "approved"  # same word da_admin_tagger uses; no import, to keep this file light


@dataclass(frozen=True)
class User:
    module: str
    level: int  # 1 = uses it directly, 2 = uses a direct user
    capability: str  # "" when the module has no approved tag


def _target_module(target: str, modules: set[str]) -> str:
    """calls and uses-class targets are 'module.name'; the module is the longest known prefix."""
    parts = target.split(".")
    for end in range(len(parts), 0, -1):
        if ".".join(parts[:end]) in modules:
            return ".".join(parts[:end])
    return ""


def _users_by_target(graph: dict) -> dict[str, set[str]]:
    """target (module or 'module.name') -> modules that point at it. Self links are left out."""
    modules = {entry["module"] for entry in graph["files"].values()}
    users: dict[str, set[str]] = {}
    for entry in graph["files"].values():
        for kind, _source, target in entry.get("edges", []):
            owner = target if kind == IMPORTS else _target_module(target, modules)
            if owner and owner != entry["module"]:
                users.setdefault(target, set()).add(entry["module"])
                users.setdefault(owner, set()).add(entry["module"])
    return users


def who_uses(graph: dict, name: str) -> list[str]:
    """Modules that import, call or subclass `name` (a module, or 'module.function')."""
    return sorted(_users_by_target(graph).get(name, set()))


def impact_of(graph: dict, module: str, tags: dict[str, dict] | None = None) -> list[User]:
    """Direct users, then their users (2 levels), each with its approved capability tag."""
    users = _users_by_target(graph)
    capability = _capabilities(graph, tags or {})
    seen = {module}
    result: list[User] = []
    frontier = [module]
    for level in range(1, MAX_LEVELS + 1):
        found = sorted({u for m in frontier for u in users.get(m, set())} - seen)
        result += [User(u, level, capability.get(u, "")) for u in found]
        seen |= set(found)
        frontier = found
    return result


def with_used_by(hits: list, graph: dict | None) -> list:
    """Each Discover hit gets the modules that use its module. No graph: hits stay as they are."""
    if graph is None:
        return hits
    users = _users_by_target(graph)
    return [
        hit.model_copy(update={"used_by": sorted(users.get(file_module(hit.source_path), set()))})
        for hit in hits
    ]


def _capabilities(graph: dict, tags: dict[str, dict]) -> dict[str, str]:
    """module -> capability, only for tags Admin approved (a proposal is not a tag yet)."""
    out: dict[str, str] = {}
    for path, entry in graph["files"].items():
        tag = tags.get(path)
        if tag and tag.get("state") == STATE_APPROVED and tag.get("proposed_capability"):
            out[entry["module"]] = str(tag["proposed_capability"])
    return out
