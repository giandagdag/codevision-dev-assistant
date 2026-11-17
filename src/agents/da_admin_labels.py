"""Plain words for field names on the Admin screens (fix 11-1, section 4). Plain code, no AI.

AS400 picture: the column headings in DDS (TEXT keyword), not the short field names.
"""

import re

LABELS = {
    "DA_SEARCH_PROVIDER": "Code search source",
    "DA_SEARCH_TOP_K": "Search results per query",
    "DA_DISCOVERY_MAX_ROUNDS": "Discover rounds per request",
    "DA_MAIN_SOURCE": "Where the current code comes from",
    "DA_SANDBOX_SOURCE_DIR": "Sandbox copy of CodeVision",
    "DA_CODE_INDEX_DIR": "Folder of the CodeVision index",
    "DA_CODE_INDEX_MAX_DISTANCE": "How close a search result must be",
    "build_max_rounds": "Max fix rounds",
    "build_test_timeout_seconds": "Test time limit (seconds)",
    "max_files": "Max files per request",
    "max_material_decisions": "Decision limit",
    "allowed_folders": "Allowed folders",
    "workspace_markers": "Workspace markers",
    "workspace_max_file_kb": "Workspace max file size (KB)",
    "new_file_name_pattern": "New file name pattern",
}

# A raw name: a DA_ setting, or a lower-case word with an underscore (a field name).
_RAW_NAME = re.compile(r"\bDA_[A-Z_]+\b|\b[a-z]+(?:_[a-z0-9]+)+\b")


def label(name: str) -> str:
    """The plain words for a field name; an unknown name gets underscores turned into spaces."""
    return LABELS.get(name) or name.replace("_", " ").strip().capitalize()


def raw_names_in(text: str, allowed: frozenset[str] = frozenset()) -> list[str]:
    """Raw names found in drawn text. `allowed` holds code-chip texts (file paths, rule IDs)."""
    return [m for m in _RAW_NAME.findall(text) if m not in allowed]
