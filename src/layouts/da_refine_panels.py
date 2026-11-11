"""Version history blocks for the Summary and Approach tabs (Phase 8 step 13b, spec section 11).

Presentation only (rule R12): the numbers come from `da_refine_screen.VersionHistory`.
"""

import dash_mantine_components as dmc

from agents.da_check_words import CHECK_KIND, check_version_name
from agents.da_refine_screen import DRAFT_TAG_WORDS, VersionHistory
from pydantic_classes.da_refine_models import CriterionChange, RecordDiff

HISTORY_ID = "da-record-history"
APPROACH_LIST_ID = "da-approach-versions"
HISTORY_TITLE = "Version history"
APPROACH_TITLE = "Approach versions"


def version_name(row) -> str:
    """The name of one Versions row: a check run reads "Test run N (your edits)" (F6)."""
    if row.kind == CHECK_KIND:
        return check_version_name(row.build_number)
    return f"Build {row.build_number} ({row.kind})"


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


DRAFT_ID = "da-record-draft"
DRAFT_COLOURS = {"new": "green", "changed": "orange", "removed": "red"}


def draft_blocks(history: VersionHistory | None) -> list:
    """F2: the draft v(N+1) criteria with their tags, before Confirm. Empty with no draft."""
    if history is None or not history.draft:
        return []
    rows = [_draft_row(row, history.draft_version) for row in history.draft]
    title = f"Draft version {history.draft_version} (not saved yet)"
    return [dmc.Stack([dmc.Text(title, fw=600), *rows], gap="xs", id=DRAFT_ID, mt="md")]


def _draft_row(row, version: int) -> dmc.Box:
    struck = {"textDecoration": "line-through"}
    head = [dmc.Text(row.criterion_id, fw=600, size="sm")]
    if row.tag:
        label = DRAFT_TAG_WORDS[row.tag].format(n=version)
        head.append(dmc.Badge(label, color=DRAFT_COLOURS[row.tag], variant="light"))
    body = []
    if row.old_text:
        body.append(dmc.Text(row.old_text, size="sm", c="dimmed", style=struck))
    body.append(dmc.Text(row.text, size="sm", style=struck if row.tag == "removed" else None))
    return dmc.Box(
        [dmc.Group(head, gap="xs"), *body],
        p="xs",
        bg="yellow.1" if row.tag in ("new", "changed") else None,
    )


def version_history_blocks(history: VersionHistory | None) -> list:
    """The draft (at the checkpoint) and the version diffs. Empty when the record has only one
    version and no draft."""
    if history is None:
        return []
    blocks = draft_blocks(history)
    if history.diffs:
        blocks.append(
            dmc.Stack(
                [dmc.Text(HISTORY_TITLE, fw=600), *[_diff_block(d) for d in history.diffs]],
                gap="xs",
                id=HISTORY_ID,
                mt="md",
            )
        )
    return blocks


TAG_ID = "da-refine-tag"
SIDE_ID = "da-edit-side-by-side"
CONFLICTS_ID = "da-conflicts"
CONFLICT_PICK_TYPE = "da-conflict-pick"
VERSIONS_ID = "da-versions"
PROTECTION_ID = "da-edit-protection"
MONO = {"fontFamily": "monospace", "whiteSpace": "pre-wrap"}


def _side_by_side(diff) -> dmc.Box:
    """Left: what the app last wrote. Right: his version. Changed rows are marked."""
    rows = [
        dmc.TableTr(
            [
                dmc.TableTd(dmc.Text(left, size="xs", style=MONO)),
                dmc.TableTd(
                    dmc.Text(right, size="xs", style=MONO, fw=700 if changed else 400),
                    bg="yellow.1" if changed else None,
                ),
            ]
        )
        for left, right, changed in diff.rows
    ]
    head = dmc.TableThead(dmc.TableTr([dmc.TableTh("App wrote"), dmc.TableTh("Your version")]))
    return dmc.Box(
        [dmc.Text(diff.path, fw=600, size="sm"), dmc.Table([head, dmc.TableTbody(rows)])]
    )


def _lines(label: str, lines: list[str]) -> dmc.Box:
    text = "\n".join(lines) if lines else "(nothing)"
    return dmc.Box([dmc.Text(label, fw=600, size="xs"), dmc.Code(text, block=True)])


def _conflict(item) -> dmc.Box:
    picked = {"mine": "Keep mine", "ai": "Take the AI's"}.get(item.choice or "", "")
    buttons = [
        dmc.Button(
            label,
            id={
                "type": CONFLICT_PICK_TYPE,
                "path": item.path,
                "conflict": item.conflict_id,
                "choice": key,
            },
            size="xs",
            variant="filled" if item.choice == key else "default",
        )
        for key, label in (("mine", "Keep mine"), ("ai", "Take the AI's"))
    ]
    return dmc.Box(
        [
            dmc.Text(
                f"{item.path} {item.conflict_id}: lines {item.his_start} to {item.his_end}",
                fw=600,
                size="sm",
            ),
            *([_lines("Before", item.context_before)] if item.context_before else []),
            _lines("Yours", item.his_lines),
            _lines("AI's", item.ai_lines),
            *([_lines("After", item.context_after)] if item.context_after else []),
            dmc.Group(buttons, gap="xs"),
            dmc.Text(f"Picked: {picked}", size="xs") if picked else None,
        ]
    )


def refine_build_blocks(panel) -> list:
    """The Refine parts of the Build tab. Empty list when there is nothing to show."""
    blocks: list = []
    if panel is None:
        return blocks
    if panel.tag:
        blocks.append(dmc.Badge(panel.tag, id=TAG_ID, variant="light"))
    if panel.conflicts:
        blocks.append(
            dmc.Stack(
                [
                    dmc.Text("Places where your lines and the AI's change meet", fw=600),
                    *[_conflict(c) for c in panel.conflicts],
                ],
                id=CONFLICTS_ID,
                gap="xs",
            )
        )
    if panel.diffs:
        blocks.append(
            dmc.Stack(
                [
                    dmc.Text("Your edits", fw=600),
                    *[_side_by_side(d) for d in panel.diffs],
                    dmc.Text(panel.not_tested_line, size="sm", c="orange"),
                    dmc.Text(panel.only_planned_line, size="xs", c="dimmed"),
                ],
                id=SIDE_ID,
                gap="xs",
            )
        )
    if panel.versions:
        rows = [
            dmc.Text(
                f"{version_name(v)}: {v.label}, {', '.join(v.files)}"
                + (" (last tested)" if v.is_last_tested else ""),
                size="sm",
            )
            for v in panel.versions
        ]
        blocks.append(dmc.Stack([dmc.Text("Versions", fw=600), *rows], id=VERSIONS_ID, gap="xs"))
    if panel.rules:
        blocks.append(
            dmc.Stack(
                [
                    dmc.Text("How your edits are protected", fw=600),
                    *[dmc.Text(f"{n}. {rule}", size="sm") for n, rule in enumerate(panel.rules, 1)],
                ],
                id=PROTECTION_ID,
                gap="xs",
            )
        )
    return blocks


def approach_version_blocks(history: VersionHistory | None) -> list:
    """Empty list when no approach version exists."""
    if history is None or not history.approaches:
        return []
    rows = [
        dmc.Text(f"Approach v{number}: source {source}, record v{record}", size="sm")
        for number, source, record in history.approaches
    ]
    return [dmc.Stack([dmc.Text(APPROACH_TITLE, fw=600), *rows], gap="xs", id=APPROACH_LIST_ID)]
