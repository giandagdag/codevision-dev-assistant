"""Find and remove the made-up home starter data in a work rulebook (Fix G4, C1 and C2).

At work the catalog must describe CodeVision, not the practice program. Matching uses the seed's
own values (read from the seed file), never a hard-coded list. Removing saves ONE new version, so
Restore brings everything back. Like clearing leftover test records out of a production file."""

import json
from dataclasses import dataclass
from pathlib import PurePosixPath

from agents.da_admin_modules import PROJECT_ROOT
from agents.da_admin_tag_requeue import requeue_for_removed
from configs.da_config import ConfigError, load_settings
from db_table_functions.db_tbl_da_rulebook import (
    SEED_RULEBOOK_FILE,
    get_active_version,
    load_rulebook_file,
    save_new_version,
)
from pydantic_classes.da_rulebook_models import Rulebook

FAKE_FOLDER = "da_fake_codevision"
SCOPE_TEXT = "The Folder scope is the made-up practice folder."
ACTION_ALL = "starter_all"
ACTION_ONE = "starter_rm:"  # followed by the row number in the leftover list
_GLOB_MARKS = "*?["


@dataclass(frozen=True)
class Leftover:
    kind: str  # "scope", "capability" or "pattern"
    capability: str  # "" for the scope
    text: str  # the scope, the capability name, or the pattern


def _made_up_files() -> set[str]:
    """Paths of the practice program (relative to its folder) and the seed's own module paths."""
    root = PROJECT_ROOT / "src" / "data" / FAKE_FOLDER
    files = {p.relative_to(root).as_posix().lower() for p in root.rglob("*.py")}
    seed = json.loads(SEED_RULEBOOK_FILE.read_text(encoding="utf-8"))
    return files | {p.lower() for p in _module_paths(seed)}


def _module_paths(node) -> list[str]:
    if isinstance(node, dict):
        found = [node["module_path"]] if isinstance(node.get("module_path"), str) else []
        return found + [p for v in node.values() for p in _module_paths(v)]
    if isinstance(node, list):
        return [p for v in node for p in _module_paths(v)]
    return []


def _is_seed_capability(cap, seed_caps) -> bool:
    key = (cap.name, cap.description, cap.named_senior, cap.backup_senior)
    return any(key == (s.name, s.description, s.named_senior, s.backup_senior) for s in seed_caps)


def _names_made_up_file(pattern: str, files: set[str]) -> bool:
    text = pattern.strip().replace("\\", "/").lower()
    if any(mark in text for mark in _GLOB_MARKS):
        return False
    text = text.removeprefix(f"src/data/{FAKE_FOLDER}/")
    return str(PurePosixPath(text)) in files


def starter_leftovers(rulebook: Rulebook) -> list[Leftover]:
    """Everything in this rulebook that came from the home seed. Scope first, then the catalog."""
    policy = rulebook.policy
    found = []
    scope = policy.index_folder_scope.replace("\\", "/")
    if FAKE_FOLDER in scope.split("/"):
        found.append(Leftover("scope", "", policy.index_folder_scope))
    seed_caps = load_rulebook_file(SEED_RULEBOOK_FILE).policy.capabilities
    files = _made_up_files()
    for cap in policy.capabilities:
        if _is_seed_capability(cap, seed_caps):
            found.append(Leftover("capability", cap.name, cap.name))
            continue
        found += [
            Leftover("pattern", cap.name, p)
            for p in cap.path_patterns
            if _names_made_up_file(p, files)
        ]
    return found


def starter_at_work(rulebook: Rulebook) -> list[Leftover]:
    """The same list, but only at work: at home the starter data is the point."""
    try:
        if load_settings().llm_provider != "onprem":
            return []
    except ConfigError:
        return []
    return starter_leftovers(rulebook)


def _without(rulebook: Rulebook, gone: list[Leftover]) -> Rulebook:
    policy = rulebook.policy
    drop_caps = {x.text for x in gone if x.kind == "capability"}
    drop_patterns = {(x.capability, x.text) for x in gone if x.kind == "pattern"}
    caps = []
    for cap in policy.capabilities:
        if cap.name in drop_caps:
            continue
        kept = [p for p in cap.path_patterns if (cap.name, p) not in drop_patterns]
        if kept:  # a capability needs at least one pattern, so it goes with its last one
            caps.append(cap.model_copy(update={"path_patterns": kept}))
    update = {"capabilities": caps}
    if any(x.kind == "scope" for x in gone):
        update["index_folder_scope"] = ""
    return rulebook.model_copy(update={"policy": policy.model_copy(update=update)})


def _note(gone: list[Leftover]) -> str:
    parts = []
    if any(x.kind == "scope" for x in gone):
        parts.append("the made-up folder scope")
    for kind, word in (("capability", "capabilities"), ("pattern", "patterns")):
        count = sum(1 for x in gone if x.kind == kind)
        if count:
            parts.append(f"{count} {word if count != 1 else kind}")
    return "Removed starter items: " + ", ".join(parts)


def remove_starter(settings, admin_id: str, action: str) -> str:
    """Do ACTION_ALL or ACTION_ONE<n> as one new version. Returns the sentence to show."""
    active = get_active_version(settings.db_path)
    leftovers = starter_leftovers(active.rulebook)
    if action == ACTION_ALL:
        gone = leftovers
    else:
        index = int(action.removeprefix(ACTION_ONE))
        gone = leftovers[index : index + 1]
    if not gone:
        return "There was nothing to remove."
    note = _note(gone)
    saved = save_new_version(
        settings.db_path, _without(active.rulebook, gone), active.version_number, admin_id, note
    )
    kept = {c.name for c in saved.rulebook.policy.capabilities}
    removed = {c.name for c in active.rulebook.policy.capabilities} - kept
    back = requeue_for_removed(removed, admin_id)
    note += f" ({back} approved programs back in the queue)" if back else ""
    return (
        f"{note}. The rulebook is now v{saved.version_number}; "
        f"restore v{active.version_number} to undo."
    )
