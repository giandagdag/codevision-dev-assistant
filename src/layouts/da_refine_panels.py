"""Version history blocks for the Summary and Approach tabs (Phase 8 step 13b, spec section 11).

Presentation only (rule R12): the numbers come from `da_refine_screen.VersionHistory`.
"""

import dash_mantine_components as dmc

from agents.da_refine_screen import VersionHistory
from pydantic_classes.da_refine_models import CriterionChange, RecordDiff

HISTORY_ID = "da-record-history"
APPROACH_LIST_ID = "da-approach-versions"
HISTORY_TITLE = "Version history"
APPROACH_TITLE = "Approach versions"


def _parts(item: dict[str, str] | None) -> str:
    if not item:
        return ""
    given, when, then = (item.get(key, "") for key in ("given", "when", "then"))
    return f"Given {given}, when {when}, then {then}"


def _criterion_line(item: CriterionChange) -> dmc.Text:
    if item.change == "added":
        text = f"{item.id} added: {_parts(item.new)}"
    elif item.change == "removed":
        text = f"{item.id} removed (was: {_parts(item.old)})"
    else:
        text = f"{item.id} changed: {_parts(item.old)}  ->  {_parts(item.new)}"
    return dmc.Text(text, size="sm")


def _diff_block(diff: RecordDiff) -> dmc.Box:
    lines = [dmc.Text(f"v{diff.from_version} to v{diff.to_version}", fw=600, size="sm")]
    lines += [
        dmc.Text(f"{change.field}: {change.old}  ->  {change.new}", size="sm")
        for change in diff.fields
    ]
    lines += [_criterion_line(item) for item in diff.criteria]
    if diff.empty:
        lines.append(dmc.Text("No change in the record.", size="sm", c="dimmed"))
    return dmc.Box(lines)


def version_history_blocks(history: VersionHistory | None) -> list:
    """Empty list when the record has only one version."""
    if history is None or not history.diffs:
        return []
    return [
        dmc.Stack(
            [dmc.Text(HISTORY_TITLE, fw=600), *[_diff_block(d) for d in history.diffs]],
            gap="xs",
            id=HISTORY_ID,
            mt="md",
        )
    ]


def approach_version_blocks(history: VersionHistory | None) -> list:
    """Empty list when no approach version exists."""
    if history is None or not history.approaches:
        return []
    rows = [
        dmc.Text(f"Approach v{number}: source {source}, record v{record}", size="sm")
        for number, source, record in history.approaches
    ]
    return [dmc.Stack([dmc.Text(APPROACH_TITLE, fw=600), *rows], gap="xs", id=APPROACH_LIST_ID)]
