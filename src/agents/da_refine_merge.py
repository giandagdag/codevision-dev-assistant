"""Plain-code rules for Refine, code side (Phase 8 sections 7 to 9): his lines, conflicts, merging
the developer's picks, appending to the frozen test set, and building a restore set.

No AI, no database. AS400 picture: two programmers on one source member. Before the app saves,
it compares the member with the version it last saw (like CMPPFM). Where both changed the same
lines, a person picks.

Line numbers: ranges are 0-based and half-open inside this file (start, end). The Conflict model
shown to the developer uses 1-based inclusive numbers.
"""

import ast
import difflib
from dataclasses import dataclass, field

from agents.da_build_checks import find_test_methods
from agents.da_workspace_checks import apply_line_ending, fingerprint, line_ending_of, normalise
from pydantic_classes.da_refine_models import Conflict

LineRange = tuple[int, int]


class MergeError(Exception):
    """A pick is missing, or a test method could not be added. The text says why, in plain words."""


# --- lines ---


def split_lines(text: str) -> list[str]:
    """The lines of a text without their line endings. A final line break adds no empty line."""
    plain = normalise(text)
    lines = plain.split("\n")
    if plain.endswith("\n") or plain == "":
        lines.pop()
    return lines


def join_lines(lines: list[str], ending_text: str) -> str:
    """Lines back to text, in the style (line ending) of `ending_text`, with a final line break."""
    body = "\n".join(lines) + ("\n" if lines else "")
    return apply_line_ending(body, line_ending_of(ending_text))


def changed_ranges(before: str, after: str) -> list[LineRange]:
    """Where `after` differs from `before`, as ranges of lines in `after`. A pure deletion is an
    empty range at the place where the lines were."""
    old, new = split_lines(before), split_lines(after)
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    return [(j1, j2) for tag, _i1, _i2, j1, j2 in matcher.get_opcodes() if tag != "equal"]


def his_lines(written: str, scanned: str) -> list[LineRange]:
    """His lines: what differs between the last version the app wrote and his scanned version."""
    return changed_ranges(written, scanned)


def marker_text(ranges: list[LineRange]) -> str:
    """The sentence for the Generator prompt (spec section 8, R5.3 step 1). Empty when none."""
    parts = []
    for start, end in ranges:
        if end > start:
            first, last = start + 1, end
            where = f"Line {first}" if first == last else f"Lines {first} to {last}"
            parts.append(f"{where} {'was' if first == last else 'were'} written by the developer.")
        else:
            parts.append(f"The developer removed lines after line {start}.")
    if not parts:
        return ""
    return " ".join(parts) + " Do not change them unless the failure report needs it."


# --- conflicts (D-J) ---


@dataclass
class _Group:
    start: int
    end: int
    # (start, end, new_lines) of every AI change inside this group, in order.
    regions: list[tuple[int, int, list[str]]] = field(default_factory=list)
    conflict: bool = False


@dataclass
class MergePlan:
    """What a rebuild changes in one file, split into free changes and conflicts."""

    path: str
    his_text: str
    groups: list[_Group]
    conflicts: list[Conflict]

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


def _near(start: int, end: int, his: LineRange, distance: int) -> bool:
    """True when an AI change [start, end) overlaps his range or is within `distance` lines of
    it. At least 1: the line next to his lines counts (spec section 8)."""
    gap = max(distance, 1)
    return start < his[1] + gap and his[0] < end + gap


def _regions(his_text: str, ai_text: str) -> list[tuple[int, int, list[str]]]:
    old, new = split_lines(his_text), split_lines(ai_text)
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    return [(i1, i2, new[j1:j2]) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"]


def plan_merge(
    path: str,
    written_text: str,
    his_text: str,
    ai_text: str,
    distance: int,
    context: int,
) -> MergePlan:
    """Compare the Generator's result with his version. Any AI change that overlaps his lines, or
    sits within `distance` lines of them, is a conflict (numbered C-1, C-2... in this file)."""
    mine = his_lines(written_text, his_text)
    groups: list[_Group] = []
    for start, end, new_lines in _regions(his_text, ai_text):
        touched = [h for h in mine if _near(start, end, h, distance)]
        if touched:
            low = min([start, *(h[0] for h in touched)])
            high = max([end, *(h[1] for h in touched)])
            groups.append(_Group(low, high, [(start, end, new_lines)], conflict=True))
        else:
            groups.append(_Group(start, end, [(start, end, new_lines)]))
    groups = _merge_groups(groups)
    lines = split_lines(his_text)
    conflicts = []
    for group in (g for g in groups if g.conflict):
        number = len(conflicts) + 1
        conflicts.append(
            Conflict(
                path=path,
                conflict_id=f"C-{number}",
                his_start=group.start + 1,
                his_end=group.end,
                his_lines=lines[group.start : group.end],
                ai_lines=_apply(lines, group),
                context_before=lines[max(0, group.start - context) : group.start],
                context_after=lines[group.end : group.end + context],
            )
        )
    return MergePlan(path=path, his_text=his_text, groups=groups, conflicts=conflicts)


def _merge_groups(groups: list[_Group]) -> list[_Group]:
    """Join groups that share or touch lines, when at least one is a conflict (a free change
    inside a conflict belongs to that conflict). Two free changes are never joined."""
    groups = sorted(groups, key=lambda g: (g.start, g.end))
    changed = True
    while changed:
        changed = False
        for index in range(len(groups) - 1):
            left, right = groups[index], groups[index + 1]
            if (left.conflict or right.conflict) and right.start <= left.end:
                groups[index : index + 2] = [
                    _Group(
                        min(left.start, right.start),
                        max(left.end, right.end),
                        sorted(left.regions + right.regions),
                        conflict=True,
                    )
                ]
                changed = True
                break
    return groups


def _apply(lines: list[str], group: _Group) -> list[str]:
    """The group's span of lines as the AI's version has it."""
    out: list[str] = []
    position = group.start
    for start, end, new_lines in sorted(group.regions):
        out += lines[position:start]
        out += new_lines
        position = end
    out += lines[position : group.end]
    return out


def ai_text(plan: MergePlan) -> str:
    """His text with every AI change applied: the tested result when all picks are the AI's."""
    return _build(plan, {conflict.conflict_id: "ai" for conflict in plan.conflicts})


def merge_picks(plan: MergePlan, picks: dict[str, str]) -> str:
    """The file after his picks: free changes applied, each conflict as he chose ("mine" keeps his
    lines, "ai" takes the AI's). Every conflict needs a pick."""
    missing = [
        c.conflict_id for c in plan.conflicts if picks.get(c.conflict_id) not in ("mine", "ai")
    ]
    if missing:
        raise MergeError(f"Pick Keep mine or Take the AI's for {', '.join(missing)} first.")
    return _build(plan, picks)


def _build(plan: MergePlan, picks: dict[str, str]) -> str:
    lines = split_lines(plan.his_text)
    out: list[str] = []
    position = 0
    conflict_number = 0
    for group in plan.groups:
        out += lines[position : group.start]
        if group.conflict:
            conflict_number += 1
            choice = picks[f"C-{conflict_number}"]
            out += lines[group.start : group.end] if choice == "mine" else _apply(lines, group)
        else:
            out += _apply(lines, group)
        position = group.end
    out += lines[position:]
    return join_lines(out, plan.his_text) if out else ""


# --- the action the Generator gets for a planned file (R5.2) ---


def generator_action(path: str, planned_action: str, known_paths: set[str]) -> str:
    """After the first write, every planned file exists in his folder, so the Generator patches it
    (edit blocks) and never rewrites it. A file with a known text is always `modify`."""
    return "modify" if path in known_paths else planned_action


# --- the frozen test set grows, it is never edited (spec section 7, step 4) ---


def method_fingerprints(test_text: str) -> dict[str, str]:
    """Method name -> fingerprint of its source, to prove earlier methods stayed the same."""
    tree = ast.parse(test_text)
    return {
        name: fingerprint(ast.get_source_segment(test_text, node) or "")
        for name, node in find_test_methods(tree).items()
    }


def append_test_method(test_text: str, method_text: str) -> str:
    """Add one test method at the end of the class that holds the tests. Earlier methods stay
    byte for byte the same. `method_text` is one `def test_...(self):` written at column 0."""
    try:
        method = ast.parse(method_text.strip("\n"))
    except SyntaxError as error:
        raise MergeError(f"The new test has a syntax error on line {error.lineno}.") from error
    names = [n.name for n in method.body if isinstance(n, ast.FunctionDef)]
    if len(method.body) != 1 or len(names) != 1 or not names[0].startswith("test"):
        raise MergeError("The new test must be exactly one method whose name starts with test.")
    tree = ast.parse(test_text)
    if names[0] in find_test_methods(tree):
        raise MergeError(f"A test called {names[0]} is already in the test set.")
    holders = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(isinstance(c, ast.FunctionDef) and c.name.startswith("test") for c in node.body)
    ]
    if not holders:
        raise MergeError("The test set has no test class to add to.")
    holder = max(holders, key=lambda node: node.end_lineno or 0)
    ending = line_ending_of(test_text)
    lines = normalise(test_text).split("\n")
    indented = ["    " + line if line else "" for line in method_text.strip("\n").split("\n")]
    at = holder.end_lineno or len(lines)
    merged = [*lines[:at], "", *indented, *lines[at:]]
    return apply_line_ending("\n".join(merged), ending)


# --- restore (spec section 9, D-L) ---


def build_restore_set(
    planned_paths: list[str], set_files: dict[str, str]
) -> tuple[dict[str, str], list[str]]:
    """(files to write, planned files the set did not have). Always the WHOLE set, in plan order.
    Files that the set did not have are not deleted; the chat lists them."""
    write = {path: set_files[path] for path in planned_paths if path in set_files}
    left = [path for path in planned_paths if path not in set_files]
    return write, left
