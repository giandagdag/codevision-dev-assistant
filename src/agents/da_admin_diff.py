"""What changed between two rulebook versions, and the Version history timeline (spec section 10).

Plain code, no AI (D-L). Both rulebooks are flattened to "path -> value". List items are keyed by
their ID or name, never by position, so moving a rule up or down does not look like a rewrite.
A list of plain words (protected files, libraries) is keyed by the word itself, so an edited word
shows as one removed and one added.
"""

import difflib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from db_table_functions.db_tbl_da_requests import list_pinned_request_ids
from db_table_functions.db_tbl_da_rulebook import list_versions
from pydantic_classes.da_rulebook_models import Rulebook

# A changed text longer than this also gets a line diff.
LONG_TEXT_LIMIT = 200

# The keys that name a list item, tried in this order.
_ITEM_KEYS = ("rule_id", "name", "term")

AREA_CHARTER = "Project charter"
AREA_REPOSITORY = "Repository and index"
AREA_CATALOG = "Capability catalog"
AREA_UI = "UI standards"
AREA_CODING = "Coding standards"
AREA_BUILD = "Build and test"

_REPOSITORY_FIELDS = (
    "allowed_folders",
    "new_file_name_pattern",
    "workspace_markers",
    "workspace_max_file_kb",
)
_CODING_FIELDS = ("approved_libraries", "build_blocked_imports", "sonar_severity_map")


@dataclass(frozen=True)
class RulebookDiff:
    added: dict[str, Any] = field(default_factory=dict)
    removed: dict[str, Any] = field(default_factory=dict)
    # path -> (old value, new value)
    changed: dict[str, tuple[Any, Any]] = field(default_factory=dict)

    @property
    def paths(self) -> list[str]:
        return sorted({*self.added, *self.removed, *self.changed})

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


@dataclass(frozen=True)
class TimelineRow:
    version_number: int
    saved_at: datetime
    saved_by: str
    change_note: str
    restored_from: int | None
    areas: list[str]
    pinned_request_ids: list[str]
    is_active: bool

    @property
    def pinned_count(self) -> int:
        return len(self.pinned_request_ids)


def flatten_rulebook(rulebook: Rulebook) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    _flatten(rulebook.model_dump(mode="json"), "", flat)
    return flat


def _flatten(value: Any, path: str, flat: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _flatten(item, f"{path}.{key}" if path else key, flat)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _flatten(item, f"{path}[{_item_key(item, index)}]", flat)
    else:
        flat[path] = value


def _item_key(item: Any, index: int) -> str:
    if isinstance(item, dict):
        for key in _ITEM_KEYS:
            if key in item:
                return str(item[key])
        return str(index)
    return str(item)


def diff_rulebooks(old: Rulebook, new: Rulebook) -> RulebookDiff:
    before, after = flatten_rulebook(old), flatten_rulebook(new)
    return RulebookDiff(
        added={path: after[path] for path in after if path not in before},
        removed={path: before[path] for path in before if path not in after},
        changed={
            path: (before[path], after[path])
            for path in before
            if path in after and before[path] != after[path]
        },
    )


def text_line_diff(old: Any, new: Any) -> list[str]:
    """A line diff for a changed text over LONG_TEXT_LIMIT characters; empty for anything else."""
    if not (isinstance(old, str) and isinstance(new, str)):
        return []
    if max(len(old), len(new)) <= LONG_TEXT_LIMIT:
        return []
    lines = difflib.unified_diff(
        _split_for_diff(old), _split_for_diff(new), "old", "new", lineterm="", n=1
    )
    return list(lines)


def _split_for_diff(text: str) -> list[str]:
    # A long text is often one line; split on sentences so the diff can point at what changed.
    return text.replace(". ", ".\n").splitlines()


def area_of_path(path: str) -> str:
    """Which console tab a flattened path belongs to."""
    if path.startswith("charter"):
        return AREA_CHARTER
    if path.startswith("rules["):
        return AREA_UI if path.startswith("rules[CV-UI-") else AREA_CODING
    if path.startswith("golden_examples"):
        return AREA_CODING
    if path.startswith("policy.capabilities"):
        return AREA_CATALOG
    name = path.split(".", 2)[1].split("[", 1)[0] if path.startswith("policy.") else ""
    if name in _REPOSITORY_FIELDS:
        return AREA_REPOSITORY
    if name in _CODING_FIELDS:
        return AREA_CODING
    return AREA_BUILD


def areas_touched(diff: RulebookDiff) -> list[str]:
    return sorted({area_of_path(path) for path in diff.paths})


def build_timeline(db_path: Path) -> list[TimelineRow]:
    """Every version, newest first, with the areas it touched and the requests pinned to it."""
    versions = list_versions(db_path)  # newest first
    pinned = list_pinned_request_ids(db_path)
    rows = []
    for position, version in enumerate(versions):
        older = versions[position + 1] if position + 1 < len(versions) else None
        areas = (
            areas_touched(diff_rulebooks(older.rulebook, version.rulebook)) if older else []
        )
        rows.append(
            TimelineRow(
                version_number=version.version_number,
                saved_at=version.saved_at,
                saved_by=version.saved_by,
                change_note=version.change_note,
                restored_from=version.restored_from,
                areas=areas,
                pinned_request_ids=pinned.get(version.version_number, []),
                is_active=position == 0,
            )
        )
    return rows
